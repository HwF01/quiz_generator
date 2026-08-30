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
- 后端（Agent 自选）：`quizgen-backend-py`；Redis 官方 `redis-core`、`redis-connections`（仓库内 `.cursor/skills/`）。不要装 Cursor 市场的 `redis-development`：市场源路径写成了不存在的 `skills/redis-development`，会 ENOENT。

文档查询用全局 Context7 MCP（按需），不要整包装 Cloudflare / OpenAI / Anthropic 文档 skill。本机 Docker Postgres 只读 MCP 在 `.cursor/mcp.json`。

不要把 Obra Superpowers 与上述 Matt 工作流同时作为默认流程。
