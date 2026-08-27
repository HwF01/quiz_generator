UNNAMED_PREFIX = "未命名题库"


def is_unnamed_title(title: str) -> bool:
    text = (title or "").strip()
    return text == "" or text == UNNAMED_PREFIX


def next_unnamed_title(existing: list[str]) -> str:
    used = set(existing)
    n = 1
    while f"{UNNAMED_PREFIX}{n}" in used:
        n += 1
    return f"{UNNAMED_PREFIX}{n}"


def with_duplicate_suffix(desired: str, existing: list[str]) -> str:
    text = desired.strip()
    if text not in existing:
        return text
    n = 1
    while f"{text}({n})" in existing:
        n += 1
    return f"{text}({n})"


def uniquify_title(desired: str, existing: list[str]) -> str:
    text = (desired or "").strip()
    if is_unnamed_title(text):
        return next_unnamed_title(existing)
    return with_duplicate_suffix(text, existing)
