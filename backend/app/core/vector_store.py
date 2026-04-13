from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams
from app.core.config import settings

_client: AsyncQdrantClient = None

VECTOR_SIZE = 768  # nomic-embed-text output dimension


def get_qdrant() -> AsyncQdrantClient:
    return _client


async def init_vector_store():
    global _client
    _client = AsyncQdrantClient(
        host=settings.QDRANT_HOST,
        port=settings.QDRANT_PORT,
    )
    print(f"[VectorStore] Connected to Qdrant at {settings.QDRANT_HOST}:{settings.QDRANT_PORT}")


async def ensure_collection(tenant_slug: str):
    """Create a Qdrant collection for a tenant if it doesn't exist."""
    collection_name = f"intellirag_{tenant_slug}"
    existing = await _client.get_collections()
    names = [c.name for c in existing.collections]

    if collection_name not in names:
        await _client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=VECTOR_SIZE,
                distance=Distance.COSINE,
            ),
        )
        print(f"[VectorStore] Created collection: {collection_name}")

    return collection_name
