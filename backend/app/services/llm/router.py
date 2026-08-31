from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.services.llm.base import ChatMessage, ChatProvider
from app.services.llm.providers import AnthropicProvider, MockProvider, OpenAICompatibleProvider

WENKE = {"civics", "history", "exam_civil", "exam_grad", "general"}
LIKE = {"it", "math", "logic"}

SELF_REVIEW_TEMP_DELTA = 0.15
_CRITIC_VENDOR_ORDER = ("claude", "openai", "qwen", "deepseek")
_CRITIC_MODEL_SIBLING: dict[str, dict[str, str]] = {
    "qwen": {
        "qwen-plus": "qwen-turbo",
        "qwen-turbo": "qwen-plus",
        "qwen-max": "qwen-plus",
        "qwen-flash": "qwen-plus",
    },
    "openai": {
        "gpt-4o": "gpt-4o-mini",
    },
    "claude": {
        "claude-sonnet-4-5": "claude-haiku-4-5",
        "claude-haiku-4-5": "claude-sonnet-4-5",
    },
}


@dataclass
class RoleAssignment:
    generator: ChatProvider
    critic: ChatProvider
    self_review: bool


def _configured_vendors() -> set[str]:
    vendors: set[str] = set()
    if settings.qwen_api_key:
        vendors.add("qwen")
    if settings.deepseek_api_key:
        vendors.add("deepseek")
    if settings.openai_api_key:
        vendors.add("openai")
    if settings.anthropic_api_key:
        vendors.add("claude")
    return vendors


def is_self_review_config() -> bool:
    if settings.use_mock_llm:
        return False
    return len(_configured_vendors()) < 2


def _make_provider(
    vendor: str,
    *,
    model: str | None = None,
    temperature_delta: float = 0.0,
) -> ChatProvider:
    if vendor == "qwen":
        return OpenAICompatibleProvider(
            settings.qwen_api_key,
            settings.qwen_base_url,
            model or settings.qwen_model,
            "qwen",
            temperature_delta=temperature_delta,
        )
    if vendor == "deepseek":
        return OpenAICompatibleProvider(
            settings.deepseek_api_key,
            settings.deepseek_base_url,
            model or settings.deepseek_model,
            "deepseek",
            temperature_delta=temperature_delta,
        )
    if vendor == "openai":
        return OpenAICompatibleProvider(
            settings.openai_api_key,
            "https://api.openai.com/v1",
            model or settings.openai_model,
            "openai",
            temperature_delta=temperature_delta,
        )
    if vendor == "claude":
        return AnthropicProvider(model=model, temperature_delta=temperature_delta)
    return MockProvider()


def _generator_vendor(subject: str, vendors: set[str]) -> str | None:
    if subject in LIKE and "deepseek" in vendors:
        return "deepseek"
    if "qwen" in vendors:
        return "qwen"
    if "deepseek" in vendors:
        return "deepseek"
    if "openai" in vendors:
        return "openai"
    return None


def _critic_vendor(generator_vendor: str | None, vendors: set[str]) -> str | None:
    for name in _CRITIC_VENDOR_ORDER:
        if name in vendors and name != generator_vendor:
            return name
    if generator_vendor in vendors:
        return generator_vendor
    return None


def _self_review_model(vendor: str, generator_model: str) -> tuple[str, float]:
    sibling = _CRITIC_MODEL_SIBLING.get(vendor, {}).get(generator_model)
    if sibling and sibling != generator_model:
        return sibling, 0.0
    return generator_model, SELF_REVIEW_TEMP_DELTA


def assign_roles(subject: str) -> RoleAssignment:
    if settings.use_mock_llm:
        return RoleAssignment(generator=MockProvider(), critic=MockProvider(), self_review=False)
    vendors = _configured_vendors()
    gen_vendor = _generator_vendor(subject, vendors)
    if not gen_vendor:
        cri_vendor = _critic_vendor(None, vendors)
        return RoleAssignment(
            generator=MockProvider(),
            critic=_make_provider(cri_vendor) if cri_vendor else MockProvider(),
            self_review=False,
        )
    gen = _make_provider(gen_vendor)
    cri_vendor = _critic_vendor(gen_vendor, vendors)
    if cri_vendor and cri_vendor != gen_vendor:
        return RoleAssignment(
            generator=gen,
            critic=_make_provider(cri_vendor),
            self_review=False,
        )
    gen_model = str(getattr(gen, "model", "") or "")
    critic_model, delta = _self_review_model(gen_vendor, gen_model)
    return RoleAssignment(
        generator=gen,
        critic=_make_provider(gen_vendor, model=critic_model, temperature_delta=delta),
        self_review=True,
    )


def generator_provider(subject: str) -> ChatProvider:
    return assign_roles(subject).generator


def critic_provider(subject: str = "general") -> ChatProvider:
    return assign_roles(subject).critic


async def complete_json(
    provider: ChatProvider,
    system: str,
    user: str,
    *,
    temperature: float = 0.6,
) -> str:
    delta = float(getattr(provider, "temperature_delta", 0) or 0)
    return await provider.complete(
        [
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content=user),
        ],
        temperature=min(1.0, max(0.0, temperature + delta)),
        json_mode=True,
    )
