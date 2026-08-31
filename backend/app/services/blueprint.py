from __future__ import annotations

from collections import Counter

from app.schemas.quiz import QUESTION_TYPES, SUBJECT_TAGS, QuizBlueprint

SKILL_DIFFICULTY = {
    "detail": "easy",
    "gist": "medium",
    "cohesion": "medium",
    "inference": "hard",
    "theme": "hard",
    "attitude": "medium",
}

TYPES = ["single_choice", "multi_choice", "true_false"]
SKILLS_CYCLE = ["gist", "inference", "theme", "detail", "attitude", "cohesion"]
_COMMON_TYPES = ("single_choice", "multi_choice", "true_false")
_TYPE_PRIORITY = {
    "single_choice": 6,
    "multi_choice": 3,
    "true_false": 4,
    "fill_blank": 5,
    "application": 5,
    "proof": 4,
    "short_answer": 5,
}
_SUBJECT_TAG_ALIASES = {
    "it": {"it", "engineering"},
    "math": {"math", "science"},
    "logic": {"logic"},
    "civics": {"humanities"},
    "history": {"humanities"},
    "exam_civil": {"humanities"},
    "exam_grad": {"humanities"},
}
_TYPE_ALIASES = {
    "单选": "single_choice",
    "多选": "multi_choice",
    "判断": "true_false",
    "填空": "fill_blank",
    "应用": "application",
    "证明": "proof",
    "简答": "short_answer",
}


def subject_tags_for(subject: str, overrides: list[str] | None = None) -> list[str]:
    tags = {tag for tag in (overrides or []) if tag in SUBJECT_TAGS}
    tags.update(_SUBJECT_TAG_ALIASES.get(subject, set()))
    return sorted(tags)


def allowed_question_types(subject_tags: list[str]) -> list[str]:
    tags = set(subject_tags)
    result = list(_COMMON_TYPES)
    if tags & {"science", "engineering"}:
        result.extend(["fill_blank", "application"])
    if "math" in tags:
        result.append("proof")
    if "humanities" in tags:
        result.extend(["fill_blank", "short_answer"])
    return list(dict.fromkeys(result))


def validate_type_counts(type_counts: dict[str, int], subject_tags: list[str]) -> None:
    invalid = set(type_counts) - QUESTION_TYPES
    if invalid:
        raise ValueError(f"不支持的题型：{', '.join(sorted(invalid))}")
    allowed = set(allowed_question_types(subject_tags))
    unsupported = {kind for kind, count in type_counts.items() if count > 0 and kind not in allowed}
    if unsupported:
        raise ValueError(f"当前学科不支持题型：{', '.join(sorted(unsupported))}")


def allocate(
    n_items: int,
    blueprint: QuizBlueprint,
    *,
    subject_tags: list[str] | None = None,
    suggested_types: list[str] | None = None,
) -> list[dict]:
    if n_items <= 0:
        return []
    n = min(n_items, blueprint.total_questions)
    resolved_tags = list(dict.fromkeys(subject_tags or blueprint.subject_tags))
    allowed_types = allowed_question_types(resolved_tags) if resolved_tags else TYPES
    if blueprint.allocation_mode == "manual":
        validate_type_counts(blueprint.type_counts, resolved_tags)
        type_seq = _sequence_from_counts(blueprint.type_counts, n)
    elif resolved_tags:
        type_seq = _auto_type_sequence(n, allowed_types, suggested_types or [])
    else:
        type_seq = _weighted_seq(blueprint.type_mix, n, TYPES, "single_choice")
    skills = []
    detail_budget = int(n * blueprint.max_detail_ratio)
    detail_used = 0
    for i in range(n):
        skill = SKILLS_CYCLE[i % len(SKILLS_CYCLE)]
        if skill == "detail":
            if detail_used >= detail_budget:
                skill = "inference"
            else:
                detail_used += 1
        skills.append(skill)
    allocs = []
    for i in range(n):
        skill = skills[i]
        kind = type_seq[i] if type_seq[i] in allowed_types else "single_choice"
        difficulty = blueprint.target_difficulty or SKILL_DIFFICULTY.get(skill, "medium")
        allocs.append(
            {
                "index": i,
                "type": kind,
                "micro_skill": skill,
                "difficulty": difficulty,
                "target_difficulty": blueprint.target_difficulty,
                "cognitive_level": _cognitive_level(kind, skill),
            }
        )
    return allocs


def _cognitive_level(kind: str, skill: str) -> str:
    if kind == "application":
        return "apply"
    if kind == "proof":
        return "analyze"
    if kind == "short_answer":
        return "understand"
    return "understand" if skill != "detail" else "remember"


def _sequence_from_counts(type_counts: dict[str, int], n: int) -> list[str]:
    sequence: list[str] = []
    for kind, count in type_counts.items():
        sequence.extend([kind] * count)
    return sequence[:n]


def _auto_type_sequence(n: int, allowed: list[str], suggested_types: list[str]) -> list[str]:
    if not allowed:
        return ["single_choice"] * n
    normalized_suggestions = [
        _TYPE_ALIASES.get(str(kind).strip(), str(kind).strip())
        for kind in suggested_types
        if _TYPE_ALIASES.get(str(kind).strip(), str(kind).strip()) in allowed
    ]
    suggestions = Counter(normalized_suggestions)
    candidates = [
        kind
        for kind in allowed
        if kind in _COMMON_TYPES or kind in suggestions
    ] or list(_COMMON_TYPES)
    weights = {kind: _TYPE_PRIORITY.get(kind, 1) + suggestions[kind] * 4 for kind in candidates}
    ranked = sorted(candidates, key=lambda kind: (-weights[kind], kind))
    active = ranked[: min(n, len(ranked))]
    counts = {kind: 1 for kind in active}
    remaining = n - len(active)
    if remaining:
        total_weight = sum(weights[kind] for kind in active)
        fractions = []
        for kind in active:
            ideal = remaining * weights[kind] / total_weight
            whole = int(ideal)
            counts[kind] += whole
            fractions.append((ideal - whole, kind))
        for _, kind in sorted(fractions, key=lambda item: (-item[0], item[1]))[: remaining - sum(
            counts[kind] - 1 for kind in active
        )]:
            counts[kind] += 1
    return _sequence_from_counts(counts, n)


def _weighted_seq(mix: dict[str, float], n: int, allowed: list[str], default: str) -> list[str]:
    counts = []
    remaining = n
    items = [(k, mix.get(k, 0)) for k in allowed if mix.get(k, 0) > 0]
    if not items:
        return [default] * n
    total = sum(w for _, w in items) or 1
    for i, (k, w) in enumerate(items):
        c = int(round(n * w / total))
        if i == len(items) - 1:
            c = remaining
        remaining -= c
        counts.extend([k] * max(c, 0))
    if len(counts) < n:
        counts.extend([default] * (n - len(counts)))
    return counts[:n]


def enforce_detail_cap(questions: list[dict], max_ratio: float) -> list[dict]:
    if not questions:
        return questions
    cap = max(1, int(len(questions) * max_ratio))
    details = [q for q in questions if q.get("micro_skill") == "detail"]
    others = [q for q in questions if q.get("micro_skill") != "detail"]
    if len(details) <= cap:
        return questions
    ranked = sorted(
        details, key=lambda q: (q.get("quality_scores") or {}).get("usability", 0), reverse=True
    )
    kept_details = ranked[:cap]
    overflow = ranked[cap:]
    for q in overflow:
        q["micro_skill"] = "inference"
        if not q.get("target_difficulty"):
            q["difficulty"] = SKILL_DIFFICULTY["inference"]
        q["cognitive_level"] = "understand"
    return others + kept_details + overflow
