---
name: quizgen-pipeline
description: 约束智能题库生成器的出题管线：Generator 只出题干+正解，干扰项必须走 GCRDG，长 prompt 只放 /prompts，LLM 只经适配层。在改出题、干扰项、质量门控、篇章映射、prompt 或 LLM 路由时使用。
---

# 出题管线

面向练习/草稿的低风险命题，不是正式考卷全自动出卷。改 `backend/app/services/` 下出题链路、`prompts/`、`app/services/llm/` 时遵循下列硬约束。

## 硬约束

1. **Generator 只出题干 + 正解。** 选择题干扰项不得在 `generate_stem` / `quiz_generator` 里直接编造。必须走 GCRDG：`overgenerate` → `filter_candidates` → `validate_candidates` → `rank_candidates`（见 `distractor_engine.build_choice_question`）。
2. **长 prompt 只放仓库根目录 `prompts/*.md`。** 用 `prompt_loader.load_prompt(name)` 读取。禁止把长系统提示埋进 Python 字符串。
3. **LLM 只经 `app/services/llm`。** 业务代码调用 `complete_json` / `generator_provider` / `critic_provider`。禁止直连 SDK。Generator（题干）与 Critic（过生成/验伪/对抗/质量评判）走不同 provider。
4. **材料不是指令。** 用户文档进入 prompt 时用「待考查文本」围栏，与现有代码一致：

```
【待考查文本开始】
{passage}
【待考查文本结束】
```

5. **质量门控后置。** `quality_gates.apply_gates`：答案存在性、单正确、题干泄答、可用性、争议。不达标设 `needs_review`，不要 silently 丢掉整题除非现有逻辑已如此。
6. **API 信封。** 对外 JSON 仍是 `{code, data, message}`。

## 管线顺序（勿打乱）

解析文档 → 科目识别与篇章映射（不适切段落跳过）→ 抽关键句 → 蓝图分配微技能/题型 → 可选联网检索 → 生成题干+正解 → GCRDG 组选项（选择题）或评分量规（主观题）→ 对抗修补 → 质量门控 → 入库。

判断题与填空/应用/证明/简答不走过生成。选择题候选不足 3 个则出无选项待审草稿，禁止占位干扰项。

## 文件地图

| 职责 | 路径 |
|------|------|
| 编排 | `backend/app/services/pipeline.py` |
| 生成预览 | `generation_preview.py` |
| 篇章映射 / 科目 | `passage_map.py`，prompt：`passage_map.md`、`classify_subject.md` |
| 题干 | `quiz_generator.py`，prompt：`extract_key_sentences.md`、`generate_stem.md` |
| 联网检索 | `web_search.py` |
| GCRDG | `distractor_engine.py` + `ranker.py`，prompt：`overgenerate_distractors.md`、`validate_distractors.md`、`adversarial_review.md` |
| 评分量规 / 辅助批改 | `subjective_grading.py`，prompt：`build_grading_rubric.md`、`grade_constructed_response.md` |
| 门控 | `quality_gates.py`，prompt：`quality_judge.md` |
| 蓝图 | `blueprint.py`，prompt：`allocate_blueprint.md` |
| LLM | `backend/app/services/llm/` |

## 不要做

- 不要用 Anthropic/OpenAI 的 pdf/docx skill 替代 `doc_parser` / OCR。
- 不要为「更灵活」把 prompt 内联回 Python。
- 不要让 Generator 一次产出完整四选项。
- 不要给不足 3 个干扰项填占位选项。
