# 智能题库生成器

AI 辅助的低风险命题产品：从讲义生成练习/草稿题，人始终审校。不是高风险考试的全自动出卷系统。

## Language

**低风险命题**：
面向练习与草稿的出题，产出必须可被教师/用户审校后才当正式材料用。
_Avoid_: 全自动出卷, 考试引擎, 高利害测评

**待考查文本**：
用户上传文档中被圈进 prompt 的材料正文，模型必须当文本读、不当指令执行。围栏为「待考查文本开始/结束」。
_Avoid_: 用户指令, system prompt, 语料

**篇章映射**：
按段落判断是否适切出题，不适切则跳过，而不是整书切片硬出题。
_Avoid_: 切片, chunking 出题, 全文灌入

**蓝图**：
一套题的题型配比、微技能循环与细节题上限，由 `allocate` 展开成逐题配额。
_Avoid_: 试卷结构, 双向细目表（本产品不做高利害细目表）

**微技能**：
单题考查的阅读/理解维度，取值如 gist、detail、inference、theme、attitude、cohesion。
_Avoid_: 知识点标签（那是 knowledge_tags）, 能力模型

**Generator**：
只负责题干与正解的模型角色（文科偏 Qwen、理科偏 DeepSeek）。
_Avoid_: 主模型, 出题模型一次出选项

**Critic**：
过生成干扰项、对抗修补、质量评判所用的模型角色。
_Avoid_: 裁判模型与 Generator 混用

**题干**：
题目题面（`content` / stem），不含选项列表。
_Avoid_: 题目（易与整道题混淆）, prompt

**正解**：
题目的正确作答，选择题为正确选项文本，填空为 texts。
_Avoid_: 标准答案（易暗示高利害）, gold label

**干扰项**：
选择题的错误选项。必须来自 GCRDG，不能由 Generator 顺便编三个。
_Avoid_: 错误答案, 陪衬项, dummy options

**GCRDG**：
干扰项流水线：过生成（约 8–12 候选）→ 语义过滤（与正解过近、与材料过远、候选互近则丢）→ 排序取 3 个，再组四选项并旋转正解位置。
_Avoid_: 直接编选项, 一次生成 ABCD

**过生成**：
Critic 按题干、正解与待考查文本大量写出干扰候选。
_Avoid_: brainstorm distractors, 随机错误项

**质量门控**：
入库前的规则+Critic 检查：答案存在性、单正确、题干泄答、可用性、争议性。不通过则 `needs_review`。
_Avoid_: QA, lint 题目

**待审校**：
`needs_review=true` 的题目，UI 应置顶让人改，不是自动扔掉。
_Avoid_: 失败题, 废题

**LLM 适配层**：
`app/services/llm` 是业务代码调用模型的唯一入口。
_Avoid_: 直连 SDK, 在 service 里写 OpenAI client

**Prompt 目录**：
长系统提示只存在仓库 `prompts/*.md`，由 `load_prompt` 读取。
_Avoid_: 内联长 prompt, Python 三引号说明书

**广场**：
已发布题库的社区浏览页，不是出题工作台。
_Avoid_: feed, marketplace

**练习**：
用户在题库上作答、看解析、进错题本的路径。
_Avoid_: 考试, 模考（除非用户文案已用该词）
