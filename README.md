# 智能题库生成器

AI 辅助低风险命题（练习 / 草稿），不是高风险考试全自动出卷。

## 最终用户（Windows）

不需要安装 Python、Node、Redis、Postgres 或 Docker。

1. 安装 `QuizGen-Setup.exe`（或解压 `QuizGen-portable.zip`）
2. 打开「智能题库生成器」快捷方式，按向导选择演示模式或填写自己的大模型 API Key
3. 浏览器会打开 http://127.0.0.1:3000 ；托盘图标可退出

安装器采用当前用户安装，不需要管理员权限；程序位于 `%LOCALAPPDATA%\Programs\QuizGen`，数据与配置在 `%APPDATA%\QuizGen`。真实出题需要你自己的通义千问或 DeepSeek Key（安装包不预置密钥）。

构建安装包见 [packaging/README.md](packaging/README.md)。未签名安装包可能被 SmartScreen 拦截，选择「仍要运行」即可。

## 需要安装的软件与配置

做完安装包后，**最终用户只看「安装后」列**。

| 软件 / 配置 | 本机开发（现在） | 安装包用户 |
| --- | --- | --- |
| Windows 10/11 x64 | 是 | 是 |
| Python 3.12 | 必装 | 内嵌，不用装 |
| Node.js 20 | 必装 | 内嵌，不用装 |
| Redis | 可选：`REDIS_URL=memory://` 则不需要 | 不需要（进程内缓存） |
| PostgreSQL | 不需要（用 SQLite） | 不需要 |
| MinIO | 不需要（本地 uploads） | 不需要 |
| ARQ worker | 不需要（进程内出题） | 不需要 |
| Tesseract OCR（`chi_sim`+`eng`） | 扫描件才需要 | 默认关，安装器可选组件 |
| Docker Desktop | 仅全栈编排时 | 不需要 |
| `APP_ENV` | `local` | `desktop` |
| `DATABASE_URL` | `sqlite+aiosqlite:///./quizgen.db` | 指向用户数据目录 |
| `REDIS_URL` | `memory://` 或本机 Redis | `memory://` |
| `SECRET_KEY` | local 可用占位 | 安装时随机生成 |
| `MOCK_LLM` / LLM Key | 无 Key 则 mock | 向导里选演示或自备 Key |
| MinIO 一组变量 | Docker 用 | 忽略 |

开发者不要用 Docker 版 `DATABASE_URL=...@postgres` 去跑本机 SQLite 路径。密钥只放本机 `.env` / `config.env`，不要提交。

## 本机开发（SQLite，无需 Redis）

一条命令（会打开前后端两个窗口）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
```

或手动：

```bash
# backend
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
# 建议：APP_ENV=local，DATABASE_URL=sqlite+aiosqlite:///./quizgen.db，REDIS_URL=memory://
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# frontend
cd frontend
npm install
npm run dev
```

- SQLite 启动时 `create_all` + seed，**不跑 Alembic**
- `APP_ENV=local` / `desktop` 时出题走 `asyncio.create_task`，不依赖 ARQ worker
- `REDIS_URL=memory://`（或留空 scheme 为 memory）使用进程内缓存，**不必再装 Redis**
- `MOCK_LLM=true` 才强制 mock；有 Key 且 `MOCK_LLM=false` 走真模型

## Docker / Postgres

开发编排（映射 5432/6379/9000，backend `--reload`）：

```bash
cp .env.example .env
docker compose up --build
```

生产编排（不映射数据端口，backend 无 reload，前端 standalone）：

```bash
cp .env.example .env
# 在 .env 中设置随机且非占位的 SECRET_KEY 后再启动：
# python -c "import secrets; print(secrets.token_urlsafe(32))"
docker compose -f docker-compose.prod.yml up --build
```

Postgres 路径用 Alembic：`alembic upgrade head`（含 `002_fk_jsonb`）。

## 已核对的配置缺口

| 项 | 说明 |
| --- | --- |
| 本机 SQLite vs Docker Alembic | 本机 `create_all` 吃 ORM `ondelete`；Docker/Postgres 必须跑 002 |
| 配额与 Redis | 真实 Redis 仍 fail-closed（挂了会 503）；`memory://` 视为可用，重启后当日配额重置 |
| `SECRET_KEY` | 非 development/local/desktop 且仍是占位则拒绝启动 |
| Embedding | 名称 `hashed-bigram`，不是真实 bge |
| JWT | 仍是 Bearer + localStorage；middleware 只用 `quiz_auth` 存在性 cookie |
| 健康检查 | `/health` 会 `SELECT 1` + Redis `PING`（内存实现恒成功） |

## 测试

```bash
cd backend
pytest -q
```

前端类型检查：`cd frontend && npm run lint`（`tsc --noEmit`）。
