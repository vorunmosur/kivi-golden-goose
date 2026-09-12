from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class Settings:
    db_path: str = field(default_factory=lambda: os.getenv("KIVI_DB_PATH", "./kivi.db"))
    # Generic provider key first; OPENAI_API_KEY remains a compatibility fallback.
    api_key: str | None = field(default_factory=lambda: os.getenv("KIVI_LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or None)
    llm_model: str = field(default_factory=lambda: os.getenv("KIVI_LLM_MODEL", "gpt-5-mini"))
    embedding_model: str = field(default_factory=lambda: os.getenv("KIVI_EMBEDDING_MODEL", "text-embedding-3-small"))
    base_url: str = field(default_factory=lambda: os.getenv("KIVI_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"))
    demo_mode: bool = field(default_factory=lambda: _env_bool("KIVI_DEMO_MODE", "true"))
    max_retries: int = field(default_factory=lambda: max(0, int(os.getenv("KIVI_LLM_MAX_RETRIES", "3"))))
    retry_base_seconds: float = field(default_factory=lambda: max(0.0, float(os.getenv("KIVI_LLM_RETRY_BASE_SECONDS", "0.6"))))


settings = Settings()
