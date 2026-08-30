from __future__ import annotations

import os
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import AppError

_EDITABLE_ENVS = frozenset({"desktop", "local"})


def setup_config_path() -> Path | None:
    raw = os.environ.get("QUIZGEN_CONFIG")
    if not raw:
        return None
    return Path(raw)


def is_setup_editable() -> bool:
    env = (settings.app_env or "").lower()
    return env in _EDITABLE_ENVS and setup_config_path() is not None


def setup_status() -> dict:
    return {
        "llm_mode": settings.llm_mode,
        "qwen_configured": bool(settings.qwen_api_key),
        "deepseek_configured": bool(settings.deepseek_api_key),
        "tavily_configured": bool(settings.tavily_api_key),
        "editable": is_setup_editable(),
    }


def upsert_env_values(path: Path, updates: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, _, _ = stripped.partition("=")
            key = key.strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        out.append(line)
    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def apply_setup_update(
    *,
    qwen_api_key: str | None = None,
    deepseek_api_key: str | None = None,
    tavily_api_key: str | None = None,
    use_demo: bool = False,
    clear_tavily: bool = False,
) -> dict:
    if not is_setup_editable():
        raise AppError("当前环境请在服务器配置中修改密钥", code=403, status_code=403)
    path = setup_config_path()
    if path is None:
        raise AppError("当前环境请在服务器配置中修改密钥", code=403, status_code=403)

    qwen = (qwen_api_key or "").strip() or settings.qwen_api_key
    deepseek = (deepseek_api_key or "").strip() or settings.deepseek_api_key
    tavily = settings.tavily_api_key
    if clear_tavily:
        tavily = ""
    elif (tavily_api_key or "").strip():
        tavily = tavily_api_key.strip()

    provided_generator = bool((qwen_api_key or "").strip() or (deepseek_api_key or "").strip())
    if provided_generator:
        mock_llm = False
    elif use_demo or not (qwen or deepseek):
        mock_llm = True
    else:
        mock_llm = False

    env_updates = {
        "QWEN_API_KEY": qwen,
        "DEEPSEEK_API_KEY": deepseek,
        "TAVILY_API_KEY": tavily,
        "MOCK_LLM": "true" if mock_llm else "false",
    }
    upsert_env_values(path, env_updates)
    object.__setattr__(settings, "qwen_api_key", qwen)
    object.__setattr__(settings, "deepseek_api_key", deepseek)
    object.__setattr__(settings, "tavily_api_key", tavily)
    object.__setattr__(settings, "mock_llm", mock_llm)
    return setup_status()
