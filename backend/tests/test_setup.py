from pathlib import Path

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.core.setup_config import apply_setup_update, setup_status, upsert_env_values
from tests.conftest import register


@pytest.fixture
def restore_settings():
    snapshot = {
        "app_env": settings.app_env,
        "qwen_api_key": settings.qwen_api_key,
        "deepseek_api_key": settings.deepseek_api_key,
        "openai_api_key": settings.openai_api_key,
        "anthropic_api_key": settings.anthropic_api_key,
        "tavily_api_key": settings.tavily_api_key,
        "mock_llm": settings.mock_llm,
    }
    yield
    for key, value in snapshot.items():
        object.__setattr__(settings, key, value)


def test_setup_status_never_includes_secrets(restore_settings):
    object.__setattr__(settings, "qwen_api_key", "sk-secret-qwen")
    object.__setattr__(settings, "deepseek_api_key", "sk-secret-ds")
    object.__setattr__(settings, "tavily_api_key", "tv-secret")
    data = setup_status()
    dumped = str(data)
    assert "sk-secret" not in dumped
    assert "tv-secret" not in dumped
    assert data["qwen_configured"] is True
    assert data["deepseek_configured"] is True
    assert data["tavily_configured"] is True
    assert "qwen_api_key" not in data


def test_setup_status_self_review_when_single_live_key(restore_settings):
    object.__setattr__(settings, "mock_llm", False)
    object.__setattr__(settings, "qwen_api_key", "sk-qwen")
    object.__setattr__(settings, "deepseek_api_key", "")
    object.__setattr__(settings, "openai_api_key", "")
    object.__setattr__(settings, "anthropic_api_key", "")
    data = setup_status()
    assert data["llm_mode"] == "live"
    assert data["self_review"] is True
    object.__setattr__(settings, "deepseek_api_key", "sk-ds")
    assert setup_status()["self_review"] is False


def test_upsert_env_values_preserves_other_keys(tmp_path):
    path = tmp_path / "config.env"
    path.write_text("SECRET_KEY=keep\nQWEN_API_KEY=old\n", encoding="utf-8")
    upsert_env_values(path, {"QWEN_API_KEY": "new", "TAVILY_API_KEY": "tv"})
    text = path.read_text(encoding="utf-8")
    assert "SECRET_KEY=keep" in text
    assert "QWEN_API_KEY=new" in text
    assert "TAVILY_API_KEY=tv" in text


async def test_get_setup_is_public(client: AsyncClient):
    res = await client.get("/api/setup")
    assert res.status_code == 200
    body = res.json()
    assert body["code"] == 0
    data = body["data"]
    assert set(data) == {
        "llm_mode",
        "qwen_configured",
        "deepseek_configured",
        "tavily_configured",
        "editable",
        "self_review",
    }
    assert "api_key" not in str(data).lower()


async def test_put_setup_requires_login(client: AsyncClient):
    res = await client.put("/api/setup", json={"qwen_api_key": "sk-x"})
    assert res.status_code == 401


async def test_put_setup_readonly_without_config_file(client: AsyncClient, restore_settings):
    object.__setattr__(settings, "app_env", "production")
    data = await register(client, "setup-ro@example.com")
    res = await client.put(
        "/api/setup",
        json={"qwen_api_key": "sk-x"},
        headers={"Authorization": f"Bearer {data['token']}"},
    )
    assert res.status_code == 403
    assert "服务器配置" in res.json()["message"]


async def test_put_setup_writes_keys_and_hot_reloads(
    client: AsyncClient, tmp_path, monkeypatch, restore_settings
):
    cfg = tmp_path / "config.env"
    cfg.write_text("MOCK_LLM=true\n", encoding="utf-8")
    monkeypatch.setenv("QUIZGEN_CONFIG", str(cfg))
    object.__setattr__(settings, "app_env", "local")
    object.__setattr__(settings, "qwen_api_key", "")
    object.__setattr__(settings, "deepseek_api_key", "")
    object.__setattr__(settings, "tavily_api_key", "")
    object.__setattr__(settings, "mock_llm", True)

    data = await register(client, "setup-rw@example.com")
    headers = {"Authorization": f"Bearer {data['token']}"}
    res = await client.put(
        "/api/setup",
        json={"qwen_api_key": "sk-qwen", "deepseek_api_key": "sk-ds", "tavily_api_key": "tv-1"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()["data"]
    assert body["llm_mode"] == "live"
    assert body["qwen_configured"] is True
    assert body["deepseek_configured"] is True
    assert body["tavily_configured"] is True
    assert body["self_review"] is False
    assert body["editable"] is True
    assert "sk-qwen" not in res.text
    assert settings.web_search_available is True

    text = Path(cfg).read_text(encoding="utf-8")
    assert "QWEN_API_KEY=sk-qwen" in text
    assert "DEEPSEEK_API_KEY=sk-ds" in text
    assert "TAVILY_API_KEY=tv-1" in text
    assert "MOCK_LLM=false" in text

    kept = await client.put("/api/setup", json={}, headers=headers)
    assert kept.status_code == 200
    assert settings.qwen_api_key == "sk-qwen"

    demo = await client.put("/api/setup", json={"use_demo": True}, headers=headers)
    assert demo.json()["data"]["llm_mode"] == "mock"
    assert demo.json()["data"]["self_review"] is False
    assert settings.qwen_api_key == "sk-qwen"

    live = await client.put("/api/setup", json={"use_demo": False}, headers=headers)
    assert live.json()["data"]["llm_mode"] == "live"

    cleared = await client.put("/api/setup", json={"clear_tavily": True}, headers=headers)
    assert cleared.json()["data"]["tavily_configured"] is False
    assert settings.web_search_available is False


def test_apply_setup_update_empty_keeps_existing(tmp_path, monkeypatch, restore_settings):
    cfg = tmp_path / "config.env"
    monkeypatch.setenv("QUIZGEN_CONFIG", str(cfg))
    object.__setattr__(settings, "app_env", "desktop")
    object.__setattr__(settings, "qwen_api_key", "keep-qwen")
    object.__setattr__(settings, "deepseek_api_key", "")
    object.__setattr__(settings, "openai_api_key", "")
    object.__setattr__(settings, "anthropic_api_key", "")
    object.__setattr__(settings, "tavily_api_key", "")
    object.__setattr__(settings, "mock_llm", False)
    status = apply_setup_update(qwen_api_key="  ", deepseek_api_key="new-ds")
    assert settings.qwen_api_key == "keep-qwen"
    assert settings.deepseek_api_key == "new-ds"
    assert status["llm_mode"] == "live"
    assert status["self_review"] is False
