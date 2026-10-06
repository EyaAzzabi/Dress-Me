from functools import lru_cache

from pinecone import Pinecone, ServerlessSpec

from app.core.config import get_settings

EMBEDDING_SIZE = 512  # CLIP ViT-B/32 image embedding size


@lru_cache
def get_vector_client() -> Pinecone:
    settings = get_settings()
    return Pinecone(api_key=settings.pinecone_api_key)


def ensure_index() -> None:
    settings = get_settings()
    client = get_vector_client()
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
    return client.Index(get_settings().pinecone_index_name)


def is_configured() -> bool:
    """False in a prototype deployment without a Pinecone key — callers (Vision/
    Purchase/Recommendation agents) degrade gracefully instead of crashing."""
    return bool(get_settings().pinecone_api_key)


def upsert_item_embedding(item_id, embedding, *, owner_id, category: str) -> None:
    """Stores one wardrobe item's embedding, keyed by its own ClothingItem.id (so a
    similarity match can be mapped straight back to a row, no separate id to track).
    `owner_id` is stored as metadata so a similarity query can be scoped to one user's
    wardrobe without an index-wide scan. No-ops without a configured Pinecone key."""
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
    """Nearest wardrobe items (by cosine similarity) belonging to `owner_id`. Returns
    [] if Pinecone isn't configured or the wardrobe has nothing indexed yet — both are
    normal, not errors."""
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
    """Batch-fetches stored vectors by ClothingItem.id — used by the Recommendation
    Agent to score outfit candidates without re-running FashionCLIP on every wardrobe
    photo. Items with no stored embedding (Pinecone wasn't configured when they were
    added) are simply absent from the returned dict, not an error."""
    if not is_configured() or not item_ids:
        return {}

    response = get_clothing_index().fetch(ids=[str(i) for i in item_ids])
    return {item_id: vector.values for item_id, vector in response.vectors.items()}
