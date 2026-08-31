from __future__ import annotations

from app.services.llm.embed import cosine, embed_texts, thresholds_for


async def rank_candidates(
    candidates: list[dict],
    *,
    answer: str,
    stem: str,
    passage: str,
) -> list[dict]:
    if not candidates:
        return []
    texts = [answer, stem, passage[:500], *[str(cand.get("text") or "") for cand in candidates]]
    vectors, backend = await embed_texts(texts)
    th = thresholds_for(backend)
    ans_v, stem_v, pass_v = vectors[0], vectors[1], vectors[2]
    scored = []
    for cand, vec in zip(candidates, vectors[3:]):
        text = str(cand.get("text") or "")
        sim_ans = cosine(vec, ans_v)
        sim_stem = cosine(vec, stem_v)
        sim_pass = cosine(vec, pass_v)
        length_pen = abs(len(text) - len(answer)) / max(len(answer), 8)
        score = (
            sim_stem * 0.35
            + sim_pass * 0.35
            + (1 - abs(sim_ans - th.rank_target)) * 0.25
            - min(length_pen, 1) * 0.1
        )
        if sim_ans > th.rank_penalty:
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
