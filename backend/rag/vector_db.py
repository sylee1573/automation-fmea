"""
Phase 3: Chroma Vector DB 클라이언트

고객사별 collection 완전 격리 (멀티테넌트).
Collection 이름: fmea_{customer_id}
저장 위치: data/chroma/ (로컬 영구 저장)
"""

from pathlib import Path
import chromadb

DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "chroma"


def get_client(db_path: str = None) -> chromadb.ClientAPI:
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(path))


def get_collection(client: chromadb.ClientAPI, customer_id: str, create: bool = True):
    """고객사별 collection 반환. create=False면 없을 경우 예외 발생."""
    name = _collection_name(customer_id)
    if create:
        return client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )
    return client.get_collection(name=name)


def list_collections(client: chromadb.ClientAPI) -> list[str]:
    return [c.name for c in client.list_collections()]


def collection_stats(collection) -> dict:
    return {
        "name": collection.name,
        "count": collection.count(),
    }


def delete_collection(client: chromadb.ClientAPI, customer_id: str):
    client.delete_collection(_collection_name(customer_id))


def _collection_name(customer_id: str) -> str:
    # Chroma collection 이름 규칙: 소문자, 숫자, 하이픈만 허용
    safe = customer_id.lower().replace(" ", "_").replace("/", "_")
    return f"fmea_{safe}"
