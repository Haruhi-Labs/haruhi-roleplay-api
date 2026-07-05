# 中转服务后端调度与配置说明

## 目标

说明当前项目在收到前端链路请求后，如何在中转服务内部调度具体后端实现，以及后端能力应该如何配置和实现。

这里的“后端实现”指本项目内部的 provider 或 adapter，例如：

- Session 使用 InMemory、SQLite 还是 PostgreSQL。
- Memory 使用 InMemory、SQLite 还是 PostgreSQL。
- RAG 使用 LocalVector、Qdrant、pgvector 还是 OpenAI Vector Store。
- Model 使用 FakeModel、Ollama、本地 OpenAI-compatible 服务还是云模型。
- Persona 使用本地配置文件还是数据库。

## 请求链路

推荐链路：

前端 -> 业务后端 -> 本项目 Roleplay API -> Provider Pack -> 具体后端实现

前端不直接选择具体 provider。前端只传业务参数：

- `persona_mode`
- `character_id`
- `message`
- `session_id`
- `capabilities`
- `generation`

业务后端负责：

- 绑定登录用户到 `user_id`。
- 传入可信的 `app_id`。
- 保管 API Key。
- 决定是否允许开启 RAG、memory、debug trace。

本项目负责：

- 校验请求。
- 鉴权和限流。
- 根据配置选择 provider pack。
- 根据 capabilities 调度 session、memory、RAG、model。
- 返回统一响应。

## 调度入口

所有请求进入 API 层后，应该统一走 application use case。

推荐调用路径：

1. API Controller 接收 HTTP 请求。
2. DTO Mapper 把 HTTP `snake_case` 转成内部 `camelCase`。
3. AuthService 生成 AuthContext。
4. RateLimiter 检查调用频率。
5. SendChatMessageUseCase 接收 ChatInput。
6. RoleplayOrchestrator 进行业务编排。
7. Orchestrator 只调用 ports。
8. ports 的具体实现由 Provider Pack 在启动时注入。

核心原则：请求运行中不要临时 `new` 具体 provider。

## 调度决策来源

调度具体后端实现时，按这个优先级决策：

1. 启动环境配置，例如 `APP_ENV`、`PROVIDER_PACK`。
2. app 级配置，例如某个 `app_id` 是否允许使用云 RAG。
3. 请求能力开关，例如 `capabilities.rag`、`capabilities.memory`。
4. character 和 persona mode 策略，例如时间线和 RAG filter。
5. generation 参数，例如模型别名、温度、最大 token。
6. provider 健康状态和 fallback 策略。

不要让前端直接传 `provider=qdrant` 或 `provider=openai` 这类字段。

## Provider Pack

Provider Pack 是一组后端实现绑定。

### local

用于本地开发和最小验证。

| 能力              | 实现                                                                             |
| ----------------- | -------------------------------------------------------------------------------- |
| PersonaRepository | 本地 YAML 或 JSON，包含角色和 preset catalog                                     |
| SessionStore      | InMemory 或 SQLite                                                               |
| MemoryStore       | InMemory 或 SQLite                                                               |
| RagService        | LocalRagService                                                                  |
| VectorIndex       | LocalVectorIndex                                                                 |
| EmbeddingProvider | HashEmbeddingProvider、OllamaEmbeddingProvider 或本地 OpenAI-compatible endpoint |
| ModelProvider     | Ollama 或本地 OpenAI-compatible                                                  |
| Logger            | ConsoleLogger                                                                    |

### test

用于单元测试、契约测试和 CI。

| 能力              | 实现                                             |
| ----------------- | ------------------------------------------------ |
| PersonaRepository | InMemoryPersonaRepository，包含测试角色和 preset |
| SessionStore      | InMemorySessionStore                             |
| MemoryStore       | InMemoryMemoryStore                              |
| RagService        | FakeRagService                                   |
| VectorIndex       | FakeVectorIndex                                  |
| EmbeddingProvider | HashEmbeddingProvider                            |
| ModelProvider     | FakeModelProvider                                |
| Logger            | NoopLogger 或 TestLogger                         |

### cloud

用于生产环境。

| 能力              | 实现                                                                          |
| ----------------- | ----------------------------------------------------------------------------- |
| PersonaRepository | PostgresPersonaRepository，存储角色和 preset catalog                          |
| SessionStore      | PostgresSessionStore                                                          |
| MemoryStore       | PostgresMemoryStore                                                           |
| CacheStore        | RedisCacheStore                                                               |
| RagService        | 当前实现 `QdrantRagService`；pgvector / OpenAI Vector Store 留作后续 provider |
| EmbeddingProvider | OpenAIEmbeddingProvider 或 OpenAI-compatible EmbeddingProvider                |
| ModelProvider     | OpenAI-compatible ChatModelProvider                                           |
| Logger            | StructuredLogger 或 OpenTelemetryLogger                                       |

## 配置项

### 基础环境

| 配置                            | 示例                    | 说明                                                         |
| ------------------------------- | ----------------------- | ------------------------------------------------------------ |
| APP_ENV                         | local                   | 运行环境                                                     |
| PROVIDER_PACK                   | local                   | provider pack 名称                                           |
| PORT                            | 3000                    | HTTP 服务端口                                                |
| ENABLE_DEBUG_TRACE              | true                    | 是否允许 debug trace                                         |
| ENABLE_SAFETY_FILTER            | true                    | 是否默认启用安全过滤                                         |
| AGENT_CONTEXT_PLANNER           | deterministic           | Agent 上下文计划器；当前支持 `deterministic`，`model` 仅预留 |
| BACKEND_CONTEXT_PROVIDER        | none                    | backend context provider；当前支持 `none`、`fake`            |
| BACKEND_CONTEXT_SOURCES         | user_profile,game_state | 本服务允许本次计划读取的业务上下文 source                    |
| BACKEND_CONTEXT_ALLOWED_SOURCES | user_profile,game_state | fake provider 白名单 source                                  |

`ENABLE_DEBUG_TRACE=false` 时，后端装配 API handler 应传入 `debug_trace_enabled=false`。该配置优先级高于请求中的 `capabilities.debug_trace=true`，用于生产环境统一关闭 debug 返回。

### `.env` 配置文件

本地 HTTP server 启动时会读取项目根目录 `.env`，也可以用 `ROLEPLAY_CONFIG_FILE` 指向其它 `.env` 文件。

仓库提供 `.env.example` 作为本地模板。复制后再填写本地密钥：

```powershell
Copy-Item .env.example .env
```

最小示例：

```env
ROLEPLAY_API_KEY=dev-secret
MODEL_PROVIDER=fake
MODEL_NAME=fake-roleplay-model
MODEL_ALIAS=fake-roleplay-model
RAG_PROVIDER=local
ENABLE_DEBUG_TRACE=true
SESSION_PROVIDER=memory
SESSION_RECENT_LIMIT=12
```

启动：

```powershell
uv run python -m haruhi_roleplay_api.infrastructure.http_server
```

读取顺序：

1. 进程环境变量。
2. `.env` 文件中的值覆盖同名进程环境变量。
3. `PATCH /v1/runtime-config` 写回 `.env`，并在当前进程内热重建 provider。

`.env` 可以保存服务端密钥，例如 `ROLEPLAY_API_KEY`、`OPENAI_API_KEY`、`DEEPSEEK_API_KEY`、`GEMINI_API_KEY`。这些值不会通过 runtime config 查询接口返回，也不能通过前端热更新接口写入。

### Runtime Config 热切换

受信任的管理前端或后台面板可以调用：

```text
GET /v1/runtime-config
PATCH /v1/runtime-config
```

这两个接口要求服务端设置 `ROLEPLAY_API_KEY`，并且请求携带 `Authorization: Bearer <key>` 或 `X-API-Key`。

示例：

```bash
curl -X PATCH http://127.0.0.1:8000/v1/runtime-config \
  -H "Authorization: Bearer dev-secret" \
  -H "Content-Type: application/json" \
  -d '{
    "values": {
      "MODEL_PROVIDER": "fake",
      "MODEL_NAME": "fake-roleplay-model",
      "MODEL_ALIAS": "fake-roleplay-model",
      "RAG_PROVIDER": "local"
    }
  }'
```

热切换会做三件事：

1. 校验 key 是否在白名单中，拒绝 `API_KEY`、`TOKEN`、`SECRET`、`PASSWORD`、`DATABASE_URL`、`REDIS_URL` 等敏感配置。
2. 用候选配置先构建新的 model router 和 RAG service。
3. 构建成功后写回 `.env`，并替换当前进程内 provider。

如果候选配置失败，例如切到 `RAG_PROVIDER=qdrant` 但没有 `QDRANT_URL`，服务会返回错误，不会写回 `.env`，也不会影响当前可用配置。

当前热切换会保留进程内 session store 和 memory store；model router、RAG service、debug trace 开关、agent planner、backend context provider 和 `SESSION_RECENT_LIMIT` 会按新配置更新。切换 RAG provider 后，非持久化本地向量数据不会自动迁移。

`GET /v1/runtime-config` 会返回两类配置 key：

- `configurable_keys`：可以通过 PATCH 热更新的非敏感配置。
- `restart_required_keys`：可以展示给管理前端，但需要重启服务才能生效的有状态配置，例如 `SESSION_PROVIDER`、`SESSION_SQLITE_PATH`。

`SESSION_PROVIDER` 不允许热切换。原因是 session store 是有状态资源，运行中从内存切到 SQLite/PostgreSQL 会让已有 session 的读写位置突然改变，容易造成会话丢失或跨库不一致。

### Agent Context Planner

`AGENT_CONTEXT_PLANNER` 控制 Orchestrator 使用哪一种上下文规划方式：

| 值            | 状态             | 说明                                                               |
| ------------- | ---------------- | ------------------------------------------------------------------ |
| deterministic | 已实现，默认值   | 不调用大模型，只按 capability 和 persona policy 生成 `ContextPlan` |
| model         | 接口预留，未实现 | 可以配置和装配，但 chat 执行时会返回 `MODEL_PROVIDER_ERROR`        |

当前确定性 planner 会生成两类安全信息：

- 调度布尔值：`readSession`、`readMemory`、`retrieveRag`。
- 安全 notes：只包含稳定标签，例如 `capability-gated`，不包含用户输入、prompt、query、URL、SQL 或 secret。

模型辅助 planner 后续会通过同一个 `AgentContextPlanner` port 接入，但必须先补齐结构化输出 schema、schema validation、权限控制、失败回退和评测集。当前不要在生产或演示配置中使用 `AGENT_CONTEXT_PLANNER=model`。

### Backend Context

Backend context 用于从业务后端或其它数据库读取受控 facts，例如用户资料、游戏状态、活动进度。当前实现的是最小 fake provider：

| 配置                            | 示例                    | 说明                                             |
| ------------------------------- | ----------------------- | ------------------------------------------------ |
| BACKEND_CONTEXT_PROVIDER        | fake                    | 支持 `none`、`fake`；默认 `none`                 |
| BACKEND_CONTEXT_SOURCES         | user_profile,game_state | Orchestrator 本次计划读取的 source，由服务端配置 |
| BACKEND_CONTEXT_ALLOWED_SOURCES | user_profile,game_state | fake provider 允许的 source 白名单               |

示例：

```env
BACKEND_CONTEXT_PROVIDER=fake
BACKEND_CONTEXT_SOURCES=user_profile,game_state
BACKEND_CONTEXT_ALLOWED_SOURCES=user_profile,game_state
```

当前 fake provider 会返回：

- `user_profile`：用户资料摘要 fact。
- `game_state`：当前活动或游戏状态 fact。

边界：

- 前端或普通用户请求不传真实 source。
- provider 只返回 `BackendContextFact`，不把业务系统原始 JSON 全量塞进 prompt。
- debug 只返回 fact 数量和 source 名称，不返回 fact 内容。
- 真实业务后端 adapter 后续应放在 `adapters/` 或独立 provider 包中，并通过同一个 `BackendContextProvider` port 注入。

### Persona

| 配置               | 示例       | 说明                  |
| ------------------ | ---------- | --------------------- |
| PERSONA_PROVIDER   | file       | persona 来源          |
| PERSONA_CONFIG_DIR | ./personas | 本地 persona 配置目录 |

### Session

| 配置                 | 示例   | 说明                                                                        |
| -------------------- | ------ | --------------------------------------------------------------------------- |
| SESSION_PROVIDER     | memory | session provider；当前已实现 `memory` / `sqlite` / `postgres` |
| SESSION_RECENT_LIMIT | 12     | 每次 chat 开启连续会话时，最多读取多少条最近 session message 进入 prompt    |
| SESSION_TTL_SECONDS  | 604800 | session 过期时间                                                            |
| SESSION_AUTO_CREATE_SCHEMA | true | SQLite / PostgreSQL 是否自动建表                                      |
| SESSION_SQLITE_PATH | .data/sessions.sqlite3 | SQLite 文件路径，建议放在已忽略的 `.data/` 下                    |
| SESSION_SQLITE_BUSY_TIMEOUT_MS | 5000 | SQLite busy timeout                                                   |
| DATABASE_URL | postgresql://... | PostgreSQL 连接串，敏感配置，只能从服务端环境或 `.env` 读取 |
| SESSION_POSTGRES_SCHEMA | public | PostgreSQL schema 名称 |
| SESSION_POSTGRES_TABLE_PREFIX | roleplay_ | PostgreSQL session 表名前缀 |
| SESSION_POSTGRES_POOL_SIZE | 5 | 预留连接池配置；当前 adapter 每次操作创建短连接 |

当前实现状态：

- 已实现 `SessionStoreSettings` 和 `build_session_store_from_env`。
- HTTP runtime 已通过 session store factory 装配，不再直接写死 `InMemorySessionStore`。
- 已实现 `SQLiteSessionStore`，使用标准库 `sqlite3`，不新增默认依赖。
- `SESSION_PROVIDER=sqlite` 会在 `SESSION_AUTO_CREATE_SCHEMA=true` 时自动创建 schema。
- `SESSION_SQLITE_PATH` 的父目录会自动创建；默认 `.data/` 已加入 `.gitignore`，避免本地数据库误提交。
- 使用同一个 SQLite 文件重新创建 runtime 后，可以继续读取已有 session 和 recent messages。
- 已实现 `PostgresSessionStore`，用于云端 session 持久化。
- `SESSION_PROVIDER=postgres` 需要服务端提供 `DATABASE_URL`，并在运行环境安装可选依赖 `psycopg` v3，例如 `uv run --with "psycopg[binary]" ...`。
- `SESSION_PROVIDER=postgres` 会在 `SESSION_AUTO_CREATE_SCHEMA=true` 时自动创建 schema、session 表、message 表和索引。
- PostgreSQL provider 错误会转换为统一 `SESSION_PROVIDER_ERROR`，不会把底层连接串或驱动错误原样返回给前端。
- `SESSION_RECENT_LIMIT` 可以通过 `PATCH /v1/runtime-config` 热更新。
- `SESSION_PROVIDER`、`SESSION_SQLITE_PATH`、`SESSION_TTL_SECONDS` 等状态相关配置只在启动装配时读取，runtime config 只展示、不热切换。
- `DATABASE_URL` 不属于 runtime config public snapshot，也不能通过 `PATCH /v1/runtime-config` 写入。

`SESSION_RECENT_LIMIT` 的作用范围：

- 只影响 `capabilities.continuous_session=true` 的 chat 请求。
- 只限制本次从 `SessionStore.recent_messages()` 读取多少条最近消息。
- 不限制 session 中实际保存的消息总数。
- 不等同于数据库分页参数，也不等同于长期记忆数量。
- 值越大，上下文更完整，但 prompt 更长、成本和延迟更高。
- 值越小，更省 token，但模型可能看不到稍早的对话。

当前没有采用 `memory.md` 式会话摘要设计。这里的判断是：session 是短期对话历史，memory 是跨会话长期事实，两者不能混在一个文件或一个 store 里。MVP 阶段直接读取最近原始消息更容易人工审核，也更容易写测试：创建 session、写入消息、读取最近 N 条即可验证。

未来可以优化为两层 session 上下文：

1. `session summary`：把较早的 session 消息压缩成滚动摘要，适合长对话。
2. `recent messages`：继续保留最近 N 条原始消息，保证角色回复能接住最近语境。

这个优化应单独拆卡实现，建议新增 `SessionSummaryStore` 或 `SessionCompactor`，并明确摘要生成策略、失败回退、摘要重建、人工可审查格式和持久化位置。不要把 session summary 写入 `MemoryStore`，也不要让普通前端直接上传或编辑 summary。

### Memory

| 配置                 | 示例   | 说明                 |
| -------------------- | ------ | -------------------- |
| MEMORY_PROVIDER      | memory | memory provider；当前已实现 `memory`，持久化 adapter 为后续能力 |
| MEMORY_READ_LIMIT    | 8      | 最多读取记忆数量     |
| MEMORY_WRITE_ENABLED | true   | 是否允许显式候选写入 |

### RAG

| 配置                     | 示例        | 说明                                                                            |
| ------------------------ | ----------- | ------------------------------------------------------------------------------- |
| RAG_PROVIDER             | local       | RAG provider；支持 `fake`、`local`、`local_vector`、`chroma`、`faiss`、`qdrant` |
| RAG_CHUNK_SIZE           | 320         | 文档切分 chunk 大小                                                             |
| RAG_EMBEDDING_DIMENSIONS | 384         | 兼容配置；未设置 `EMBEDDING_DIMENSIONS` 时作为 embedding 维度回退               |
| RAG_VECTOR_BACKEND       | memory      | `local_vector` 的本地 backend，可选 `memory`、`chroma`、`faiss`                 |
| CHROMA_COLLECTION        | haruhi_rag  | Chroma collection 名称                                                          |
| CHROMA_PERSIST_PATH      | .chroma     | Chroma 本地持久化目录，可选                                                     |
| QDRANT_URL               | https://... | Qdrant 服务地址                                                                 |
| QDRANT_COLLECTION        | haruhi_rag  | Qdrant collection 名称                                                          |
| QDRANT_API_KEY           | 可选        | Qdrant API key                                                                  |
| QDRANT_TIMEOUT_MS        | 10000       | Qdrant 请求超时                                                                 |
| QDRANT_ENSURE_COLLECTION | false       | 是否由服务尝试创建 collection                                                   |
| RAG_TOP_K_DEFAULT        | 5           | 默认检索数量                                                                    |
| RAG_TOP_K_MAX            | 10          | 最大检索数量                                                                    |

### Embedding

Embedding provider 只由服务端配置决定，前端和业务后端不能传 provider、URL 或 API key。

| 配置                  | 示例                      | 说明                                                       |
| --------------------- | ------------------------- | ---------------------------------------------------------- |
| EMBEDDING_PROVIDER    | hash                      | 支持 `hash`、`local_openai_compatible`、`ollama`、`openai` |
| EMBEDDING_MODEL       | text-embedding-3-small    | provider 侧真实 embedding 模型名                           |
| EMBEDDING_BASE_URL    | http://localhost:11434/v1 | 本地或 OpenAI-compatible embedding endpoint                |
| EMBEDDING_DIMENSIONS  | 1536                      | 向量维度；必须和向量库 collection 维度一致                 |
| EMBEDDING_TIMEOUT_MS  | 30000                     | embedding 请求超时                                         |
| EMBEDDING_API_KEY     | 可选                      | embedding provider API key；不写入前端请求                 |
| EMBEDDING_API_KEY_ENV | OPENAI_API_KEY            | 从指定环境变量读取 key                                     |
| EMBEDDING_PATH        | embeddings                | 自定义 OpenAI-compatible embeddings path                   |

本地 Ollama 示例：

```powershell
$env:RAG_PROVIDER="local_vector"
$env:EMBEDDING_PROVIDER="ollama"
$env:EMBEDDING_MODEL="nomic-embed-text"
$env:EMBEDDING_DIMENSIONS="768"
```

本地 OpenAI-compatible 示例：

```powershell
$env:RAG_PROVIDER="local_vector"
$env:EMBEDDING_PROVIDER="local_openai_compatible"
$env:EMBEDDING_BASE_URL="http://localhost:9999/v1"
$env:EMBEDDING_MODEL="local-embed"
$env:EMBEDDING_DIMENSIONS="768"
```

云端 OpenAI 示例：

```powershell
$env:RAG_PROVIDER="qdrant"
$env:EMBEDDING_PROVIDER="openai"
$env:EMBEDDING_MODEL="text-embedding-3-small"
$env:EMBEDDING_DIMENSIONS="1536"
$env:OPENAI_API_KEY="..."
```

### Model

推荐使用 `MODEL_PROVIDER_REGISTRY` 统一声明 provider 和模型别名。旧的 `MODEL_PROVIDER`、`MODEL_BASE_URL`、`MODEL_NAME` 仍然兼容，但只适合单 provider 本地验证。

| 配置                    | 示例                      | 说明                                                                                          |
| ----------------------- | ------------------------- | --------------------------------------------------------------------------------------------- |
| MODEL_PROVIDER_REGISTRY | JSON 字符串               | 推荐配置；声明 providers、aliases 和 default_alias                                            |
| MODEL_PROVIDER          | local                     | 兼容配置；支持 `fake`、`local`、`openai_compatible`、`ollama`、`deepseek`、`gemini`、`openai` |
| MODEL_ALIAS             | haruhi-ollama             | 兼容配置；暴露给前端的模型别名，不填时等于 `MODEL_NAME`                                       |
| MODEL_BASE_URL          | http://localhost:11434/v1 | OpenAI-compatible 模型服务地址                                                                |
| MODEL_NAME              | qwen2.5:7b                | provider 侧真实模型名                                                                         |
| MODEL_TIMEOUT_MS        | 60000                     | 模型超时                                                                                      |
| MODEL_API_KEY           | 可选                      | OpenAI-compatible API Key，本地无鉴权服务可不设置                                             |

Ollama local 示例：

```powershell
$env:MODEL_PROVIDER_REGISTRY='{
  "default_alias": "haruhi-ollama",
  "providers": {
    "ollama-local": {
      "type": "ollama",
      "base_url": "http://localhost:11434/v1",
      "timeout_ms": 60000
    }
  },
  "aliases": {
    "haruhi-ollama": {
      "provider": "ollama-local",
      "model": "qwen2.5:7b"
    }
  }
}'
```

前端或业务后端只能传：

```json
{
  "generation": {
    "model": "haruhi-ollama"
  }
}
```

不能传 `provider=ollama`、`base_url` 或真实 API key。未配置的 alias 会返回统一 `MODEL_PROVIDER_ERROR`。

DeepSeek / Gemini / OpenAI 示例：

```powershell
$env:DEEPSEEK_API_KEY="..."
$env:GEMINI_API_KEY="..."
$env:OPENAI_API_KEY="..."
$env:MODEL_PROVIDER_REGISTRY='{
  "default_alias": "haruhi-deepseek",
  "providers": {
    "deepseek-cloud": {
      "type": "deepseek",
      "api_key_env": "DEEPSEEK_API_KEY",
      "timeout_ms": 60000
    },
    "gemini-cloud": {
      "type": "gemini",
      "api_key_env": "GEMINI_API_KEY",
      "timeout_ms": 60000
    },
    "openai-cloud": {
      "type": "openai",
      "timeout_ms": 60000
    }
  },
  "aliases": {
    "haruhi-deepseek": {
      "provider": "deepseek-cloud",
      "model": "deepseek-chat"
    },
    "haruhi-gemini": {
      "provider": "gemini-cloud",
      "model": "gemini-3.5-flash"
    },
    "haruhi-openai": {
      "provider": "openai-cloud",
      "model": "gpt-4.1-mini"
    }
  }
}'
```

`deepseek` 默认使用 `https://api.deepseek.com/chat/completions`。`gemini` 默认使用 `https://generativelanguage.googleapis.com/v1beta/openai/chat/completions`。`openai` 默认使用 `https://api.openai.com/v1/chat/completions`，默认从 `OPENAI_API_KEY` 读取 secret。secret 通过环境变量读取，不写入前端请求，也不要写入公开文档。

#### Model Provider 实现落层

模型后端接入拆成四层，避免一个 `models.py` 随着厂商增加而无限膨胀：

| 层             | 文件                                       | 作用                                                                                    |
| -------------- | ------------------------------------------ | --------------------------------------------------------------------------------------- |
| application    | `application/models.py`                    | 只保留 `ModelProviderRegistryRouter`，根据服务端 alias 白名单选择 provider 和真实模型名 |
| ports          | `ports/models.py`                          | 定义 `ChatModelProvider` 和 `ChatModelRouter`，让 Orchestrator 不依赖具体厂商           |
| adapters       | `adapters/models/*.py`                     | 放具体 provider：`fake`、`openai_compatible`、`ollama`、`deepseek`、`gemini`、`openai`  |
| infrastructure | `infrastructure/model_registry.py`         | 解析 `MODEL_PROVIDER_REGISTRY` 和兼容环境变量                                           |
| infrastructure | `infrastructure/model_provider_factory.py` | 注册 provider factory，填充厂商默认配置，并做启动期校验                                 |

新增模型后端的最小路径：

1. 在 `adapters/models/<provider>.py` 新增薄 adapter。
2. 如果厂商兼容 OpenAI `/chat/completions`，复用 `OpenAICompatibleModelProvider`。
3. 在 `model_provider_factory.py` 注册 provider type、默认 base URL、默认 API key env 和是否必须有 secret。
4. 在 `MODEL_PROVIDER_REGISTRY` 里新增 provider 和 alias。
5. 增加 provider factory/config 测试，mock HTTP 请求，不在单元测试里调用真实云服务。

### Cloud

| 配置                  | 说明                           |
| --------------------- | ------------------------------ |
| DATABASE_URL          | PostgreSQL 连接串              |
| REDIS_URL             | Redis 连接串                   |
| QDRANT_URL            | Qdrant 地址                    |
| QDRANT_API_KEY        | Qdrant API Key                 |
| OPENAI_API_KEY        | OpenAI-compatible provider key |
| DEEPSEEK_API_KEY      | DeepSeek provider key          |
| GEMINI_API_KEY        | Gemini provider key            |
| OBJECT_STORAGE_BUCKET | 对象存储 bucket                |

不要在日志、debug trace、接口响应中输出这些敏感配置值。

## Chat 请求内部调度

收到 `POST /v1/chat` 或 `POST /v1/chat/stream` 后的推荐调度：

1. API 层校验请求字段。
2. 把 `persona_mode` 转成内部 `personaMode`。
3. AuthService 校验调用方。
4. 根据 `app_id` 读取 app 级权限。
5. 如果调用方不允许 RAG，则强制关闭 `capabilities.rag` 或返回权限错误。
6. Orchestrator 读取 CharacterProfile 和 PersonaPreset。
7. 如果 `continuousSession=true`，调用 SessionStore。
8. 如果 `memory=true`，调用 MemoryPolicyEngine 和 MemoryStore。
9. 如果 `rag=true`，调用 RagService。
10. PromptBuilder 组装 messages。
11. SafetyGuard 检查输入。
12. `ChatModelRouter` 的 `ModelProviderRegistryRouter` 实现根据 generation 和配置选择模型。
13. 非流式接口调用 `ChatModelProvider.generate`，流式接口调用 `ChatModelProvider.stream`。
14. 流式接口把 provider delta 转成统一 `delta` event，并累积完整 assistant reply。
15. SafetyGuard 检查输出。
16. SessionStore 写入完整消息。
17. 如果存在 `metadata.memory_write`，MemoryPolicyEngine 判断是否写入。
18. Logger 写入请求摘要。
19. 非流式接口返回完整响应，流式接口返回或发送 `start/source/delta/usage/done/error` events。
20. API 层把内部 `camelCase` 转成外部 `snake_case` 响应。

## 能力开关如何影响调度

| capability        | false 时              | true 时                          |
| ----------------- | --------------------- | -------------------------------- |
| continuousSession | 不读写 session 上下文 | 读最近消息，回复后写入消息       |
| rag               | 不执行 RAG            | 根据 persona filter 检索 chunks  |
| memory            | 不读写长期记忆        | 读取相关记忆，并审核显式写入候选 |
| safetyFilter      | 只做基础校验          | 执行输入和输出安全检查           |
| debugTrace        | 不返回 debug          | 返回裁剪后的调试摘要             |
| stream            | 返回完整 reply        | 返回 stream event                |

## 模型路由调度

模型选择不应该由前端直接决定 provider。

推荐策略：

| 条件                          | 模型路由                        |
| ----------------------------- | ------------------------------- |
| `APP_ENV=test`                | FakeModel                       |
| `APP_ENV=local`               | Ollama 或本地 OpenAI-compatible |
| `generation.model` 有合法别名 | 使用别名映射                    |
| RAG query rewrite             | cheap_fast_model                |
| memory policy 判断            | 当前使用规则策略，不调用模型    |
| 高质量角色扮演                | high_quality_model              |
| provider 失败                 | fallback_model                  |

`generation.model` 应该是服务端定义的模型别名，不是直接暴露真实厂商模型名。当前实现由 `ModelProviderRegistryRouter` 完成 alias 路由，由 `model_provider_factory.py` 在启动装配阶段创建具体 provider。

## 模型 Provider 产品化顺序

模型 provider 需要逐个接入，不在一个卡片里同时接多个厂商。

推荐顺序：

1. `fake`：测试和 CI。
2. `local_openai_compatible`：本地 Ollama、LM Studio、vLLM 等 OpenAI-compatible endpoint。
3. `deepseek`：云端 OpenAI-compatible 调用，单独配置 API key、model alias 和超时。
4. `gemini`：Google Gemini OpenAI compatibility 调用，单独配置 API key、model alias 和超时。
5. `openai`：云端 OpenAI-compatible 调用，单独配置 API key、model alias 和超时。
6. fallback routing：仅在基础 provider 稳定后实现。

所有 provider 都必须满足：

- 实现同一个 `ChatModelProvider` port。
- 支持非流式 `generate`。
- 支持流式 `stream`，或明确在配置校验时报错。
- provider 错误转换为统一 `AppError`。
- debug trace 只返回 provider 名称、model alias 和安全摘要。

## RAG 调度

RAG 调度需要同时看请求能力和 persona 策略：

1. `capabilities.rag` 必须为 true。
2. 当前 app 必须有 RAG 权限。
3. persona mode 必须允许 RAG。
4. 根据 persona mode 生成默认 filters。
5. 合并调用方允许的 filters。
6. 调用 RagService retrieve。
7. 返回 chunks 给 PromptBuilder。
8. 返回 source 摘要给调用方。

RAG filter 必须至少包含：

- `characterId`
- `timeline`
- `spoilerLevelMax`
- `language`

## RAG Provider 产品化顺序

RAG provider 也需要分阶段：

1. `fake`：固定 chunks，验证 Orchestrator 和 PromptBuilder 融合。
2. `local`：本地文档、chunk、简单文本检索。
3. `local_vector`：可使用 hash、Ollama、本地 OpenAI-compatible 或云端 embedding provider。
4. `chroma`：可选 Chroma backend；需要本地环境安装 `chromadb`。
5. `faiss`：可选 Faiss backend；需要本地环境安装 `faiss-cpu`。
6. `qdrant`：Qdrant REST 云端 provider。
7. rerank/query rewrite：仅在基础 retrieve 稳定后增加。

无论本地还是云端，RAG 输出都必须是统一 `RagRetrieveOutput`，并且 source 摘要必须可追溯。

推荐本地向量配置：

```powershell
$env:RAG_PROVIDER="local_vector"
$env:EMBEDDING_PROVIDER="hash"
$env:EMBEDDING_DIMENSIONS="384"
```

推荐 Qdrant 配置：

```powershell
$env:RAG_PROVIDER="qdrant"
$env:QDRANT_URL="https://your-qdrant.example"
$env:QDRANT_COLLECTION="haruhi_rag"
$env:QDRANT_API_KEY="..."
$env:QDRANT_ENSURE_COLLECTION="false"
$env:EMBEDDING_PROVIDER="openai"
$env:EMBEDDING_MODEL="text-embedding-3-small"
$env:EMBEDDING_DIMENSIONS="1536"
$env:OPENAI_API_KEY="..."
```

Chroma/Faiss 是可选本地库支持，不进入默认依赖。需要使用时先在本地环境安装对应包，再设置 `RAG_PROVIDER=chroma` 或 `RAG_PROVIDER=faiss`。

### Ollama + Chroma 手动体验入口

当前仓库提供一个最小手动 smoke 脚本，用于验证本机 `Ollama chat model + Ollama embedding + Chroma vector store + HTTP runtime` 的完整链路。该脚本不进入默认 CI，也不要求把 `chromadb` 写入默认依赖。

前置条件：

```powershell
ollama serve
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
```

运行：

```powershell
uv run --with chromadb python scripts/local_ollama_chroma_smoke.py
```

脚本会按顺序执行：

1. 检查 `chromadb` 是否可用。
2. 检查 Ollama 是否可访问，以及 chat / embedding 模型是否存在。
3. 通过 `RoleplayHttpRuntime` 调用 `GET /health`。
4. 调用 `GET /v1/personas` 读取角色 catalog。
5. 调用 `POST /v1/rag/documents` 写入一段本地资料。
6. 使用 Ollama embedding 写入 Chroma。
7. 调用 `POST /v1/rag/search` 从 Chroma 检索 source。
8. 调用 `POST /v1/chat`，启用 RAG，最终由 Ollama 生成角色回复。

可选覆盖项：

| 环境变量                     | 默认值                    | 说明                                        |
| ---------------------------- | ------------------------- | ------------------------------------------- |
| SMOKE_OLLAMA_BASE_URL        | http://localhost:11434    | Ollama 原生 API 地址，用于 `/api/tags` 预检 |
| SMOKE_OLLAMA_OPENAI_BASE_URL | http://localhost:11434/v1 | Ollama OpenAI-compatible 地址               |
| SMOKE_CHAT_MODEL             | qwen2.5:7b                | chat 模型                                   |
| SMOKE_EMBEDDING_MODEL        | nomic-embed-text:latest   | embedding 模型                              |
| SMOKE_EMBEDDING_DIMENSIONS   | 768                       | embedding 维度                              |
| SMOKE_CHROMA_COLLECTION      | haruhi_manual_smoke       | Chroma collection 名称                      |

## Memory 调度

Memory 调度需要避免污染：

1. `capabilities.memory` 必须为 true。
2. 当前 app 必须允许 memory。
3. MemoryPolicyEngine 判断是否读取。
4. MemoryStore 按 app、user、character、persona 查询。
5. PromptBuilder 只接收通过 policy 的 memory items。
6. 如果 `metadata.memory_write` 存在，MemoryPolicyEngine 判断是否写入。
7. 写入候选必须记录 type、reason、confidence。
8. 默认策略拒绝临时闲聊、敏感信息、低置信度和不被 persona 允许的类型。

## Agent 编排调度

当前 Orchestrator 已经接入“上下文计划”层。第一版使用确定性 planner，不让模型直接调用工具。

推荐链路：

1. API 层生成 `ChatInput`。
2. `AgentContextPlanner` 读取 `ChatInput`、persona policy 和 capabilities。
3. Planner 输出结构化 `ContextPlan`。
4. Orchestrator 按 plan 调用 session、memory、RAG 和 backend context ports。
5. `BackendContextProvider` 返回受控 `BackendContextFact`，不返回原始业务 JSON。
6. `PromptBuilder` 融合 persona、session、memory、RAG、backend facts 和用户消息。
7. `ChatModelRouter` 调用模型 provider，当前实现是 `ModelProviderRegistryRouter`。
8. `MemoryCandidateExtractor` 可在回复后生成候选记忆。
9. `MemoryPolicyEngine` 决定是否写入。

当前确定性 `ContextPlan` 示例：

```json
{
  "planner": "deterministic",
  "status": "ready",
  "readSession": true,
  "readMemory": true,
  "retrieveRag": true,
  "backendFetches": ["user_profile", "game_state"],
  "notes": ["capability-gated", "persona-rag-policy", "persona-memory-policy"]
}
```

基于后端大模型的 plan 当前只预留接口：

```env
AGENT_CONTEXT_PLANNER=model
```

当前状态：

- 已有 `ModelBackedAgentContextPlanner` 占位类。
- 已有 `AgentContextPlanner` port 和 factory。
- 已有 runtime config 配置入口。
- 未实现 planner prompt、模型调用、结构化输出解析、schema validation 和失败回退。
- 配置为 `model` 后发起 chat 会返回 `MODEL_PROVIDER_ERROR`，这是预期状态。

## 后端实现步骤

### 第一步：先实现 ports

先写接口，不写具体 SDK 逻辑。至少包括：

- PersonaRepository
- SessionStore
- MemoryStore
- RagService
- ChatModelRouter
- ChatModelProvider
- PromptBuilder
- SafetyGuard

### 第二步：实现 test provider

先用 FakeModel、FakeRag、InMemorySession 跑通编排。

验收重点：

- ChatInput 能到达 Orchestrator。
- capability 分支能按预期启停。
- ChatOutput 结构稳定。

### 第三步：实现 local provider

再接本地配置、本地 session、本地 RAG、本地模型。

验收重点：

- 不依赖云服务可以跑通。
- 内置角色和自定义角色 preset 可切换。
- RAG 和 memory 可独立启用。

### 第四步：实现 HTTP runtime adapter

在 framework-agnostic API handler 稳定后，再接真实 HTTP 服务。

验收重点：

- `GET /v1/personas` 可通过浏览器或 curl 调用。
- `POST /v1/chat` 返回统一 envelope。
- `POST /v1/chat/stream` 可编码为 SSE。
- HTTP 层不直接创建 provider。

当前本地 HTTP runtime adapter 已实现，默认使用标准库 `http.server`，不新增 Web 框架依赖。

启动命令：

```powershell
$env:PYTHONPATH="src"
$env:MODEL_PROVIDER="fake"
$env:MODEL_NAME="fake-roleplay-model"
$env:ROLEPLAY_PORT="8000"
uv run python -m haruhi_roleplay_api.infrastructure.http_server
```

本地验证命令：

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/v1/personas
```

最小 chat 请求：

```bash
curl -X POST http://127.0.0.1:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "app_id": "web",
    "user_id": "user-1",
    "character_id": "haruhi",
    "persona_mode": "mid_late_haruhi",
    "message": "今天有什么计划？",
    "language": "zh-CN",
    "capabilities": {
      "rag": false,
      "memory": false,
      "continuous_session": false,
      "safety_filter": true,
      "debug_trace": true,
      "stream": false
    },
    "generation": {
      "model": "fake-roleplay-model"
    }
  }'
```

SSE stream 请求：

```bash
curl -N -X POST http://127.0.0.1:8000/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "app_id": "web",
    "user_id": "user-1",
    "character_id": "haruhi",
    "persona_mode": "mid_late_haruhi",
    "message": "社团活动怎么安排？",
    "language": "zh-CN",
    "capabilities": {
      "rag": false,
      "memory": false,
      "continuous_session": false,
      "safety_filter": true,
      "debug_trace": true,
      "stream": true
    },
    "generation": {
      "model": "fake-roleplay-model"
    }
  }'
```

前端 demo 或业务后端接入时，只需要请求这些 HTTP 接口。模型、RAG、Memory、Session 的具体实现由本项目启动时的环境变量和 composition root 装配，不应该由前端传 `provider` 字段决定。

### 第五步：实现 cloud provider

最后接 PostgreSQL、Redis、Qdrant 或其它云服务。

验收重点：

- 只改配置，不改 application。
- provider 错误会转换成统一 AppError。
- debug trace 不泄露敏感配置。

### 第六步：实现 Agent planner 和 backend context

在已有 session、memory、RAG 能力稳定后，再让本项目分析请求并决定拉取哪些上下文。

验收重点：

- planner 输出结构化 plan。
- executor 只调用白名单 ports。
- debug trace 能看到 plan 摘要。
- 模型 provider 不直接访问 backend context。

当前状态：

- `AgentContextPlanner` 确定性版本已实现。
- `BackendContextProvider` port 已实现。
- `FakeBackendContextProvider` 已实现。
- `PromptBuilder` 已能插入 backend facts。
- 真实业务系统 adapter 尚未实现。

## 配置校验

服务启动时必须校验：

- provider pack 是否存在。
- 当前 pack 必需的环境变量是否完整。
- `APP_ENV=production` 时不能使用 FakeModel。
- `ENABLE_DEBUG_TRACE=true` 在生产环境必须有权限控制。
- RAG provider 和 embedding provider 维度必须匹配。
- cloud provider 的 secret 只检查是否存在，不打印值。

## 推荐本地配置

| 配置                    | 值                   |
| ----------------------- | -------------------- |
| APP_ENV                 | local                |
| PROVIDER_PACK           | local                |
| PERSONA_PROVIDER        | file                 |
| SESSION_PROVIDER        | sqlite               |
| MEMORY_PROVIDER         | memory               |
| RAG_PROVIDER            | local_vector         |
| RAG_VECTOR_BACKEND      | memory               |
| EMBEDDING_PROVIDER      | ollama               |
| EMBEDDING_MODEL         | nomic-embed-text     |
| EMBEDDING_DIMENSIONS    | 768                  |
| MODEL_PROVIDER_REGISTRY | 见 Ollama local 示例 |
| ENABLE_DEBUG_TRACE      | true                 |
| ENABLE_SAFETY_FILTER    | true                 |

当前本地推荐可以使用 `SESSION_PROVIDER=sqlite` 保存连续会话；Memory 的本地持久化 adapter 尚未实现，当前推荐仍使用 `MEMORY_PROVIDER=memory`。

## 推荐测试配置

| 配置               | 值     |
| ------------------ | ------ |
| APP_ENV            | test   |
| PROVIDER_PACK      | test   |
| SESSION_PROVIDER   | memory |
| MEMORY_PROVIDER    | memory |
| RAG_PROVIDER       | fake   |
| MODEL_PROVIDER     | fake   |
| ENABLE_DEBUG_TRACE | true   |

## 推荐生产配置

| 配置                    | 值                                 |
| ----------------------- | ---------------------------------- |
| APP_ENV                 | production                         |
| PROVIDER_PACK           | cloud                              |
| PERSONA_PROVIDER        | postgres                           |
| SESSION_PROVIDER        | postgres                           |
| DATABASE_URL            | 部署平台 secret 注入               |
| MEMORY_PROVIDER         | postgres                           |
| CACHE_PROVIDER          | redis                              |
| RAG_PROVIDER            | qdrant                             |
| QDRANT_URL              | 生产 Qdrant 地址                   |
| QDRANT_COLLECTION       | haruhi_rag                         |
| EMBEDDING_PROVIDER      | openai                             |
| EMBEDDING_MODEL         | text-embedding-3-small             |
| EMBEDDING_DIMENSIONS    | 1536                               |
| MODEL_PROVIDER_REGISTRY | 见 DeepSeek / Gemini / OpenAI 示例 |
| ENABLE_DEBUG_TRACE      | false                              |
| ENABLE_SAFETY_FILTER    | true                               |

生产配置中的 PostgreSQL session adapter 已实现；persona / memory 的 PostgreSQL adapter 仍是目标形态，后续应按同样的 ports / adapters / infrastructure 边界逐步补齐。

## 前端调用时的关键约束

- 前端只选择业务能力，不选择具体 provider。
- `debugTrace` 只能在开发环境或授权用户中启用。
- `character_id` 和 `persona_mode` 是允许前端选择的业务参数，但必须来自 catalog 白名单。
- `generation.model` 即使开放，也只能是服务端白名单别名。
- RAG 和 memory 是否可用最终由本项目和业务后端共同决定。

## 验收标准

- 同一个前端请求在 test、local、cloud pack 下走同一套 application 流程。
- 切换 provider pack 不需要改 Orchestrator。
- 关闭某个 capability 时，对应 provider 不被调用。
- provider 错误不会原样暴露给前端。
- debug trace 能说明选择了哪个 provider，但不暴露 secret。
