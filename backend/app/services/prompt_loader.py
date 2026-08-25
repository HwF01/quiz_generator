import os
from functools import lru_cache
from pathlib import Path

_env_prompts = os.environ.get("QUIZGEN_PROMPTS")
PROMPT_DIRS = [
    Path("/app/prompts"),
    Path(__file__).resolve().parents[3] / "prompts",
    Path.cwd() / "prompts",
]
if _env_prompts:
    PROMPT_DIRS.insert(0, Path(_env_prompts))


@lru_cache
def load_prompt(name: str) -> str:
    filename = name if name.endswith(".md") else f"{name}.md"
    for folder in PROMPT_DIRS:
        path = folder / filename
        if path.exists():
            return path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"prompt not found: {filename}")
