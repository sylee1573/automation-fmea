"""
Phase 3: 한국어 임베딩 생성

모델: paraphrase-multilingual-MiniLM-L12-v2
  - 한국어 포함 50개 언어 지원
  - 무료, 로컬 실행 (최초 실행 시 ~90MB 자동 다운로드)
  - 벡터 차원: 384
  - 라이선스: Apache 2.0

싱글턴 패턴으로 모델을 한 번만 로드.
"""

from typing import Optional

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

_model: Optional[object] = None


def get_model():
    global _model
    if _model is None:
        import os
        from sentence_transformers import SentenceTransformer
        # 번들 배포 시 STANDARDS_MODEL_DIR 로 로컬 모델 경로를 지정하면 오프라인 로드.
        # 미설정이면 기존대로 이름으로 로드(온라인/캐시 폴백).
        local_dir = os.environ.get("STANDARDS_MODEL_DIR")
        source = local_dir if (local_dir and os.path.isdir(local_dir)) else MODEL_NAME
        print(f"  임베딩 모델 로드: {source}", flush=True)
        print("  (최초 실행 시 ~90MB 다운로드, 이후 캐시 사용)", flush=True)
        _model = SentenceTransformer(source)
    return _model


def embed_texts(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """텍스트 목록 → 임베딩 벡터 목록"""
    if not texts:
        return []
    model = get_model()
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=len(texts) > 50,
        convert_to_numpy=True,
        normalize_embeddings=True,  # cosine 유사도 계산 최적화
    )
    return embeddings.tolist()


def embed_query(query: str) -> list[float]:
    """단일 쿼리 문장 임베딩"""
    return embed_texts([query])[0]
