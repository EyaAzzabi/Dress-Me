from functools import lru_cache

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
    if not is_configured():
        return
    get_clothing_index().upsert(vectors=[{
        "id": str(item_id),
        "values": embedding.tolist() if hasattr(embedding, "tolist") else list(embedding),
        "metadata": {"owner_id": str(owner_id), "category": category},
    }])


def delete_item_embedding(item_id) -> None:
    if not is_configured():
        return
    get_clothing_index().delete(ids=[str(item_id)])


def find_similar_items(embedding, *, owner_id, top_k: int = 10, exclude_item_id=None) -> list[dict]:
    if not is_configured():
        return []

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


def fetch_embeddings(item_ids: list) -> dict[str, list[float]]:
    if not is_configured() or not item_ids:
        return {}

    response = get_clothing_index().fetch(ids=[str(i) for i in item_ids])
    return {item_id: vector.values for item_id, vector in response.vectors.items()}
