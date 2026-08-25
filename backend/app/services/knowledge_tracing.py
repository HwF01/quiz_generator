from __future__ import annotations

# Simple Bayesian Knowledge Tracing per micro-skill.
# P(L0)=0.2, P(T)=0.15, P(G)=0.2, P(S)=0.1


def update_mastery(p_l: float, correct: bool) -> float:
    p_t, p_g, p_s = 0.15, 0.2, 0.1
    if correct:
        numer = p_l * (1 - p_s)
        denom = numer + (1 - p_l) * p_g
    else:
        numer = p_l * p_s
        denom = numer + (1 - p_l) * (1 - p_g)
    p_l_obs = numer / denom if denom else p_l
    return p_l_obs + (1 - p_l_obs) * p_t


def recommend_difficulty(mastery: dict[str, float], micro_skill: str) -> str:
    p = mastery.get(micro_skill, 0.35)
    if p < 0.4:
        return "easy"
    if p < 0.7:
        return "medium"
    return "hard"


def apply_play(mastery: dict[str, float], skill_results: dict[str, bool]) -> dict[str, float]:
    out = dict(mastery)
    for skill, ok in skill_results.items():
        out[skill] = update_mastery(out.get(skill, 0.2), bool(ok))
    return out
