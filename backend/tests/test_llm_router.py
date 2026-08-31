from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.llm.router import (
    SELF_REVIEW_TEMP_DELTA,
    assign_roles,
    complete_json,
    critic_provider,
    generator_provider,
    is_self_review_config,
)

_SETTING_KEYS = (
    "mock_llm",
    "qwen_api_key",
    "qwen_model",
    "deepseek_api_key",
    "deepseek_model",
    "openai_api_key",
    "openai_model",
    "anthropic_api_key",
    "anthropic_model",
)


@pytest.fixture
def live_llm():
    snapshot = {key: getattr(settings, key) for key in _SETTING_KEYS}
    object.__setattr__(settings, "mock_llm", False)
    object.__setattr__(settings, "qwen_api_key", "")
    object.__setattr__(settings, "deepseek_api_key", "")
    object.__setattr__(settings, "openai_api_key", "")
    object.__setattr__(settings, "anthropic_api_key", "")
    object.__setattr__(settings, "qwen_model", "qwen-plus")
    object.__setattr__(settings, "deepseek_model", "deepseek-chat")
    object.__setattr__(settings, "openai_model", "gpt-4o-mini")
    object.__setattr__(settings, "anthropic_model", "claude-sonnet-4-5")
    yield

    for key, value in snapshot.items():
        object.__setattr__(settings, key, value)


def _set_keys(*, qwen: str = "", deepseek: str = "", openai: str = "", anthropic: str = "") -> None:
    object.__setattr__(settings, "qwen_api_key", qwen)
    object.__setattr__(settings, "deepseek_api_key", deepseek)
    object.__setattr__(settings, "openai_api_key", openai)
    object.__setattr__(settings, "anthropic_api_key", anthropic)


def test_qwen_only_civics_uses_sibling_model_and_self_review(live_llm):
    _set_keys(qwen="sk-qwen")
    roles = assign_roles("civics")
    assert roles.generator.name == "qwen"
    assert roles.generator.model == "qwen-plus"
    assert roles.critic.name == "qwen"
    assert roles.critic.model == "qwen-turbo"
    assert roles.critic.model != roles.generator.model
    assert roles.self_review is True
    assert getattr(roles.critic, "temperature_delta", 0) == 0.0
    assert is_self_review_config() is True


def test_deepseek_only_science_self_reviews_with_temperature_delta(live_llm):
    _set_keys(deepseek="sk-ds")
    roles = assign_roles("it")
    assert roles.generator.name == "deepseek"
    assert roles.critic.name == "deepseek"
    assert roles.critic.name != "mock"
    assert roles.critic.model == "deepseek-chat"
    assert roles.self_review is True
    assert getattr(roles.critic, "temperature_delta", 0) == SELF_REVIEW_TEMP_DELTA
    assert critic_provider("it").name == "deepseek"


def test_qwen_and_deepseek_cross_by_subject(live_llm):
    _set_keys(qwen="sk-qwen", deepseek="sk-ds")
    liberal = assign_roles("civics")
    assert liberal.generator.name == "qwen"
    assert liberal.critic.name == "deepseek"
    assert liberal.self_review is False

    science = assign_roles("it")
    assert science.generator.name == "deepseek"
    assert science.critic.name == "qwen"
    assert science.self_review is False
    assert is_self_review_config() is False


def test_qwen_and_anthropic_critic_is_claude(live_llm):
    _set_keys(qwen="sk-qwen", anthropic="sk-ant")
    roles = assign_roles("civics")
    assert roles.generator.name == "qwen"
    assert roles.critic.name == "claude"
    assert roles.self_review is False
    assert critic_provider("civics").name == "claude"


def test_anthropic_only_is_not_self_review(live_llm):
    _set_keys(anthropic="sk-ant")
    roles = assign_roles("civics")
    assert roles.generator.name == "mock"
    assert roles.critic.name == "claude"
    assert roles.self_review is False
    assert is_self_review_config() is False


def test_mock_roles_are_not_self_review(live_llm):
    object.__setattr__(settings, "mock_llm", True)
    _set_keys(qwen="sk-qwen")
    roles = assign_roles("civics")
    assert generator_provider("civics").name == "mock"
    assert critic_provider("civics").name == "mock"
    assert roles.self_review is False
    assert is_self_review_config() is False


class _RecordingProvider:
    name = "rec"
    model = "m"
    temperature_delta = SELF_REVIEW_TEMP_DELTA
    last_temperature: float | None = None

    async def complete(self, messages, *, temperature=0.6, json_mode=True, max_tokens=2048):
        self.last_temperature = temperature
        return "{}"


@pytest.mark.asyncio
async def test_complete_json_applies_temperature_delta():
    provider = _RecordingProvider()
    await complete_json(provider, "sys", "user", temperature=0.1)
    assert provider.last_temperature == pytest.approx(0.25)


@pytest.mark.asyncio
async def test_complete_json_clamps_temperature_to_one():
    provider = _RecordingProvider()
    await complete_json(provider, "sys", "user", temperature=0.95)
    assert provider.last_temperature == pytest.approx(1.0)
