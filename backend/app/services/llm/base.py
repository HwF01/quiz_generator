from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class ChatMessage:
    role: str
    content: str


class ChatProvider(Protocol):
    name: str
    model: str

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.6,
        json_mode: bool = True,
        max_tokens: int = 2048,
    ) -> str: ...
