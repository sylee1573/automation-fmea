"""
Phase 3: FMEA 일괄 인덱싱 파이프라인

quality_filter.py 출력 CSV (RAG_투입=O, A/B 등급)를 읽어
FMEA Excel 행을 파싱하고 Chroma Vector DB에 인덱싱.

실행:
  python indexer.py --input 목록표_graded.csv --customer-id hyundai
  python indexer.py --input 목록표_graded.csv --customer-id hyundai --reset   # 전체 재인덱싱
  python indexer.py --input 목록표_graded.csv --customer-id hyundai --limit 10 # 테스트

멀티테넌트: --customer-id 로 고객사별 격리. 고객사가 여러 곳이면 각각 실행.
"""

import argparse
import csv
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from preprocessing.excel_parser import parse_fmea_excel
from rag.vector_db import get_client, get_collection, delete_collection, collection_stats
from rag.embeddings import embed_texts


# ─── FMEA 행 → 검색용 텍스트 변환 ──────────────────────────────────────────

def row_to_text(row: dict) -> str:
    """FMEA 1행을 검색 가능한 자연어 텍스트로 변환"""
    effect = row.get("effect_end_user") or row.get("effect") or ""
    parts = [
        ("공정", row.get("process_step", "")),
        ("고장유형", row.get("failure_mode", "")),
        ("원인", row.get("cause", "")),
        ("영향", effect),
        ("예방관리", row.get("prevention_controls", "")),
        ("검출관리", row.get("detection_controls", "")),
    ]
    return " | ".join(f"{k}: {v}" for k, v in parts if str(v or "").strip())


def make_doc_id(file_path: str, row_idx: int) -> str:
    h = hashlib.md5(file_path.encode("utf-8")).hexdigest()[:8]
    return f"{h}_{row_idx:04d}"


# ─── 단일 파일 인덱싱 ─────────────────────────────────────────────────────────

def index_file(collection, record: dict, customer_id: str) -> tuple[int, int]:
    """
    FMEA Excel 1개 파일을 파싱하여 collection에 upsert.
    반환: (인덱싱된 행 수, 빈 행으로 건너뜀 수)
    """
    file_path = str(Path(record.get("경로", "")) / record.get("파일명", ""))
    quality_grade = record.get("품질등급", "B")
    factory_type = (record.get("태그_공장명") or record.get("공장명_추정", "")).strip()
    process_type = (record.get("태그_공정유형") or record.get("공정유형_추정", "")).strip()
    year = (record.get("태그_작성연도") or record.get("연도_추정", "")).strip()

    parsed = parse_fmea_excel(file_path)
    if "error" in parsed or not parsed.get("rows"):
        return 0, 0

    rows = parsed["rows"]
    texts, ids, metadatas = [], [], []

    for idx, row in enumerate(rows):
        text = row_to_text(row)
        if not text.replace("|", "").strip():
            continue

        texts.append(text)
        ids.append(make_doc_id(file_path, idx))
        metadatas.append({
            "file_path": file_path,
            "customer_id": customer_id,
            "factory_type": factory_type,
            "process_type": process_type,
            "quality_grade": quality_grade,
            "year": year,
            "process_step": str(row.get("process_step") or ""),
            "failure_mode": str(row.get("failure_mode") or ""),
            "S": str(row.get("S") or ""),
            "AP": str(row.get("AP") or row.get("rpn_ap") or ""),
        })

    if not texts:
        return 0, len(rows)

    embeddings = embed_texts(texts)
    collection.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
    return len(texts), len(rows) - len(texts)


# ─── 메인 인덱싱 파이프라인 ───────────────────────────────────────────────────

def run_indexer(
    csv_path: str,
    customer_id: str,
    db_path: str = None,
    reset: bool = False,
    limit: int = 0,
):
    with open(csv_path, encoding="utf-8-sig") as f:
        all_records = list(csv.DictReader(f))

    rag_records = [r for r in all_records if r.get("RAG_투입") == "O"]
    if limit:
        rag_records = rag_records[:limit]

    print(f"[Phase 3] Vector DB 인덱싱")
    print(f"  고객사 ID  : {customer_id}")
    print(f"  전체 파일  : {len(all_records)}개")
    print(f"  RAG 대상   : {len(rag_records)}개 (A/B 등급)")
    if limit:
        print(f"  제한 (테스트): {limit}개")

    client = get_client(db_path)

    if reset:
        try:
            delete_collection(client, customer_id)
            print(f"  기존 collection 삭제 완료")
        except Exception:
            pass

    collection = get_collection(client, customer_id)
    print(f"  Collection : fmea_{customer_id} (현재 {collection.count()}개 문서)\n")

    total_indexed = total_skipped = total_errors = 0

    for i, record in enumerate(rag_records, 1):
        name = record.get("파일명", "")
        grade = record.get("품질등급", "?")
        print(f"  [{i:3}/{len(rag_records)}] [{grade}] {name[:42]}", end=" ... ", flush=True)
        try:
            indexed, skipped = index_file(collection, record, customer_id)
            total_indexed += indexed
            total_skipped += skipped
            msg = f"{indexed}행"
            if skipped:
                msg += f" ({skipped}건 빈행 제외)"
            print(msg)
        except Exception as e:
            print(f"오류: {e}")
            total_errors += 1

    stats = collection_stats(collection)
    a_count = sum(1 for r in rag_records if r.get("품질등급") == "A")
    b_count = sum(1 for r in rag_records if r.get("품질등급") == "B")

    print(f"\n  {'─'*50}")
    print(f"  인덱싱 완료")
    print(f"    A등급 파일 : {a_count}개")
    print(f"    B등급 파일 : {b_count}개")
    print(f"    추가된 행  : {total_indexed:5}개")
    print(f"    건너뜀     : {total_skipped:5}개 (빈행)")
    print(f"    오류 파일  : {total_errors:5}개")
    print(f"    DB 총 문서 : {stats['count']:5}개")
    print(f"  {'─'*50}")
    print(f"\n  → 다음 단계: Phase 4 Multi-Agent 구성")


def main():
    parser = argparse.ArgumentParser(description="Phase 3 — FMEA Vector DB 인덱싱")
    parser.add_argument("--input", required=True,
                        help="quality_filter.py 출력 CSV (RAG_투입 컬럼 포함)")
    parser.add_argument("--customer-id", required=True,
                        help="고객사 ID (예: hyundai, kia, gm). collection 이름에 사용")
    parser.add_argument("--db-path", default="",
                        help="Chroma DB 저장 경로 (기본: data/chroma)")
    parser.add_argument("--reset", action="store_true",
                        help="기존 collection 삭제 후 전체 재인덱싱")
    parser.add_argument("--limit", type=int, default=0,
                        help="처리할 최대 파일 수 (테스트: --limit 5)")
    args = parser.parse_args()

    run_indexer(
        csv_path=args.input,
        customer_id=args.customer_id,
        db_path=args.db_path or None,
        reset=args.reset,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
