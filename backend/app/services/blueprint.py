from __future__ import annotations

from app.schemas.quiz import QuizBlueprint

SKILL_DIFFICULTY = {
    "detail": "easy",
    "gist": "medium",
    "cohesion": "medium",
    "inference": "hard",
    "theme": "hard",
    "attitude": "medium",
}

TYPES = ["single_choice", "true_false"]
SKILLS_CYCLE = ["gist", "inference", "theme", "detail", "attitude", "cohesion"]


def allocate(n_items: int, blueprint: QuizBlueprint) -> list[dict]:
    if n_items <= 0:
        return []
    n = blueprint.total_questions
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
        allocs.append(
            {
                "index": i,
                "type": type_seq[i] if type_seq[i] in TYPES else "single_choice",
                "micro_skill": skill,
                "difficulty": SKILL_DIFFICULTY.get(skill, "medium"),
                "cognitive_level": "understand" if skill != "detail" else "remember",
            }
        )
    return allocs


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
        q["difficulty"] = SKILL_DIFFICULTY["inference"]
        q["cognitive_level"] = "understand"
    return others + kept_details + overflow
