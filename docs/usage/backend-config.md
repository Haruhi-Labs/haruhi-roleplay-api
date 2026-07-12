# 后端配置文档

## 文档定位

这份文档是后端配置的第一入口。它只说明当前项目已经能用的配置方式、最小推荐配置

更完整的使用说明和 provider 调度细节见：

- `docs/usage/docker-compose.md`
- `docs/usage/backend-dispatch-and-configuration.md`
- `docs/usage/config-panel.md`
- `docs/usage/interface-reference.md`

如果目标是 Linux 单机部署，后续推荐走 Docker Compose 单容器路径。配置化简方向不是整套部署方案，而是模仿酒馆：选择 API type / provider，再填写 base URL、model 或 index、token。酒馆式 provider 配置字段已经实现；Docker Compose 封装仍在后续 `10.01` 中实现。使用形状见 `docs/usage/docker-compose.md`，实现卡片见 `docs/agent-dev/cards/10.*.md`。

## 当前配置面

当前项目有三类配置入口：

| 入口                            | 用途                                             | 适合谁使用               |
| ------------------------------- | ------------------------------------------------ | ------------------------ |
| `.env` / `ROLEPLAY_CONFIG_FILE` | 持久化后端配置，包含 secret 和需要重启的配置     | 本地开发、部署环境       |
| `GET/PATCH /v1/runtime-config`  | 非敏感配置热更新                                 | 受信任管理后端或本地调试 |
| `/config` + `/v1/env-config/*`  | 可视化 `.env` 编辑、字段 check、secret redaction | 本地开发、受信任后台     |

当前推荐新增一层简单 provider 配置：

| 分组             | 字段                                                                       | 作用                         |
| ---------------- | -------------------------------------------------------------------------- | ---------------------------- |
| Simple LLM       | `LLM_API_TYPE`、`LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`                 | 配置单个聊天模型后端         |
| Simple Embedding | `EMBEDDING_API_TYPE`、`EMBEDDING_BASE_URL`、`EMBEDDING_MODEL`、`EMBEDDING_API_KEY` | 配置单个 embedding 后端      |
| Simple RAG       | `RAG_API_TYPE`、`RAG_BASE_URL`、`RAG_INDEX`、`RAG_API_KEY`                 | 配置单个 RAG / vector 后端   |

这些 simple 字段会在服务端映射到现有 `MODEL_PROVIDER_REGISTRY`、`EMBEDDING_*`、`RAG_PROVIDER`、`QDRANT_*` 等内部配置。显式 `MODEL_PROVIDER_REGISTRY` 仍然优先，适合高级多模型路由。

普通聊天前端不应该配置后端 provider。普通前端只传：

- `character_id`
- `persona_mode`
- `message`
- `session_id`
- `capabilities`
- `generation.model` 中的服务端白名单 alias

模型、RAG、embedding、session store 和 secret 都由本项目服务端配置决定。

## 使用方式总览

个人开发者当前推荐按下面顺序使用：

1. 从模板创建本地配置。

   ```powershell
   Copy-Item .env.example .env
   ```

2. 先使用 fake local 配置启动服务，确认 HTTP、角色、session、stream、RAG 开关和前端 demo 能跑通。

   ```powershell
   $env:PYTHONPATH="src"
   uv run python -m haruhi_roleplay_api.infrastructure.http_server
   ```

3. 打开本地页面。

   ```text
   http://127.0.0.1:8000/demo
   http://127.0.0.1:8000/config
   ```

   如果修改了 `ROLEPLAY_PORT`，把 URL 中的端口换成 `.env` 中的新端口。`ROLEPLAY_HOST` / `ROLEPLAY_PORT` 是启动级配置，保存后需要重启服务才能重新绑定监听地址。

4. 如果只是聊天体验，用 `/demo`。如果要改后端 provider、模型、RAG、embedding、session 或 secret，用 `/config`。

5. 切换后端时优先只切一条链路：

   - fake local：不依赖真实模型，验证 API 和前端。
   - Ollama local：接入本地真实模型。
   - Ollama + Chroma：接入本地模型和持久化向量库。
   - cloud model：接入 OpenAI、DeepSeek 或 Gemini。
   - cloud full：再考虑 Qdrant、PostgreSQL 等云端组件。

6. 保存 `.env` 后查看 `/config` 返回的提示：

   - hot reload 成功：当前进程已尝试重建无状态 provider。
   - restart required：需要重启服务后完整生效。
   - check failed：字段格式或 provider 装配失败，先修正再保存。

## 当前已实现后端能力

| 能力            | 已实现 provider / adapter                                                                        | 当前建议                                                     |
| --------------- | ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------ |
| Model           | `fake`、`local_openai_compatible`、`openai_compatible`、`ollama`、`openai`、`deepseek`、`gemini` | 前端只传模型 alias；真实 provider 由服务端 registry 决定     |
| RAG             | `fake`、`local`、`local_vector`、`chroma`、`faiss`、`qdrant`                                     | 先用 `local` 或 `local_vector`，需要持久化再用 Chroma/Qdrant |
| Embedding       | `hash`、`local_openai_compatible`、`ollama`、`openai`                                            | 本地 smoke 用 `hash` 或 `ollama`；云端再用 `openai`          |
| Session         | `memory`、`sqlite`、`postgres`                                                                   | 本地开发用 SQLite；云端部署再用 PostgreSQL                   |
| Memory          | 当前为服务进程内 memory store                                                                    | 适合验证策略，不适合长期生产持久化                           |
| Agent planner   | `deterministic` 已实现，`model` 为预留入口                                                       | 当前使用 `deterministic`                                     |
| Backend context | `none` / `fake` 调试 provider                                                                    | 真实业务后端 adapter 后续单独实现                            |

其中 Chroma、Faiss、PostgreSQL 依赖为可选能力；如果本地环境没有安装对应 Python 包或没有数据库服务，配置 check 会提示失败。

## 最小可用配置

### 1. 最安全的本地 fake 配置

用途：验证 HTTP、角色、session、RAG 开关、stream 和前端 demo，不依赖真实模型。

```env
ROLEPLAY_HOST=127.0.0.1
ROLEPLAY_PORT=8000
ROLEPLAY_API_KEY=dev-secret
ENABLE_DEBUG_TRACE=true

MODEL_PROVIDER=fake
MODEL_NAME=fake-roleplay-model
MODEL_ALIAS=fake-roleplay-model

RAG_PROVIDER=local
RAG_CHUNK_SIZE=320

EMBEDDING_PROVIDER=hash
EMBEDDING_DIMENSIONS=384

SESSION_PROVIDER=memory
SESSION_RECENT_LIMIT=12
```

启动：

```powershell
$env:PYTHONPATH="src"
uv run python -m haruhi_roleplay_api.infrastructure.http_server
```

访问：

```text
http://127.0.0.1:8000/demo
http://127.0.0.1:8000/config
```

### 2. 本地真实模型配置：Ollama + 本地 RAG

用途：个人开发者本机跑真实回复，仍避免云服务成本。

```env
ROLEPLAY_API_KEY=dev-secret
ENABLE_DEBUG_TRACE=true

MODEL_PROVIDER_REGISTRY={"default_alias":"haruhi-ollama","providers":{"ollama-local":{"type":"ollama","base_url":"http://localhost:11434/v1","timeout_ms":180000}},"aliases":{"haruhi-ollama":{"provider":"ollama-local","model":"qwen2.5:7b"}}}

RAG_PROVIDER=local_vector
RAG_VECTOR_BACKEND=memory
RAG_CHUNK_SIZE=320

EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text:latest
EMBEDDING_BASE_URL=http://localhost:11434/v1
EMBEDDING_DIMENSIONS=768

SESSION_PROVIDER=sqlite
SESSION_SQLITE_PATH=.data/sessions.sqlite3
SESSION_RECENT_LIMIT=12
```

如果要使用 Chroma 持久化向量库：

```env
RAG_PROVIDER=chroma
CHROMA_COLLECTION=haruhi_rag
CHROMA_PERSIST_PATH=.chroma
```

Chroma 是可选依赖，默认不进入项目依赖。使用时需要在本地运行环境额外安装。

### 3. 云模型配置

用途：接入 OpenAI、DeepSeek、Gemini 等云模型。推荐仍通过 `MODEL_PROVIDER_REGISTRY` 声明 provider 和 alias。

示例形状：

```env
ROLEPLAY_API_KEY=dev-secret
OPENAI_API_KEY=replace-with-local-secret

MODEL_PROVIDER_REGISTRY={"default_alias":"haruhi-openai","providers":{"openai-main":{"type":"openai","api_key_env":"OPENAI_API_KEY","timeout_ms":60000}},"aliases":{"haruhi-openai":{"provider":"openai-main","model":"gpt-4.1-mini"}}}

RAG_PROVIDER=local
EMBEDDING_PROVIDER=hash
SESSION_PROVIDER=memory
```

secret 可以保存在 `.env` 或部署平台 secret 中。API 响应和 `/config` 页面只显示 secret 状态，不回显原文。

## 配置分组

| 分组            | 常用字段                                                                              | 说明                     |
| --------------- | ------------------------------------------------------------------------------------- | ------------------------ |
| HTTP            | `ROLEPLAY_HOST`、`ROLEPLAY_PORT`、`ROLEPLAY_API_KEY`                                  | 服务监听和管理鉴权       |
| Access Token    | `ACCESS_TOKEN_SQLITE_PATH`                                                            | 服务令牌、额度、用量和日志持久化 |
| Model           | `MODEL_PROVIDER_REGISTRY`、`MODEL_PROVIDER`、`MODEL_NAME`、`MODEL_ALIAS`              | 模型 provider 和模型别名 |
| Simple LLM      | `LLM_API_TYPE`、`LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`                            | 单模型后端的酒馆式入口   |
| RAG             | `RAG_PROVIDER`、`RAG_CHUNK_SIZE`、`RAG_VECTOR_BACKEND`、`CHROMA_*`、`QDRANT_*`        | 文档导入、检索和向量库   |
| Simple RAG      | `RAG_API_TYPE`、`RAG_BASE_URL`、`RAG_INDEX`、`RAG_API_KEY`                            | 单 RAG 后端的酒馆式入口  |
| Embedding       | `EMBEDDING_PROVIDER`、`EMBEDDING_MODEL`、`EMBEDDING_BASE_URL`、`EMBEDDING_DIMENSIONS` | 向量生成                 |
| Simple Embedding | `EMBEDDING_API_TYPE`、`EMBEDDING_BASE_URL`、`EMBEDDING_MODEL`、`EMBEDDING_API_KEY`   | 单 embedding 后端入口     |
| Session         | `SESSION_PROVIDER`、`SESSION_RECENT_LIMIT`、`SESSION_SQLITE_PATH`、`DATABASE_URL`     | 连续会话存储             |
| Agent           | `AGENT_CONTEXT_PLANNER`                                                               | 当前推荐 `deterministic` |
| Backend Context | `BACKEND_CONTEXT_PROVIDER`、`BACKEND_CONTEXT_SOURCES`                                 | 当前只建议本地 fake 调试 |
| Secrets         | `OPENAI_API_KEY`、`DEEPSEEK_API_KEY`、`GEMINI_API_KEY`、`DATABASE_URL`                | 只在服务端保存           |

当前 runtime 中 Memory store 仍是 in-memory 装配，不建议添加 `MEMORY_PROVIDER` 配置。等持久化 memory adapter 实现后再单独纳入配置面。

## 后端字段字典

本节按 `/config` 页面和 `EnvConfigEditor` schema 的分组解释当前后端配置字段。状态含义：

- hot reload：保存后当前进程会尝试重建相关无状态 provider。
- restart required：会写入 `.env`，但需要重启服务后完整生效。
- secret：只能显示 set / empty / missing 状态，不回显原文。
- reserved：字段已在 schema 中预留，但当前主链路尚未完整使用。

### HTTP

用途：控制本项目 HTTP 服务监听地址、管理接口鉴权和 debug 返回。

| 字段                   | 状态               | 含义                                                              | 什么时候用                         |
| ---------------------- | ------------------ | ----------------------------------------------------------------- | ---------------------------------- |
| `ROLEPLAY_CONFIG_FILE` | 启动读取           | 指定 `.env` 文件路径；不在 `/config` schema 中，但 runtime 会读取 | 多环境、本地临时配置文件           |
| `ROLEPLAY_HOST`        | restart required   | HTTP bind host                                                    | 需要局域网访问时可设为 `0.0.0.0`   |
| `ROLEPLAY_PORT`        | restart required   | HTTP bind port                                                    | 本地端口冲突或多实例运行           |
| `ROLEPLAY_API_KEY`     | secret, hot reload | Bootstrap 管理密钥                                                 | `/config`、配置 API、服务令牌签发 |
| `ENABLE_DEBUG_TRACE`   | hot reload         | 是否允许返回安全裁剪后的 debug trace                              | 本地调试打开，生产环境建议关闭     |

示例：

```env
ROLEPLAY_HOST=127.0.0.1
ROLEPLAY_PORT=8010
ROLEPLAY_API_KEY=dev-secret
ENABLE_DEBUG_TRACE=true
```

启动后访问：

```text
http://127.0.0.1:8010/demo
http://127.0.0.1:8010/config
```

如果修改 `ROLEPLAY_HOST` 或 `ROLEPLAY_PORT`，必须重启服务。端口不是热更新字段，因为 HTTP socket 在启动时已经绑定。

生产中的业务后端应使用管理 API 签发的独立 `hrt_...` 服务令牌，不应共享 `ROLEPLAY_API_KEY`。令牌签发、吊销、额度和日志说明见 `docs/usage/access-token-management.md`。

### Access Token

| 字段 | 状态 | 含义 |
| --- | --- | --- |
| `ACCESS_TOKEN_SQLITE_PATH` | restart required | SQLite 令牌账本路径，默认 `.data/access-tokens.sqlite3` |

该账本保存令牌哈希、状态、过期时间、额度、累计模型 Token 用量和逐令牌请求日志。修改路径需要重启；令牌额度通过 `/v1/access-tokens` 管理 API 设置，不放在 `.env` 中。

### Simple Provider Facade

用途：个人用户只接一个 LLM、一个 embedding provider、一个 RAG provider 时使用。它是当前推荐入口，形状接近酒馆类工具：选择 API type/provider，再填 base URL、模型或 index、token。

| 字段                 | 状态               | 含义                                                  | 映射到内部字段                         |
| -------------------- | ------------------ | ----------------------------------------------------- | -------------------------------------- |
| `LLM_API_TYPE`       | hot reload         | LLM API 类型，支持 `fake`、`openai`、`openai_compatible`、`ollama`、`deepseek`、`gemini` | `MODEL_PROVIDER_REGISTRY.providers.*.type` |
| `LLM_BASE_URL`       | hot reload         | LLM base URL；OpenAI/DeepSeek/Gemini 可使用默认值     | `MODEL_PROVIDER_REGISTRY.providers.*.base_url` |
| `LLM_MODEL`          | hot reload         | LLM 模型名，同时作为默认模型 alias                    | `MODEL_PROVIDER_REGISTRY.aliases.*.model` |
| `LLM_API_KEY`        | secret, hot reload | LLM token                                             | `MODEL_PROVIDER_REGISTRY.providers.*.api_key_env=LLM_API_KEY` |
| `EMBEDDING_API_TYPE` | hot reload         | Embedding API 类型，支持 `hash`、`openai`、`openai_compatible`、`local_openai_compatible`、`ollama` | `EMBEDDING_PROVIDER` |
| `EMBEDDING_BASE_URL` | hot reload         | Embedding base URL                                    | `EMBEDDING_BASE_URL` |
| `EMBEDDING_MODEL`    | hot reload         | Embedding 模型名                                      | `EMBEDDING_MODEL` |
| `EMBEDDING_API_KEY`  | secret, hot reload | Embedding token                                       | `EMBEDDING_API_KEY` |
| `RAG_API_TYPE`       | hot reload         | RAG API 类型；当前云端链路主要是 `qdrant`             | `RAG_PROVIDER` |
| `RAG_BASE_URL`       | hot reload         | RAG base URL                                          | `QDRANT_URL` when `RAG_API_TYPE=qdrant` |
| `RAG_INDEX`          | hot reload         | collection、index 或 vector store id                  | `QDRANT_COLLECTION` / `CHROMA_COLLECTION` |
| `RAG_API_KEY`        | secret, hot reload | RAG token                                             | `QDRANT_API_KEY` when `RAG_API_TYPE=qdrant` |

示例：

```env
LLM_API_TYPE=openai
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4.1-mini
LLM_API_KEY=replace-with-local-secret

EMBEDDING_API_TYPE=openai
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_API_KEY=replace-with-local-secret

RAG_API_TYPE=qdrant
RAG_BASE_URL=https://your-qdrant.example
RAG_INDEX=haruhi_rag
RAG_API_KEY=replace-with-local-secret
```

优先级：

- 如果设置了 `MODEL_PROVIDER_REGISTRY`，模型侧使用高级 registry，忽略 `LLM_*` facade。
- 如果设置了 `LLM_*` 且没有 `MODEL_PROVIDER_REGISTRY`，`LLM_*` 会覆盖 legacy `MODEL_PROVIDER` / `MODEL_NAME` / `MODEL_ALIAS`。
- `EMBEDDING_*` 和 `RAG_*` simple 字段会覆盖对应内部 provider 字段。
- 如果 simple provider 字段存在但没有显式 `SESSION_PROVIDER`，服务端默认使用 `sqlite` 和 `.data/sessions.sqlite3`；Docker Compose 后续会在 `.env.compose.example` 中显式设置 `/app/data/sessions.sqlite3`。

### Model：简单单 provider 配置

用途：个人开发者只接一个模型后端时使用。它比 `MODEL_PROVIDER_REGISTRY` 简单，适合 fake、Ollama、本地 OpenAI-compatible 或单个云模型 smoke。

| 字段                  | 状态               | 含义                                                                                                  | 什么时候用                                         |
| --------------------- | ------------------ | ----------------------------------------------------------------------------------------------------- | -------------------------------------------------- |
| `MODEL_PROVIDER`      | hot reload         | 单 provider 类型；支持 `fake`、`local`、`openai_compatible`、`ollama`、`openai`、`deepseek`、`gemini` | 只接一个模型后端                                   |
| `MODEL_PROVIDER_ID`   | hot reload         | provider 内部 id，默认由 provider type 推导                                                           | 需要稳定 debug/provider 标识时                     |
| `MODEL_PROVIDER_NAME` | hot reload         | 本地 OpenAI-compatible provider 的显示名                                                              | LM Studio、vLLM 等本地服务区分来源                 |
| `MODEL_NAME`          | hot reload         | 传给 provider 的真实模型名                                                                            | Ollama 的 `qwen2.5:7b`、OpenAI 的 `gpt-4.1-mini`   |
| `MODEL_ALIAS`         | hot reload         | 暴露给前端 `generation.model` 的服务端白名单别名                                                      | 希望前端不直接使用真实模型名                       |
| `MODEL_BASE_URL`      | hot reload         | OpenAI-compatible base URL                                                                            | Ollama、LM Studio、vLLM、本地网关                  |
| `MODEL_TIMEOUT_MS`    | hot reload         | 模型请求超时，毫秒                                                                                    | 本地大模型推理慢时调大                             |
| `MODEL_API_KEY_ENV`   | hot reload         | 从哪个环境变量读取模型 API key                                                                        | 不想把 key 直接写在 provider 配置里                |
| `MODEL_API_KEY`       | secret, hot reload | 单 provider 直接 API key fallback                                                                     | 本地私有网关或临时调试；生产更推荐 `*_API_KEY_ENV` |

fake 示例：

```env
MODEL_PROVIDER=fake
MODEL_NAME=fake-roleplay-model
MODEL_ALIAS=fake-roleplay-model
MODEL_TIMEOUT_MS=60000
```

Ollama 简单示例：

```env
MODEL_PROVIDER=ollama
MODEL_BASE_URL=http://localhost:11434/v1
MODEL_NAME=qwen2.5:7b
MODEL_ALIAS=haruhi-local
MODEL_TIMEOUT_MS=180000
```

前端或业务后端只传：

```json
{
  "generation": {
    "model": "haruhi-local"
  }
}
```

如果不传 `generation.model`，服务端使用默认 alias。简单配置下默认 alias 就是 `MODEL_ALIAS`；如果未设置 `MODEL_ALIAS`，则回退为 `MODEL_NAME`。

### Model Registry：多 provider 配置

用途：同时接多个模型来源时使用，例如本地 Ollama、OpenAI、DeepSeek、Gemini 共存。它是高级配置；个人开发者只有一个模型后端时不必使用。

| 字段                      | 状态       | 含义                                                      | 什么时候用                                   |
| ------------------------- | ---------- | --------------------------------------------------------- | -------------------------------------------- |
| `MODEL_PROVIDER_REGISTRY` | hot reload | JSON 字符串，声明 `providers`、`aliases`、`default_alias` | 多模型、多厂商、前端需要选择服务端白名单模型 |

JSON 内部字段：

| 字段                         | 含义                                                         |
| ---------------------------- | ------------------------------------------------------------ |
| `default_alias`              | 请求没有传 `generation.model` 时使用的默认模型别名           |
| `providers.<id>.type`        | provider 类型，例如 `ollama`、`openai`、`deepseek`、`gemini` |
| `providers.<id>.base_url`    | provider base URL；云厂商有默认值，本地服务通常要写          |
| `providers.<id>.api_key_env` | 从指定环境变量读取 API key                                   |
| `providers.<id>.timeout_ms`  | 当前 provider 请求超时                                       |
| `aliases.<alias>.provider`   | alias 指向哪个 provider id                                   |
| `aliases.<alias>.model`      | provider 侧真实模型名                                        |

Ollama registry 示例：

```env
MODEL_PROVIDER_REGISTRY={"default_alias":"haruhi-local","providers":{"ollama-local":{"type":"ollama","base_url":"http://localhost:11434/v1","timeout_ms":180000}},"aliases":{"haruhi-local":{"provider":"ollama-local","model":"qwen2.5:7b"}}}
```

云模型 registry 示例：

```env
OPENAI_API_KEY=replace-with-local-secret
DEEPSEEK_API_KEY=replace-with-local-secret

MODEL_PROVIDER_REGISTRY={"default_alias":"haruhi-openai","providers":{"openai-main":{"type":"openai","api_key_env":"OPENAI_API_KEY","timeout_ms":60000},"deepseek-main":{"type":"deepseek","api_key_env":"DEEPSEEK_API_KEY","timeout_ms":60000}},"aliases":{"haruhi-openai":{"provider":"openai-main","model":"gpt-4.1-mini"},"haruhi-deepseek":{"provider":"deepseek-main","model":"deepseek-chat"}}}
```

使用边界：

- `generation.model` 是 alias，不是厂商真实模型名。
- 前端不能传 provider、base URL、API key。
- registry 中不要写 inline `api_key`，推荐写 `api_key_env` 并把真实 key 放在 `.env` 或部署平台 secret。
- 如果 `MODEL_PROVIDER_REGISTRY` 存在且非空，它优先于简单单 provider 配置。

### RAG

用途：控制文档导入、检索、向量库和云端检索后端。前端只通过 `capabilities.rag=true` 请求使用 RAG，不直接选择 provider。

| 字段                       | 状态               | 含义                                                                            | 什么时候用                                   |
| -------------------------- | ------------------ | ------------------------------------------------------------------------------- | -------------------------------------------- |
| `RAG_PROVIDER`             | hot reload         | RAG provider；支持 `fake`、`local`、`local_vector`、`chroma`、`faiss`、`qdrant` | 切换本地文本检索、向量检索或云向量库         |
| `RAG_CHUNK_SIZE`           | hot reload         | 本地导入文档切 chunk 的字符粒度                                                 | chunk 太短信息碎，太长检索粗                 |
| `RAG_EMBEDDING_DIMENSIONS` | hot reload         | 兼容字段，RAG 向量维度                                                          | 旧配置兼容；优先使用 `EMBEDDING_DIMENSIONS`  |
| `RAG_VECTOR_BACKEND`       | hot reload         | `local_vector` 的本地向量 backend，支持 `memory`、`chroma`、`faiss`             | 本地向量 RAG 的底层选择                      |
| `LOCAL_VECTOR_RAG_BACKEND` | hot reload         | `RAG_VECTOR_BACKEND` 的兼容别名                                                 | 旧配置兼容，不建议新配置继续使用             |
| `CHROMA_COLLECTION`        | hot reload         | Chroma collection 名称                                                          | 使用 `RAG_PROVIDER=chroma` 或 Chroma backend |
| `CHROMA_PERSIST_PATH`      | hot reload         | Chroma 本地持久化目录                                                           | 希望重启后保留本地向量数据                   |
| `QDRANT_URL`               | hot reload         | Qdrant 服务地址                                                                 | 使用云端或本地 Qdrant                        |
| `QDRANT_COLLECTION`        | hot reload         | Qdrant collection 名称                                                          | 区分项目或环境                               |
| `QDRANT_TIMEOUT_MS`        | hot reload         | Qdrant 请求超时，毫秒                                                           | 云端网络慢时调大                             |
| `QDRANT_ENSURE_COLLECTION` | hot reload         | 是否尝试创建缺失 collection                                                     | 本地调试可开，生产建议由运维/迁移脚本管理    |
| `QDRANT_API_KEY`           | secret, hot reload | Qdrant API key                                                                  | Qdrant Cloud 或私有鉴权                      |

本地文本 RAG 示例：

```env
RAG_PROVIDER=local
RAG_CHUNK_SIZE=320
```

本地向量 RAG 示例：

```env
RAG_PROVIDER=local_vector
RAG_VECTOR_BACKEND=memory
RAG_CHUNK_SIZE=320
EMBEDDING_PROVIDER=hash
EMBEDDING_DIMENSIONS=384
```

Chroma 示例：

```env
RAG_PROVIDER=chroma
CHROMA_COLLECTION=haruhi_rag
CHROMA_PERSIST_PATH=.chroma
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text:latest
EMBEDDING_BASE_URL=http://localhost:11434/v1
EMBEDDING_DIMENSIONS=768
```

Qdrant 示例：

```env
RAG_PROVIDER=qdrant
QDRANT_URL=http://127.0.0.1:6333
QDRANT_COLLECTION=haruhi_rag
QDRANT_TIMEOUT_MS=10000
QDRANT_ENSURE_COLLECTION=false
QDRANT_API_KEY=replace-with-local-secret
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
OPENAI_API_KEY=replace-with-local-secret
```

Chroma、Faiss、PostgreSQL、psycopg 等属于可选能力；缺少依赖时配置 check 或 provider 构建会失败，不会静默降级。

### Embedding

用途：给向量 RAG 生成 query/document embedding。只有 `local_vector`、Chroma、Faiss、Qdrant 等向量链路需要重点配置。

| 字段                    | 状态               | 含义                                                                                                         | 什么时候用                                   |
| ----------------------- | ------------------ | ------------------------------------------------------------------------------------------------------------ | -------------------------------------------- |
| `EMBEDDING_PROVIDER`    | hot reload         | embedding provider；支持 `hash`、`local_openai_compatible`、`openai_compatible`、`local`、`ollama`、`openai` | 选择本地 hash、Ollama、本地兼容端点或 OpenAI |
| `EMBEDDING_MODEL`       | hot reload         | provider 侧真实 embedding 模型名                                                                             | Ollama/OpenAI embedding                      |
| `EMBEDDING_BASE_URL`    | hot reload         | embedding provider base URL                                                                                  | Ollama 或本地 OpenAI-compatible endpoint     |
| `EMBEDDING_DIMENSIONS`  | hot reload         | 向量维度                                                                                                     | 必须和向量库 collection 维度一致             |
| `EMBEDDING_TIMEOUT_MS`  | hot reload         | embedding 请求超时，毫秒                                                                                     | 本地模型慢或云端网络慢时调大                 |
| `EMBEDDING_API_KEY_ENV` | hot reload         | 从哪个环境变量读取 embedding API key                                                                         | 云端或私有 endpoint                          |
| `EMBEDDING_API_KEY`     | secret, hot reload | 直接 embedding API key fallback                                                                              | 临时调试；生产更推荐 `*_API_KEY_ENV`         |
| `EMBEDDING_PATH`        | hot reload         | embeddings API path override                                                                                 | 非标准 OpenAI-compatible endpoint            |

hash 示例，最适合本地 smoke：

```env
EMBEDDING_PROVIDER=hash
EMBEDDING_DIMENSIONS=384
```

Ollama 示例：

```env
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text:latest
EMBEDDING_BASE_URL=http://localhost:11434/v1
EMBEDDING_DIMENSIONS=768
EMBEDDING_TIMEOUT_MS=60000
```

OpenAI 示例：

```env
OPENAI_API_KEY=replace-with-local-secret
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
EMBEDDING_API_KEY_ENV=OPENAI_API_KEY
```

如果向量库已经建好，修改 `EMBEDDING_DIMENSIONS` 通常意味着需要重建 collection 或重新导入文档。

### Agent

用途：决定每次 chat 前如何规划上下文读取。当前推荐保持确定性，不调用额外模型。

| 字段                    | 状态       | 含义                                                   | 什么时候用                                              |
| ----------------------- | ---------- | ------------------------------------------------------ | ------------------------------------------------------- |
| `AGENT_CONTEXT_PLANNER` | hot reload | planner 模式；支持 `deterministic`，`model` 为预留入口 | 默认用 `deterministic`；不要在当前生产/演示使用 `model` |

示例：

```env
AGENT_CONTEXT_PLANNER=deterministic
```

当前状态：

- `deterministic` 已实现，会按 capability、persona policy 和服务端配置决定是否读 session、memory、RAG、backend context。
- `model` 只是接口预留。配置 check 会给 warning，chat 执行时仍可能返回未实现错误。

### Backend Context

用途：让中转服务在 prompt 组装前，从业务后端或其它系统读取受控 facts。当前只实现 `fake` 调试 provider。

| 字段                              | 状态       | 含义                                          | 什么时候用                     |
| --------------------------------- | ---------- | --------------------------------------------- | ------------------------------ |
| `BACKEND_CONTEXT_PROVIDER`        | hot reload | backend context provider；支持 `none`、`fake` | 本地调试业务上下文融合         |
| `BACKEND_CONTEXT_SOURCES`         | hot reload | 本次 planner 可读取的 source 列表，逗号分隔   | 例如 `user_profile,game_state` |
| `BACKEND_CONTEXT_ALLOWED_SOURCES` | hot reload | fake provider 允许的 source 白名单            | 防止配置中请求未允许 source    |

关闭示例：

```env
BACKEND_CONTEXT_PROVIDER=none
BACKEND_CONTEXT_SOURCES=
BACKEND_CONTEXT_ALLOWED_SOURCES=user_profile,game_state
```

fake 调试示例：

```env
BACKEND_CONTEXT_PROVIDER=fake
BACKEND_CONTEXT_SOURCES=user_profile,game_state
BACKEND_CONTEXT_ALLOWED_SOURCES=user_profile,game_state
```

真实业务后端 adapter 尚未实现。普通前端不应该选择 `BACKEND_CONTEXT_SOURCES`；这属于服务端调度配置。

### Session

用途：保存连续会话的短期消息历史。它和长期 memory 不是一回事：session 是当前对话历史，memory 是跨会话稳定事实。

| 字段                             | 状态                     | 含义                                                 | 什么时候用                                  |
| -------------------------------- | ------------------------ | ---------------------------------------------------- | ------------------------------------------- |
| `SESSION_PROVIDER`               | restart required         | session store；支持 `memory`、`sqlite`、`postgres`   | 本地用 `sqlite`，云端用 `postgres`          |
| `SESSION_RECENT_LIMIT`           | hot reload               | 每次 chat 读取最近多少条 session message 进入 prompt | 控制上下文长度、成本和连续性                |
| `SESSION_TTL_SECONDS`            | restart required         | session 过期秒数                                     | 后续持久化清理/过期策略                     |
| `SESSION_AUTO_CREATE_SCHEMA`     | restart required         | 是否自动建表/schema                                  | 本地开发方便；生产可关闭后走迁移            |
| `SESSION_SQLITE_PATH`            | restart required         | SQLite 数据库文件路径                                | 本地持久化 session                          |
| `SESSION_SQLITE_BUSY_TIMEOUT_MS` | restart required         | SQLite busy timeout                                  | 并发写入时减少锁冲突错误                    |
| `SESSION_POSTGRES_SCHEMA`        | restart required         | PostgreSQL schema 名                                 | 云端隔离表结构                              |
| `SESSION_POSTGRES_TABLE_PREFIX`  | restart required         | PostgreSQL 表名前缀                                  | 同库多项目隔离                              |
| `SESSION_POSTGRES_POOL_SIZE`     | restart required         | 预留连接池大小                                       | 当前 adapter 每次操作短连接，后续连接池使用 |
| `DATABASE_URL`                   | secret, restart required | PostgreSQL 连接串                                    | `SESSION_PROVIDER=postgres` 必填            |

memory session 示例：

```env
SESSION_PROVIDER=memory
SESSION_RECENT_LIMIT=12
SESSION_TTL_SECONDS=604800
SESSION_AUTO_CREATE_SCHEMA=true
```

SQLite 示例：

```env
SESSION_PROVIDER=sqlite
SESSION_SQLITE_PATH=.data/sessions.sqlite3
SESSION_SQLITE_BUSY_TIMEOUT_MS=5000
SESSION_RECENT_LIMIT=12
```

PostgreSQL 示例：

```env
SESSION_PROVIDER=postgres
DATABASE_URL=postgresql://user:password@localhost:5432/haruhi_roleplay
SESSION_POSTGRES_SCHEMA=public
SESSION_POSTGRES_TABLE_PREFIX=roleplay_
SESSION_POSTGRES_POOL_SIZE=5
SESSION_AUTO_CREATE_SCHEMA=true
```

`SESSION_PROVIDER` 不能运行中热切换。它会改变有状态存储位置，必须重启后重新装配。

### Secrets

用途：保存模型、embedding、RAG、数据库等后端 secret。secret 可以通过 `/config` 设置，但任何响应都只能返回状态，不返回真实值。

| 字段                | 状态                               | 含义                            | 当前使用者                              |
| ------------------- | ---------------------------------- | ------------------------------- | --------------------------------------- |
| `OPENAI_API_KEY`    | secret, hot reload                 | OpenAI chat / embedding API key | OpenAI model provider、OpenAI embedding |
| `DEEPSEEK_API_KEY`  | secret, hot reload                 | DeepSeek API key                | DeepSeek model provider                 |
| `GEMINI_API_KEY`    | secret, hot reload                 | Gemini API key                  | Gemini model provider                   |
| `MODEL_API_KEY`     | secret, hot reload                 | 单 provider 直接模型 API key    | 本地/私有 OpenAI-compatible provider    |
| `EMBEDDING_API_KEY` | secret, hot reload                 | 直接 embedding API key          | 私有 embedding endpoint                 |
| `QDRANT_API_KEY`    | secret, hot reload                 | Qdrant API key                  | Qdrant RAG provider                     |
| `DATABASE_URL`      | secret, restart required           | PostgreSQL 连接串               | PostgreSQL session store                |
| `REDIS_URL`         | secret, restart required, reserved | Redis 连接串预留                | 当前主链路未使用                        |

推荐做法：

```env
OPENAI_API_KEY=replace-with-local-secret
DEEPSEEK_API_KEY=replace-with-local-secret
GEMINI_API_KEY=replace-with-local-secret
QDRANT_API_KEY=replace-with-local-secret
DATABASE_URL=postgresql://user:password@localhost:5432/haruhi_roleplay
```

不要把这些字段放进前端请求、debug trace、日志或公开文档示例的真实值里。

### Advanced

用途：保留更底层或未来扩展字段。当前普通本地开发不需要修改。

| 字段                 | 状态                       | 含义                     | 当前状态                                                            |
| -------------------- | -------------------------- | ------------------------ | ------------------------------------------------------------------- |
| `PERSONA_CONFIG_DIR` | restart required, reserved | 本地 persona config 目录 | schema 已暴露，但当前 HTTP runtime 仍使用项目根目录下的 `personas/` |

示例：

```env
PERSONA_CONFIG_DIR=./personas
```

该字段目前不要作为主要配置入口。后续如果要支持多 persona 目录，应先把 persona repository factory 接入 runtime，再把该字段标为正式可用。

## 热更新与重启边界

| 类型     | 示例                                                                                                                   | 行为                          |
| -------- | ---------------------------------------------------------------------------------------------------------------------- | ----------------------------- |
| 可热更新 | `MODEL_*`、`RAG_PROVIDER`、`EMBEDDING_*`、`SESSION_RECENT_LIMIT`、`ENABLE_DEBUG_TRACE`                                 | 保存后尝试重建无状态 provider |
| 需要重启 | `ROLEPLAY_HOST`、`ROLEPLAY_PORT`、`SESSION_PROVIDER`、`SESSION_SQLITE_PATH`、`SESSION_POSTGRES_SCHEMA`、`DATABASE_URL` | 写入 `.env`，重启后完整生效   |
| 敏感字段 | `ROLEPLAY_API_KEY`、`OPENAI_API_KEY`、`DATABASE_URL`                                                                   | 只返回状态，不返回原文        |

不要在运行中热切换 `ROLEPLAY_PORT` 或 `SESSION_PROVIDER`。端口对应已经绑定的 HTTP socket，session store 是有状态资源，运行中切换会造成连接入口或会话读写位置突变。
