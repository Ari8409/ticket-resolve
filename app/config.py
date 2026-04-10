from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    OPENAI_API_KEY: str = "sk-placeholder"
    LLM_MODEL: str = "gpt-4o"

    # Embedding backend — "sentence_transformers" (local) or "openai" (API)
    EMBEDDING_BACKEND: str = "sentence_transformers"

    # sentence-transformers settings (used when EMBEDDING_BACKEND=sentence_transformers)
    ST_MODEL:  str = "all-MiniLM-L6-v2"   # 384-dim, fast, no GPU required
    ST_DEVICE: str = "cpu"                  # "cpu" | "cuda" | "mps"

    # OpenAI embedding settings (used when EMBEDDING_BACKEND=openai)
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # Chroma
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8001
    TICKET_COLLECTION: str = "tickets"
    SOP_COLLECTION: str = "sops"
    CHROMA_DISTANCE_FUNCTION: str = "cosine"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/tickets.db"

    # Ingestion
    WEBHOOK_SECRET: str = "changeme"
    MAX_FILE_SIZE_MB: int = 10

    # App
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    SIMILARITY_TOP_K: int = 5
    SOP_TOP_K: int = 3
    SIMILARITY_SCORE_THRESHOLD: float = 0.75

    # Alarm subsystem
    ALARM_RETENTION_DAYS: int = 30          # Purge cleared alarms older than N days
    ALARM_CLEARED_HOLD_MINUTES: int = 30    # How long after clear before auto-closing ticket

    # Maintenance subsystem
    MAINTENANCE_LOOKAHEAD_HOURS: int = 4    # Window ahead of ticket timestamp to check for maintenance
    MAINTENANCE_LOOKBACK_HOURS: int = 1     # Window behind ticket timestamp (covers just-ended windows)

    # Correlation engine
    CORRELATION_SIMILAR_K: int = 5          # Similar tickets fetched during correlation
    CORRELATION_SOP_K: int = 3              # SOPs fetched during correlation

    # Embedding pipeline
    EMBEDDING_PIPELINE_TOP_K: int = 3           # Resolved matches returned per ticket
    EMBEDDING_PIPELINE_THRESHOLD: float = 0.0   # Minimum cosine similarity (0 = return all)


@lru_cache
def get_settings() -> Settings:
    return Settings()
