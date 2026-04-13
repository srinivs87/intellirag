from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # ── LLM ──────────────────────────────────────────────────────────────────
    LLM_PROVIDER: str = "groq"                      # "groq" | "ollama"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # ── Ollama (local fallback) ───────────────────────────────────────────────
    OLLAMA_HOST: str = "ollama"
    OLLAMA_PORT: int = 11434
    OLLAMA_MODEL: str = "llama3.2"
    EMBED_MODEL: str = "nomic-embed-text"

    # ── Vector store ─────────────────────────────────────────────────────────
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://intellirag:intellirag_secret@postgres:5432/intellirag"

    # ── MinIO ────────────────────────────────────────────────────────────────
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "intellirag"
    MINIO_SECRET_KEY: str = "intellirag_secret"
    MINIO_BUCKET: str = "intellirag-docs"
    MINIO_SECURE: bool = False

    # ── Security ─────────────────────────────────────────────────────────────
    SECRET_KEY: str = "change-me-in-production-32chars!!"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # ── CORS ─────────────────────────────────────────────────────────────────
    CORS_ORIGINS: str = "*"

    # ── RAG tuning ───────────────────────────────────────────────────────────
    CHUNK_SIZE: int = 400
    CHUNK_OVERLAP: int = 50
    TOP_K: int = 5
    HYBRID_ALPHA: float = 0.7

    @property
    def cors_origins_list(self) -> List[str]:
        if self.CORS_ORIGINS == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
