from functools import lru_cache
import json
from pathlib import Path
from typing import Any
import numpy as np

from app.core.config import get_settings

EMBEDDING_SIZE = 512  # CLIP ViT-B/32 image embedding size


def _import_pinecone():
    try:
        from pinecone import Pinecone, ServerlessSpec
        return Pinecone, ServerlessSpec
    except ImportError:
        return None, None


@lru_cache
def get_vector_client():
    settings = get_settings()
    Pinecone, _ = _import_pinecone()
    if Pinecone is None:
        return None
    return Pinecone(api_key=settings.pinecone_api_key)


def ensure_index() -> None:
    settings = get_settings()
    _, ServerlessSpec = _import_pinecone()
    client = get_vector_client()
    if client is None:
        return
    existing = {index.name for index in client.list_indexes()}
    if settings.pinecone_index_name not in existing:
        client.create_index(
            name=settings.pinecone_index_name,
            dimension=EMBEDDING_SIZE,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )


def get_clothing_index():
    client = get_vector_client()
    if client is None:
        return None
    return client.Index(get_settings().pinecone_index_name)


def is_configured() -> bool:
    """False in a prototype deployment without a Pinecone key — callers (Vision/
    Purchase/Recommendation agents) degrade gracefully instead of crashing."""
    Pinecone, _ = _import_pinecone()
    if Pinecone is None:
        return False
    return bool(get_settings().pinecone_api_key)


def upsert_item_embedding(item_id, embedding, *, owner_id, category: str) -> None:
    vec = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
    _save_local_embedding(str(item_id), vec, str(owner_id), category)
    if not is_configured():
        return
    get_clothing_index().upsert(vectors=[{
        "id": str(item_id),
        "values": vec,
        "metadata": {"owner_id": str(owner_id), "category": category},
    }])


def delete_item_embedding(item_id) -> None:
    _delete_local_embedding(str(item_id))
    if not is_configured():
        return
    get_clothing_index().delete(ids=[str(item_id)])


def find_similar_items(embedding, *, owner_id, top_k: int = 10, exclude_item_id=None) -> list[dict]:
    if not is_configured():
        return _query_local_embeddings(embedding, str(owner_id), top_k, exclude_item_id)

    vector = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
    response = get_clothing_index().query(
        vector=vector,
        top_k=top_k,
        filter={"owner_id": {"$eq": str(owner_id)}},
        include_metadata=True,
    )
    matches = [
        {"item_id": m.id, "score": m.score, "category": (m.metadata or {}).get("category")}
        for m in response.matches
    ]
    if exclude_item_id is not None:
        matches = [m for m in matches if m["item_id"] != str(exclude_item_id)]
    return matches


def fetch_embeddings(item_ids: list) -> dict[Any, list[float]]:
    if not item_ids:
        return {}
    results = {}
    if is_configured():
        try:
            response = get_clothing_index().fetch(ids=[str(i) for i in item_ids])
            for k, v in response.vectors.items():
                results[k] = v.values
        except Exception:
            pass

    # Complete any missing items from local embedding store
    local_data = _load_local_store()
    for i in item_ids:
        sid = str(i)
        if sid not in results and sid in local_data:
            results[sid] = local_data[sid]["values"]
            results[i] = local_data[sid]["values"]
        elif sid in results:
            results[i] = results[sid]
    return results


# --- Local embedding store fallback (JSON/Disk) for offline/dev/testing ---
import json
from pathlib import Path
from typing import Any
import numpy as np

_LOCAL_STORE_PATH = Path(__file__).resolve().parent.parent.parent / "uploads" / "local_vectors.json"


def _load_local_store() -> dict:
    if not _LOCAL_STORE_PATH.exists():
        return {}
    try:
        with open(_LOCAL_STORE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_local_embedding(item_id: str, values: list[float], owner_id: str, category: str):
    store = _load_local_store()
    store[item_id] = {"values": values, "owner_id": owner_id, "category": category}
    _LOCAL_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_LOCAL_STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(store, f)


def _delete_local_embedding(item_id: str):
    store = _load_local_store()
    if item_id in store:
        del store[item_id]
        with open(_LOCAL_STORE_PATH, "w", encoding="utf-8") as f:
            json.dump(store, f)


def _query_local_embeddings(embedding, owner_id: str, top_k: int = 10, exclude_item_id=None) -> list[dict]:
    store = _load_local_store()
    vec = np.array(embedding, dtype=np.float32)
    norm_v = np.linalg.norm(vec)
    if norm_v > 0:
        vec = vec / norm_v

    matches = []
    for item_id, data in store.items():
        if data.get("owner_id") != owner_id:
            continue
        if exclude_item_id and item_id == str(exclude_item_id):
            continue
        cand_vec = np.array(data["values"], dtype=np.float32)
        norm_c = np.linalg.norm(cand_vec)
        if norm_c > 0:
            cand_vec = cand_vec / norm_c
        score = float(np.dot(vec, cand_vec))
        matches.append({"item_id": item_id, "score": score, "category": data.get("category")})

    matches.sort(key=lambda m: m["score"], reverse=True)
    return matches[:top_k]

