from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_PLACEHOLDER_SECRETS = frozenset({"change-me-in-production", "change-me"})
_LOCAL_ENVS = frozenset({"development", "local", "dev", "desktop"})
_SINGLE_NODE_ENVS = frozenset({"local", "desktop", "dev"})
_BACKEND_ROOT = Path(__file__).resolve().parents[2]

_CONFIG_FILES: tuple[str, ...] = tuple(
    p
    for p in (os.environ.get("QUIZGEN_CONFIG"), ".env", "../.env")
    if p
)


def default_desktop_data_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
        return base / "QuizGen"
    return Path.home() / ".local" / "share" / "quizgen"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_CONFIG_FILES, env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "智能题库生成器"
    app_env: str = "development"
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 60 * 24 * 7
    daily_gen_quota: int = 20

    database_url: str = "sqlite+aiosqlite:///./quizgen.db"
    redis_url: str = "redis://localhost:6379/0"
    quizgen_data_dir: str = ""

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "quiz-docs"
    minio_secure: bool = False

    frontend_url: str = "http://localhost:3000"

    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen-plus"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    embedding_provider: str = "local"
    embedding_model: str = "hashed-bigram"
    tavily_api_key: str = ""
    tavily_max_results: int = 5

    mock_llm: bool = False
    enable_ocr: bool = True
    max_upload_mb: int = 20
    max_key_sentences: int = 50
    max_questions: int = 50

    @property
    def is_local_stack(self) -> bool:
        env = (self.app_env or "").lower()
        return env in _SINGLE_NODE_ENVS or "sqlite" in (self.database_url or "")

    @property
    def allow_storage_failure(self) -> bool:
        return (self.app_env or "").lower() in _LOCAL_ENVS

    @property
    def use_memory_redis(self) -> bool:
        url = (self.redis_url or "").strip().lower()
        scheme = url.split(":", 1)[0]
        return scheme in {"", "memory"}

    @property
    def data_dir(self) -> Path:
        return Path(self.quizgen_data_dir)

    @property
    def has_llm_key(self) -> bool:
        return any(
            [
                self.qwen_api_key,
                self.deepseek_api_key,
                self.anthropic_api_key,
                self.openai_api_key,
            ]
        )

    @property
    def web_search_available(self) -> bool:
        return bool(self.tavily_api_key)

    @property
    def use_mock_llm(self) -> bool:
        # Only explicit MOCK_LLM=true forces mock. Keys + MOCK_LLM=false use live models.
        if self.mock_llm:
            return True
        return not self.has_llm_key

    @property
    def llm_mode(self) -> str:
        return "mock" if self.use_mock_llm else "live"

    @model_validator(mode="after")
    def _resolve_paths_and_secrets(self) -> Self:
        env = (self.app_env or "").lower()
        if self.quizgen_data_dir:
            data = Path(self.quizgen_data_dir)
        elif env == "desktop":
            data = default_desktop_data_dir()
        else:
            data = _BACKEND_ROOT
        data.mkdir(parents=True, exist_ok=True)
        object.__setattr__(self, "quizgen_data_dir", str(data.resolve()))

        if self.database_url.startswith("sqlite") and ":///" in self.database_url:
            prefix, _, rest = self.database_url.partition(":///")
            db_path = Path(rest)
            if rest and not db_path.is_absolute():
                resolved = (data / db_path.name).resolve()
                object.__setattr__(
                    self,
                    "database_url",
                    f"{prefix}:///{resolved.as_posix()}",
                )

        if env not in _LOCAL_ENVS and self.secret_key in _PLACEHOLDER_SECRETS:
            raise RuntimeError(
                "APP_ENV 非 development/local/desktop 时必须设置非占位 SECRET_KEY / secret_key"
            )
        return self


settings = Settings()
