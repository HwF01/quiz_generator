from __future__ import annotations

from app.services.llm.embed import similarity


def rank_candidates(
    candidates: list[dict],
    *,
    answer: str,
    stem: str,
    passage: str,
) -> list[dict]:
    scored = []
    for cand in candidates:
        text = str(cand.get("text") or "")
        sim_ans = similarity(text, answer)
        sim_stem = similarity(text, stem)
        sim_pass = similarity(text, passage[:500])
        length_pen = abs(len(text) - len(answer)) / max(len(answer), 8)
        # prefer mid-distance from answer, related to stem/passage
        score = (
            sim_stem * 0.35
            + sim_pass * 0.35
            + (1 - abs(sim_ans - 0.45)) * 0.25
            - min(length_pen, 1) * 0.1
        )
        if sim_ans > 0.82:
            score -= 1
        scored.append((score, cand))
    scored.sort(key=lambda x: x[0], reverse=True)
    ranked = [c for _, c in scored]
    diverse: list[dict] = []
    seen_error_types: set[str] = set()
    for candidate in ranked:
        error_type = str(candidate.get("error_type") or "")
        if error_type and error_type in seen_error_types:
            continue
        diverse.append(candidate)
        if error_type:
            seen_error_types.add(error_type)
    diverse.extend(candidate for candidate in ranked if candidate not in diverse)
    return diverse
