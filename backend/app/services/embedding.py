from typing import List
import asyncio
import ollama
from app.core.config import settings


async def get_embeddings(texts: List[str]) -> List[List[float]]:
    """Generate embeddings using local Ollama (nomic-embed-text)."""
    embeddings = []
    loop = asyncio.get_event_loop()
    for text in texts:
        response = await loop.run_in_executor(
            None,
            lambda t=text: ollama.embeddings(
                model=settings.EMBED_MODEL,
                prompt=t,
            )
        )
        embeddings.append(response["embedding"])
    return embeddings


async def get_embedding(text: str) -> List[float]:
    """Generate a single embedding."""
    result = await get_embeddings([text])
    return result[0]
