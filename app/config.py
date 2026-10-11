"""All runtime configuration comes from environment variables (12-factor). See .env.example."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # --- LLM (any OpenAI-compatible endpoint: Ollama, Groq, Gemini, OpenRouter, ...) ---
    llm_base_url: str = "http://localhost:11434/v1"  # local Ollama by default ($0)
    llm_api_key: str = "ollama"
    llm_model: str = "qwen3.5:4b"
    llm_timeout_s: float = 120.0
    llm_reasoning_effort: str | None = "none"  # Ollama: disables slow "thinking"; unset for providers without it
    llm_cache: bool = False  # cache responses on disk (evals: deterministic and free to re-run)
    llm_max_rpm: int = 0  # e.g. 8 for a free tier allowing 10 requests/minute; 0 = unlimited
    llm_price_per_mtok_in: float = 0.0
    llm_price_per_mtok_out: float = 0.0
    judge_base_url: str | None = None  # defaults to the generator endpoint
    judge_api_key: str | None = None
    judge_model: str | None = None
    judge_budget_usd: float = 5.0
    judge_price_per_mtok_in: float = 0.0  # set for paid judges so the spend cap works
    judge_price_per_mtok_out: float = 0.0

    # --- retrieval ---
    qdrant_url: str | None = None  # None -> embedded local Qdrant under .cache/qdrant
    embed_model: str = "BAAI/bge-small-en-v1.5"
    rerank_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    enable_rerank: bool = True
    retrieve_k: int = 20
    context_k: int = 5

    # --- agent ---
    enable_healing: bool = True
    max_retries: int = 2
    max_unresolved_turns: int = 3

    # --- observability ---
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"
    online_eval_sample_rate: float = 0.1

    # --- api ---
    demo_token: str | None = None  # if set, requests must send X-Demo-Token
    rate_limit_per_min: int = 20
    database_url: str = f"sqlite:///{ROOT / '.cache' / 'app.db'}"

    app_env: str = "dev"  # dev | ci | prod
    app_release: str = "dev"  # set to the git SHA by the container build

    cache_dir: Path = ROOT / ".cache"


@lru_cache
def get_settings() -> Settings:
    return Settings()
