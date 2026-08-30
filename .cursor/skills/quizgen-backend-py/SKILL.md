---
name: quizgen-backend-py
description: 本仓库 FastAPI / SQLAlchemy 2 async / Alembic / ARQ 约定。在改 backend/app/、Alembic 迁移、worker、Redis 队列或对外 API 信封时使用。
---

# 后端约定

只写本仓库已有做法。出题管线硬约束见 `quizgen-pipeline`，这里不重复 GCRDG / 篇章映射。

## I/O 与会话

- 所有 I/O 用 `async`/`await`。CPU 或同步库（如 `hash_password`）用 `asyncio.to_thread`。
- DB：`AsyncSession` via `app.db.session.SessionLocal` / `get_db`。`expire_on_commit=False`。
- 本地 sqlite 与 Docker Postgres 两套 URL 都已存在；新查询保持 SQLAlchemy 2 async，不要写同步 `Session`。

## API 信封

对外 JSON 一律 `{code, data, message}`。成功用 `ok(...)`（`app.core.exceptions`）。失败抛 `AppError`，由 `app_error_handler` 转成同一形状。不要 `JSONResponse` 手写另一套字段。

```python
raise AppError("该邮箱已注册")
return ok({"token": token, "user": ...})
```

## LLM 与 prompt

- 业务代码只经 `app.services.llm`：`complete_json` / `generator_provider` / `critic_provider`。禁止直连 SDK。
- 长系统提示只放仓库根 `prompts/*.md`，用 `prompt_loader.load_prompt(name)`。

## 队列与缓存

- 出题任务走 ARQ：`app.core.arq.redis_settings` + `app.worker.generate_quiz_job`。
- Redis 客户端：`app.core.redis.get_redis()`（`redis.asyncio` 或 local `MemoryRedis`）。不要另开一套连接工厂。
- 改 Redis 键或连接时同时看官方 `redis-core` / `redis-connections`。

## 存储

对象存储只经 `app.services.storage`（MinIO / boto3）。不要在 API 层直接 `boto3.client`。

## Alembic

Postgres 路径改表结构用 `backend/alembic/versions/` 新版本，不要只改 sqlite 的 `create_all` 旁路。迁移与模型字段保持一致。
