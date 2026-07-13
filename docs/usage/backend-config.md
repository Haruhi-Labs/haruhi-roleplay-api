# 后端配置

## 文档定位

本文是后端配置的最小入口。单模型、单 embedding、单 RAG 场景只需要阅读本文，不需要理解 `MODEL_PROVIDER_REGISTRY`。

- Docker Compose 启动见 `docker-compose.md`。
- 所有高级字段和装配关系见 `backend-dispatch-and-configuration.md`。
- 管理页面和 `.env` 写回规则见 `config-panel.md`。
- 前端请求字段见 `interface-reference.md`。

## 当前可用能力

| 能力 | 已实现 |
| --- | --- |
| HTTP | `/health`、persona、chat、SSE、session 创建、RAG、memory、配置和 Access Token API |
| LLM | fake、Ollama、OpenAI、OpenAI-compatible、DeepSeek、Gemini |
| RAG | fake、本地文本、本地向量、Chroma、Faiss、Qdrant |
| Embedding | hash、Ollama、OpenAI、OpenAI-compatible |
| Session | memory、SQLite、PostgreSQL |
| Memory | memory、SQLite |
| Agent | deterministic planner；model-backed planner 只有配置入口，尚未实现 |
| 部署 | 本地 Python 和单容器 Docker Compose |

## 最快启动

### 本地 fake 闭环

复制模板：

```powershell
Copy-Item .env.example .env
```

确认 `.env` 至少包含：

```env
ROLEPLAY_HOST=127.0.0.1
ROLEPLAY_PORT=8000
ROLEPLAY_API_KEY=change-me-local-admin-key
ROLEPLAY_CORS_ORIGINS=

LLM_API_TYPE=fake
LLM_MODEL=fake-roleplay-model

RAG_API_TYPE=local

SESSION_PROVIDER=sqlite
SESSION_SQLITE_PATH=.data/sessions.sqlite3
MEMORY_PROVIDER=sqlite
MEMORY_SQLITE_PATH=.data/memories.sqlite3
```

启动：

```powershell
$env:PYTHONPATH="src"
uv run python -m haruhi_roleplay_api.infrastructure.http_server
```

当前 `pyproject.toml` 设置了 `tool.uv.package=false`，本地源码不会自动安装进虚拟环境，因此直接从仓库运行时需要把 `src` 加入模块搜索路径。Dockerfile 已在容器内设置该路径。

服务地址：

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/demo
http://127.0.0.1:8000/config
```

### Docker Compose

```bash
cp .env.compose.example .env
docker compose up -d --build
```

Compose 只启动本服务，不额外启动模型、Qdrant 或 PostgreSQL。

## 简单 Provider 配置

单 provider 配置采用同一种心智模型：选择 API type，再填写地址、模型或索引、令牌。

常见 API type 的最小字段矩阵：

| 类型 | 最小字段 |
| --- | --- |
| fake LLM | `LLM_API_TYPE` |
| Ollama LLM | `LLM_API_TYPE`、`LLM_BASE_URL`、`LLM_MODEL` |
| OpenAI / DeepSeek / Gemini | `LLM_API_TYPE`、`LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY` |
| hash embedding | `EMBEDDING_API_TYPE`、`EMBEDDING_DIMENSIONS` |
| Ollama embedding | API type、base URL、model、dimensions |
| 云端 embedding | API type、base URL、model、token、dimensions |
| local text RAG | `RAG_API_TYPE` |
| Chroma | `RAG_API_TYPE`、`RAG_INDEX` |
| Qdrant | `RAG_API_TYPE`、`RAG_BASE_URL`、`RAG_INDEX`、`RAG_API_KEY` |

`LLM_MODEL` 同时作为服务端默认 alias，单 provider 用户不需要填写 `MODEL_ALIAS`。`MODEL_PROVIDER_REGISTRY` 存在时具有最高优先级，适合多 provider；否则 `LLM_*` 映射为内部 registry。简单 Embedding/RAG 字段覆盖对应 legacy 单 provider 字段，显式 `SESSION_PROVIDER` / `MEMORY_PROVIDER` 则覆盖 SQLite 默认。

### LLM

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `LLM_API_TYPE` | 是 | `fake`、`ollama`、`openai`、`openai_compatible`、`deepseek`、`gemini` |
| `LLM_BASE_URL` | 视类型 | API base URL；标准 provider 可使用内置默认值 |
| `LLM_MODEL` | 是 | provider 侧模型名称，同时作为默认聊天模型别名 |
| `LLM_API_KEY` | 云端必填 | API 令牌，只保存在 `.env` 或部署 secret |

OpenAI 示例：

```env
LLM_API_TYPE=openai
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4.1-mini
LLM_API_KEY=replace-with-secret
```

Gemini OpenAI compatibility 示例：

```env
LLM_API_TYPE=gemini
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
LLM_MODEL=gemini-2.5-flash
LLM_API_KEY=replace-with-secret
```

Ollama 示例：

```env
LLM_API_TYPE=ollama
LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_MODEL=qwen2.5:7b
```

### Embedding

只有向量 RAG 需要配置 embedding。纯文本 `RAG_API_TYPE=local` 不需要云 embedding。

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `EMBEDDING_API_TYPE` | 是 | `hash`、`ollama`、`openai`、`openai_compatible` |
| `EMBEDDING_BASE_URL` | 视类型 | Embedding API base URL |
| `EMBEDDING_MODEL` | 真实模型必填 | provider 侧 embedding 模型名称 |
| `EMBEDDING_API_KEY` | 云端必填 | API 令牌 |
| `EMBEDDING_DIMENSIONS` | 向量服务必填 | 请求和校验使用的向量维度，必须与向量库 collection 一致 |

OpenAI-compatible 示例：

```env
EMBEDDING_API_TYPE=openai_compatible
EMBEDDING_BASE_URL=https://embedding.example/v1
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_API_KEY=replace-with-secret
EMBEDDING_DIMENSIONS=1024
```

`EMBEDDING_DIMENSIONS` 会作为 `dimensions` 写入 OpenAI-compatible embedding 请求体，并用于校验响应向量长度。provider 不支持该参数时，应填写其固定输出维度。

### RAG

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `RAG_API_TYPE` | 是 | `fake`、`local`、`local_vector`、`chroma`、`faiss`、`qdrant` |
| `RAG_BASE_URL` | Qdrant 必填 | 向量服务地址 |
| `RAG_INDEX` | 持久化向量库必填 | collection 或 index 名称 |
| `RAG_API_KEY` | 云服务视情况 | 向量服务令牌 |

Qdrant 示例：

```env
RAG_API_TYPE=qdrant
RAG_BASE_URL=https://qdrant.example
RAG_INDEX=haruhi_rag
RAG_API_KEY=replace-with-secret
```

Qdrant collection 的向量维度必须与 `EMBEDDING_DIMENSIONS` 一致。文档导入成功只说明 upsert 成功；查询仍会因 collection 维度、filter schema 或权限不一致而返回 `RAG_PROVIDER_ERROR`。

RAG payload 从 12.04 起必须包含 `app_id`。升级已有 Chroma/Qdrant collection 时，推荐使用新的 collection 名称并从可信文档重新导入；也可以先备份，再清空旧 collection 后重导入。服务不会把缺少 `app_id` 的旧记录自动归属到某个应用，这些记录不会被新检索命中。

## 默认存储

`.env.example`、Compose 和简单 provider 配置默认使用 SQLite：

```env
SESSION_PROVIDER=sqlite
SESSION_SQLITE_PATH=.data/sessions.sqlite3
SESSION_RECENT_LIMIT=12

MEMORY_PROVIDER=sqlite
MEMORY_SQLITE_PATH=.data/memories.sqlite3

ACCESS_TOKEN_SQLITE_PATH=.data/access-tokens.sqlite3
```

- `SESSION_RECENT_LIMIT` 只限制每次进入 prompt 的最近 session 消息数量，不限制数据库总消息数。
- session 是连续对话原始消息；memory 是通过 policy 审核的长期信息，两者不是同一个存储。
- Compose 把宿主机 `./.data` 挂载到容器 `/app/.data`，重启容器不会自动删除数据。
- PostgreSQL session 配置属于高级场景；Memory 当前没有 PostgreSQL adapter。

## 鉴权和配置管理

`ROLEPLAY_API_KEY` 是受信任管理员密钥，用于配置和 Access Token 管理接口。普通业务调用可使用管理员密钥或由管理员创建的 `hrt_...` 服务令牌。

```env
ROLEPLAY_API_KEY=replace-with-strong-secret
```

`ROLEPLAY_HOST` 为 loopback（`127.0.0.1`、`::1`、`localhost`）时允许无管理密钥开发。绑定 `0.0.0.0`、`::` 或其它非 loopback 地址时，启动要求 `ROLEPLAY_API_KEY` 至少 32 字符且不能使用 `change-me`、`replace-with` 等占位值。

浏览器同源调用无需配置 CORS。前端和 API 不同源时，使用逗号分隔的精确 Origin 白名单，不填写路径且不能使用 `*`：

```env
ROLEPLAY_CORS_ORIGINS=https://app.example.com,https://admin.example.com
```

该字段修改后需要重启。未携带 `Origin` 的服务间调用继续由 API Key 或 Access Token 鉴权。

配置面板的字段 check 会拒绝 `*`、带路径的 Origin，以及非 loopback 监听配合短密钥或占位密钥的候选配置，避免保存后才在重启时发现错误。

受信任配置页面：

```text
http://127.0.0.1:8000/config
```

页面对应的 Env Config API 可以查看字段 schema、校验候选值并写回 `.env`。secret 只显示状态，不回显原值。该页面不应暴露到未受保护的公网。

## 热更新边界

- `PATCH /v1/runtime-config` 只更新允许热切换的非敏感运行参数。
- Env Config API 可以保存完整受支持字段，但 `restart_required_keys` 仍需重启服务生效。
- 监听地址、端口、session/memory provider 和数据库路径属于有状态或启动期配置，不能安全地原地替换。
- `ROLEPLAY_CORS_ORIGINS` 属于启动期配置，不能热切换。
- provider 配置保存前应先调用 `POST /v1/env-config/check`；保存成功不代表外部 provider 一定可连接，仍需实际 chat 或 RAG smoke。

## 高级配置何时使用

只有以下情况需要阅读 `backend-dispatch-and-configuration.md`：

- 一个服务实例需要多个模型 alias。
- 需要 `MODEL_PROVIDER_REGISTRY` 路由不同模型。
- 使用 PostgreSQL session。
- 调整 RAG chunk、Qdrant、Chroma/Faiss 或超时细节。
- 接入 backend context、debug trace 或 Agent planner 配置。

不要同时混用简单 `LLM_*` 配置和 `MODEL_PROVIDER_REGISTRY`。registry 存在时，模型路由以 registry 为准。

## 当前限制

- 请求资源上限使用代码常量，不新增 `.env` 字段：body 1 MiB、chat message 16,000 字符、RAG content 500,000 字符、`top_k` 20、`max_tokens` 8,192。
- `SafetyGuard` 尚未接入，`safety_filter` 目前不是内容审核保证。
- model-backed planner 尚未实现，使用 `AGENT_CONTEXT_PLANNER=model` 会导致 chat 返回 `MODEL_PROVIDER_ERROR`。
- 当前公开 persona 只有 `haruhi/mid_late_haruhi` 和 `kyon/default_kyon`；应通过 `GET /v1/personas` 获取实际 catalog。
- 配置编辑器适合本地或受信任后台，不是普通聊天前端接口。
