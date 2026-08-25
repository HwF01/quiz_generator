from __future__ import annotations

from app.core.config import settings
from app.services.llm.base import ChatMessage, ChatProvider
from app.services.llm.providers import AnthropicProvider, MockProvider, OpenAICompatibleProvider

WENKE = {"civics", "history", "exam_civil", "exam_grad", "general"}
LIKE = {"it", "math", "logic"}


def generator_provider(subject: str) -> ChatProvider:
    if settings.use_mock_llm:
        return MockProvider()
    if subject in LIKE and settings.deepseek_api_key:
        return OpenAICompatibleProvider(
            settings.deepseek_api_key,
            settings.deepseek_base_url,
            settings.deepseek_model,
            "deepseek",
        )
    if settings.qwen_api_key:
        return OpenAICompatibleProvider(
            settings.qwen_api_key,
            settings.qwen_base_url,
            settings.qwen_model,
            "qwen",
        )
    if settings.deepseek_api_key:
        return OpenAICompatibleProvider(
            settings.deepseek_api_key,
            settings.deepseek_base_url,
            settings.deepseek_model,
            "deepseek",
        )
    if settings.openai_api_key:
        return OpenAICompatibleProvider(
            settings.openai_api_key,
            "https://api.openai.com/v1",
            settings.openai_model,
            "openai",
        )
    return MockProvider()


def critic_provider() -> ChatProvider:
    if settings.use_mock_llm:
        return MockProvider()
    if settings.anthropic_api_key:
        return AnthropicProvider()
    if settings.openai_api_key:
        return OpenAICompatibleProvider(
            settings.openai_api_key,
            "https://api.openai.com/v1",
            settings.openai_model,
            "openai",
        )
    if settings.qwen_api_key:
        return OpenAICompatibleProvider(
            settings.qwen_api_key,
            settings.qwen_base_url,
            settings.qwen_model,
            "qwen",
        )
    return MockProvider()


async def complete_json(
    provider: ChatProvider,
    system: str,
    user: str,
    *,
    temperature: float = 0.6,
) -> str:
    return await provider.complete(
        [
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content=user),
        ],
        temperature=temperature,
        json_mode=True,
    )
