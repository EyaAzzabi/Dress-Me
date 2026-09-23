from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams

from app.core.config import get_settings

CLOTHING_COLLECTION = "clothing_embeddings"
EMBEDDING_SIZE = 512  # CLIP ViT-B/32 image embedding size


@lru_cache
def get_vector_client() -> QdrantClient:
    settings = get_settings()
    return QdrantClient(url=settings.qdrant_url)


def ensure_collections() -> None:
    client = get_vector_client()
    existing = {c.name for c in client.get_collections().collections}
    if CLOTHING_COLLECTION not in existing:
        client.create_collection(
            collection_name=CLOTHING_COLLECTION,
            vectors_config=VectorParams(size=EMBEDDING_SIZE, distance=Distance.COSINE),
        )
