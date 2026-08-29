# 智能题库生成器 — Agent 入口

项目法在 `.cursorrules`。行为底线在 `.cursor/rules/karpathy-zh.mdc`。对用户与计划用中文。

## Agent skills

### Issue tracker

议题写在本地 `.scratch/`，不使用 GitHub Issues。见 `docs/agents/issue-tracker.md`。

### Domain docs

单一上下文：根目录 `CONTEXT.md` + `docs/adr/`。见 `docs/agents/domain.md`。

### 本仓库装了哪些 skill

- 工作流（按需 `/`）：`grill-with-docs`、`tdd`、`diagnosing-bugs`、`implement`、`code-review`；依赖 `grilling`、`domain-modeling`、`setup-matt-pocock-skills`
- 前端（Agent 自选）：`react-best-practices`、`web-design-guidelines`
- 领域（中文）：`quizgen-pipeline`、`quizgen-ui-zh`

不要把 Obra Superpowers 与上述 Matt 工作流同时作为默认流程。
