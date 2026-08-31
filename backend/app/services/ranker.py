from __future__ import annotations

from app.services.llm.embed import cosine, embed_texts, thresholds_for


def answer_texts(answer: str | list[str]) -> list[str]:
    raw = answer if isinstance(answer, list) else [answer]
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


async def rank_candidates(
    candidates: list[dict],
    *,
    answer: str | list[str],
    stem: str,
    passage: str,
) -> list[dict]:
    if not candidates:
        return []
    answers = answer_texts(answer) or [""]
    texts = [*answers, stem, passage[:500], *[str(cand.get("text") or "") for cand in candidates]]
    vectors, backend = await embed_texts(texts)
    th = thresholds_for(backend)
    n_answers = len(answers)
    ans_vecs = vectors[:n_answers]
    stem_v, pass_v = vectors[n_answers], vectors[n_answers + 1]
    scored = []
    for cand, vec in zip(candidates, vectors[n_answers + 2 :]):
        text = str(cand.get("text") or "")
        sim_ans = max(cosine(vec, ans_v) for ans_v in ans_vecs)
        sim_stem = cosine(vec, stem_v)
        sim_pass = cosine(vec, pass_v)
        length_pen = min(abs(len(text) - len(item)) / max(len(item), 8) for item in answers)
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
