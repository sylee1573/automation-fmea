#!/usr/bin/env python3
"""
Phase 2: LLM Wiki Agent (Karpathy 패턴)

raw/ 폴더의 AIAG/IATF/CSR 원본 문서를 읽어
wiki/ 폴더에 FMEA 작성에 활용 가능한 마크다운 요약본을 자동 생성·갱신.

실행:
  python wiki_agent.py --build          # 전체 빌드
  python wiki_agent.py --build --force  # 변경 여부 무관 전체 재생성
  python wiki_agent.py --list           # 생성된 wiki 페이지 목록

폴더 구조:
  backend/wiki/raw/   ← 원본 문서 (수정 금지) — PDF, Excel, txt, md
  backend/wiki/wiki/  ← 자동 생성 마크다운 (수정 금지)
  backend/wiki/.wiki_index.json ← 처리 이력 (파일 해시 기록)
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import anthropic

try:
    import fitz
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

WIKI_DIR = Path(__file__).parent
RAW_DIR = WIKI_DIR / "raw"
OUT_DIR = WIKI_DIR / "wiki"
INDEX_FILE = WIKI_DIR / ".wiki_index.json"

SUPPORTED_EXTS = {".pdf", ".txt", ".md", ".xlsx", ".xls"}

WIKI_SYSTEM_PROMPT = """너는 자동차 부품 FMEA 전문가이자 기술 문서 편집자다.
입력된 문서를 분석하여 PFMEA 작성 시 실제로 활용 가능한 마크다운 위키 페이지를 작성해라.
불필요한 서론 없이 핵심 내용만 간결하게 작성해라. 출력은 마크다운 형식만."""

WIKI_PROMPT_TEMPLATE = """다음 문서를 분석하여 PFMEA 작성 시 참고할 수 있는 위키 페이지를 작성해라.

문서 유형: {doc_type}
파일명: {filename}

문서 내용:
{content}

---

마크다운 위키 페이지 작성 요령:
1. 제목: # [문서명] 요약
2. 메타 정보: 원본 파일명, 생성일
3. **핵심 요약** — 3~5줄
4. **FMEA/PFMEA 관련 규칙·기준** — 번호 목록
5. **주요 용어·정의** — 표 또는 목록
6. **체크리스트** — FMEA 작성 시 확인 사항

문서 유형별 추가 섹션:
- AIAG/VDA 기준서: AP 판단 기준표, 심각도/발생도/검출도 기준
- CSR 문서: 고객사별 요구사항, 제출 서식, 특별특성 정의
- 사내 기준서: 작성 절차, 승인 프로세스
"""


def file_hash(path: Path) -> str:
    h = hashlib.md5()
    h.update(path.read_bytes())
    return h.hexdigest()


def load_index() -> dict:
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_index(index: dict):
    INDEX_FILE.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def read_pdf(path: Path) -> str:
    if not HAS_FITZ:
        return "(PyMuPDF 미설치)"
    doc = fitz.open(str(path))
    texts = [page.get_text() for page in doc]
    doc.close()
    return "\n".join(texts)[:8000]


def read_excel(path: Path) -> str:
    if not HAS_OPENPYXL:
        return "(openpyxl 미설치)"
    try:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        ws = wb.active
        rows = []
        for row in ws.iter_rows(min_row=1, max_row=40, values_only=True):
            if any(c is not None for c in row):
                rows.append(" | ".join(str(c) if c is not None else "" for c in row[:10]))
        wb.close()
        return "\n".join(rows)[:6000]
    except Exception as e:
        return f"(Excel 읽기 실패: {e})"


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:8000]
    except Exception as e:
        return f"(텍스트 읽기 실패: {e})"


def read_document(path: Path) -> tuple[str, str]:
    """(content, doc_type) 반환"""
    ext = path.suffix.lower()
    if ext == ".pdf":
        return read_pdf(path), "PDF 문서"
    elif ext in (".xlsx", ".xls"):
        return read_excel(path), "Excel 문서"
    else:
        return read_text(path), "텍스트/마크다운 문서"


def classify_doc_type(filename: str) -> str:
    name = filename.lower()
    if any(k in name for k in ["aiag", "vda", "fmea"]):
        return "AIAG/VDA FMEA 기준서"
    elif any(k in name for k in ["iatf", "16949", "iso"]):
        return "IATF/ISO 품질 기준서"
    elif any(k in name for k in ["csr", "현대", "기아", "gm", "르노", "고객"]):
        return "고객사 CSR (Customer Specific Requirements)"
    elif any(k in name for k in ["사내", "작성기준", "기준", "절차"]):
        return "사내 기준서"
    return "참고 문서"


def generate_wiki_page(
    client: anthropic.Anthropic,
    path: Path,
    content: str,
    doc_type: str,
) -> str:
    prompt = WIKI_PROMPT_TEMPLATE.format(
        doc_type=doc_type,
        filename=path.name,
        content=content,
    )

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=[{
            "type": "text",
            "text": WIKI_SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": prompt}],
        extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
    )

    page = msg.content[0].text.strip()

    # 메타 헤더 삽입
    meta = (
        f"\n\n---\n"
        f"*원본: `raw/{path.name}` | "
        f"자동 생성: {datetime.now().strftime('%Y-%m-%d %H:%M')} | "
        f"수정 금지 (wiki_agent.py가 관리)*\n"
    )
    return page + meta


def build_wiki(force: bool = False):
    if not RAW_DIR.exists():
        RAW_DIR.mkdir(parents=True)
        print(f"  raw/ 폴더 생성됨: {RAW_DIR}")
        print("  → raw/ 폴더에 AIAG/IATF/CSR 문서를 넣고 다시 실행하세요.")
        return

    raw_files = [f for f in RAW_DIR.iterdir() if f.suffix.lower() in SUPPORTED_EXTS]
    if not raw_files:
        print(f"  raw/ 폴더에 처리할 문서 없음 ({', '.join(SUPPORTED_EXTS)})")
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY") or input("Anthropic API 키: ").strip()
    if not api_key:
        sys.exit("오류: API 키 필요")
    client = anthropic.Anthropic(api_key=api_key)

    index = load_index()
    OUT_DIR.mkdir(exist_ok=True)

    print(f"[Wiki Agent] {len(raw_files)}개 문서 처리 시작")

    built = skipped = errors = 0
    for path in sorted(raw_files):
        fhash = file_hash(path)
        already_done = index.get(str(path.name), {}).get("hash") == fhash

        if already_done and not force:
            print(f"  [건너뜀] {path.name} (변경 없음)")
            skipped += 1
            continue

        print(f"  [처리중] {path.name} ...", end=" ", flush=True)
        try:
            content, raw_doc_type = read_document(path)
            doc_type = classify_doc_type(path.name) or raw_doc_type
            wiki_text = generate_wiki_page(client, path, content, doc_type)

            # 출력 파일명: 원본명_wiki.md
            out_name = re.sub(r"[^\w가-힣\-]", "_", path.stem) + "_wiki.md"
            out_path = OUT_DIR / out_name
            out_path.write_text(wiki_text, encoding="utf-8")

            index[str(path.name)] = {
                "hash": fhash,
                "wiki_file": out_name,
                "updated": datetime.now().isoformat(),
            }
            save_index(index)

            print(f"완료 → wiki/{out_name}")
            built += 1
        except Exception as e:
            print(f"오류: {e}")
            errors += 1

    print(f"\n  빌드 완료: {built}개 생성, {skipped}개 건너뜀, {errors}개 오류")
    print(f"  Wiki 위치: {OUT_DIR}")


def list_wiki():
    if not OUT_DIR.exists() or not list(OUT_DIR.glob("*.md")):
        print("  생성된 wiki 페이지 없음. --build 먼저 실행하세요.")
        return

    index = load_index()
    print(f"[Wiki Agent] 생성된 페이지 목록")
    for md_file in sorted(OUT_DIR.glob("*.md")):
        # 인덱스에서 원본 파일 찾기
        source = next(
            (k for k, v in index.items() if v.get("wiki_file") == md_file.name),
            "?"
        )
        updated = index.get(source, {}).get("updated", "?")[:10]
        size_kb = round(md_file.stat().st_size / 1024, 1)
        print(f"  {md_file.name:<50} ← raw/{source}  [{updated}] {size_kb}KB")


def main():
    parser = argparse.ArgumentParser(description="Phase 2 — LLM Wiki Agent")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--build", action="store_true", help="raw/ → wiki/ 빌드 (변경된 파일만)")
    group.add_argument("--list", action="store_true", help="생성된 wiki 페이지 목록")
    parser.add_argument("--force", action="store_true", help="변경 여부 무관 전체 재생성 (--build 와 함께)")
    args = parser.parse_args()

    if args.build:
        build_wiki(force=args.force)
    elif args.list:
        list_wiki()


if __name__ == "__main__":
    main()
