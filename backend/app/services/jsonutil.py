from __future__ import annotations

import json
import re


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _strip_trailing_commas(text: str) -> str:
    return re.sub(r",(\s*[}\]])", r"\1", text)


def _loads(text: str) -> dict | list:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(_strip_trailing_commas(text))


def parse_json(text: str) -> dict | list:
    text = _strip_fences(text)
    try:
        return _loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}|\[.*\]", text, re.S)
        if match:
            return _loads(match.group(0))
        raise
