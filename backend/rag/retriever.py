"""
Phase 3: FMEA 유사 사례 검색

공정유형 메타 필터 + 시맨틱 검색.
Agent가 FMEA 생성 시 유사 사례를 검색하는 인터페이스.

사용 예:
    results = search(
        query="드로잉 공정 스프링백 고장유형",
        customer_id="hyundai",
        process_type="드로잉",
        n_results=5,
    )
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from rag.vector_db import get_client, get_collection
from rag.embeddings import embed_query


def search(
    query: str,
    customer_id: str,
    n_results: int = 5,
    process_type: str = None,
    factory_type: str = None,
    quality_grade: str = None,
    db_path: str = None,
) -> list[dict]:
    """
    유사 FMEA 행 검색.

    Args:
        query:         검색 쿼리 (예: "피어싱 볼트홀 직경 불량")
        customer_id:   고객사 ID — 멀티테넌트 격리 (필수)
        n_results:     반환할 결과 수
        process_type:  공정 유형 필터 (예: "드로잉", "용접")
        factory_type:  공장 유형 필터 (예: "프레스공장")
        quality_grade: 품질 등급 필터 ("A" 만 검색 등)
        db_path:       Chroma DB 경로 (기본: data/chroma)

    Returns:
        [{"document": str, "metadata": dict, "similarity": float}, ...]
        similarity: 0.0(최하) ~ 1.0(최고), 0.7 이상이면 유사 사례로 활용 가능
    """
    client = get_client(db_path)

    try:
        collection = get_collection(client, customer_id, create=False)
    except Exception:
        return []

    if collection.count() == 0:
        return []

    # 메타 필터 구성
    where_clauses = []
    if process_type:
        where_clauses.append({"process_type": {"$eq": process_type}})
    if factory_type:
        where_clauses.append({"factory_type": {"$eq": factory_type}})
    if quality_grade:
        where_clauses.append({"quality_grade": {"$eq": quality_grade}})

    where = None
    if len(where_clauses) == 1:
        where = where_clauses[0]
    elif len(where_clauses) > 1:
        where = {"$and": where_clauses}

    query_vec = embed_query(query)

    results = collection.query(
        query_embeddings=[query_vec],
        n_results=min(n_results, collection.count()),
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    output = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        output.append({
            "document": doc,
            "metadata": meta,
            "similarity": round(1.0 - dist, 4),
        })

    # 유사도 내림차순 정렬
    output.sort(key=lambda x: x["similarity"], reverse=True)
    return output


def format_for_prompt(results: list[dict], max_results: int = 3) -> str:
    """검색 결과를 프롬프트 주입용 텍스트로 변환"""
    if not results:
        return "(유사 사례 없음)"

    lines = ["## 유사 사례 (Vector DB 검색 결과)\n"]
    for i, r in enumerate(results[:max_results], 1):
        sim_pct = int(r["similarity"] * 100)
        meta = r["metadata"]
        lines.append(
            f"### 유사 사례 {i} (유사도 {sim_pct}%)\n"
            f"- 출처: {Path(meta.get('file_path', '')).name} "
            f"({meta.get('factory_type', '')} / {meta.get('process_type', '')})\n"
            f"- 내용: {r['document']}\n"
        )
    return "\n".join(lines)
