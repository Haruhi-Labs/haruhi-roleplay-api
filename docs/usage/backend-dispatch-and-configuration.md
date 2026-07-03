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

| 能力              | 实现                                         |
| ----------------- | -------------------------------------------- |
| PersonaRepository | 本地 YAML 或 JSON，包含角色和 preset catalog |
| SessionStore      | InMemory 或 SQLite                           |
| MemoryStore       | InMemory 或 SQLite                           |
| RagService        | LocalRagService                              |
| VectorIndex       | LocalVectorIndex                             |
| EmbeddingProvider | LocalEmbeddingProvider                       |
| ModelProvider     | Ollama 或本地 OpenAI-compatible              |
| Logger            | ConsoleLogger                                |

### test

用于单元测试、契约测试和 CI。

| 能力              | 实现                                             |
| ----------------- | ------------------------------------------------ |
| PersonaRepository | InMemoryPersonaRepository，包含测试角色和 preset |
| SessionStore      | InMemorySessionStore                             |
| MemoryStore       | InMemoryMemoryStore                              |
| RagService        | FakeRagService                                   |
| VectorIndex       | FakeVectorIndex                                  |
| EmbeddingProvider | FakeEmbeddingProvider                            |
| ModelProvider     | FakeModelProvider                                |
| Logger            | NoopLogger 或 TestLogger                         |

### cloud

用于生产环境。

| 能力              | 实现                                                                |
| ----------------- | ------------------------------------------------------------------- |
| PersonaRepository | PostgresPersonaRepository，存储角色和 preset catalog                |
| SessionStore      | PostgresSessionStore                                                |
| MemoryStore       | PostgresMemoryStore                                                 |
| CacheStore        | RedisCacheStore                                                     |
| RagService        | QdrantRagService、PgVectorRagService 或 OpenAIVectorStoreRagService |
| EmbeddingProvider | OpenAI-compatible EmbeddingProvider                                 |
| ModelProvider     | OpenAI-compatible ChatModelProvider                                 |
| Logger            | StructuredLogger 或 OpenTelemetryLogger                             |

## 配置项

### 基础环境

| 配置                 | 示例  | 说明                 |
| -------------------- | ----- | -------------------- |
| APP_ENV              | local | 运行环境             |
| PROVIDER_PACK        | local | provider pack 名称   |
| PORT                 | 3000  | HTTP 服务端口        |
| ENABLE_DEBUG_TRACE   | true  | 是否允许 debug trace |
| ENABLE_SAFETY_FILTER | true  | 是否默认启用安全过滤 |

`ENABLE_DEBUG_TRACE=false` 时，后端装配 API handler 应传入 `debug_trace_enabled=false`。该配置优先级高于请求中的 `capabilities.debug_trace=true`，用于生产环境统一关闭 debug 返回。

### Persona

| 配置               | 示例       | 说明                  |
| ------------------ | ---------- | --------------------- |
| PERSONA_PROVIDER   | file       | persona 来源          |
| PERSONA_CONFIG_DIR | ./personas | 本地 persona 配置目录 |

### Session

| 配置                 | 示例   | 说明             |
| -------------------- | ------ | ---------------- |
| SESSION_PROVIDER     | sqlite | session provider |
| SESSION_RECENT_LIMIT | 12     | 读取最近消息数量 |
| SESSION_TTL_SECONDS  | 604800 | session 过期时间 |

### Memory

| 配置                 | 示例   | 说明                 |
| -------------------- | ------ | -------------------- |
| MEMORY_PROVIDER      | sqlite | memory provider      |
| MEMORY_READ_LIMIT    | 8      | 最多读取记忆数量     |
| MEMORY_WRITE_ENABLED | true   | 是否允许显式候选写入 |

### RAG

| 配置               | 示例  | 说明                  |
| ------------------ | ----- | --------------------- |
| RAG_PROVIDER       | local | RAG provider          |
| VECTOR_PROVIDER    | local | vector index provider |
| EMBEDDING_PROVIDER | local | embedding provider    |
| RAG_TOP_K_DEFAULT  | 5     | 默认检索数量          |
| RAG_TOP_K_MAX      | 10    | 最大检索数量          |

### Model

推荐使用 `MODEL_PROVIDER_REGISTRY` 统一声明 provider 和模型别名。旧的 `MODEL_PROVIDER`、`MODEL_BASE_URL`、`MODEL_NAME` 仍然兼容，但只适合单 provider 本地验证。

| 配置                    | 示例                      | 说明                                                         |
| ----------------------- | ------------------------- | ------------------------------------------------------------ |
| MODEL_PROVIDER_REGISTRY | JSON 字符串               | 推荐配置；声明 providers、aliases 和 default_alias           |
| MODEL_PROVIDER          | local                     | 兼容配置；支持 `fake`、`local`、`openai_compatible`、`ollama` |
| MODEL_ALIAS             | haruhi-ollama             | 兼容配置；暴露给前端的模型别名，不填时等于 `MODEL_NAME`      |
| MODEL_BASE_URL          | http://localhost:11434/v1 | OpenAI-compatible 模型服务地址                               |
| MODEL_NAME              | qwen2.5:7b                | provider 侧真实模型名                                        |
| MODEL_TIMEOUT_MS        | 60000                     | 模型超时                                                     |
| MODEL_API_KEY           | 可选                      | OpenAI-compatible API Key，本地无鉴权服务可不设置            |

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

### Cloud

| 配置                  | 说明                           |
| --------------------- | ------------------------------ |
| DATABASE_URL          | PostgreSQL 连接串              |
| REDIS_URL             | Redis 连接串                   |
| QDRANT_URL            | Qdrant 地址                    |
| QDRANT_API_KEY        | Qdrant API Key                 |
| OPENAI_API_KEY        | OpenAI-compatible provider key |
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
12. ModelRouter 根据 generation 和配置选择模型。
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

## ModelRouter 调度

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

`generation.model` 应该是服务端定义的模型别名，不是直接暴露真实厂商模型名。

## 模型 Provider 产品化顺序

模型 provider 需要逐个接入，不在一个卡片里同时接多个厂商。

推荐顺序：

1. `fake`：测试和 CI。
2. `local_openai_compatible`：本地 Ollama、LM Studio、vLLM 等 OpenAI-compatible endpoint。
3. `deepseek`：云端 OpenAI-compatible 调用，单独配置 API key 和 base URL。
4. `openai`：云端 OpenAI-compatible 调用，单独配置 API key、model alias 和超时。
5. fallback routing：仅在基础 provider 稳定后实现。

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

1. `fake_rag`：固定 chunks，验证 Orchestrator 和 PromptBuilder 融合。
2. `local_rag`：本地文档、chunk、简单文本检索。
3. `local_vector_rag`：本地 embedding 和向量索引。
4. `cloud_rag`：Qdrant、pgvector、OpenAI Vector Store 或其它云端检索。
5. rerank/query rewrite：仅在基础 retrieve 稳定后增加。

无论本地还是云端，RAG 输出都必须是统一 `RagRetrieveOutput`，并且 source 摘要必须可追溯。

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

当前 Orchestrator 已经有确定性编排顺序。完整 Agent 编排应在这个基础上增加“上下文计划”层，而不是让模型直接调用工具。

推荐链路：

1. API 层生成 `ChatInput`。
2. `AgentContextPlanner` 读取 `ChatInput`、persona policy、capabilities 和 app 权限。
3. Planner 输出结构化 `ContextPlan`。
4. `ContextExecutor` 按 plan 调用 session、memory、RAG 和 backend context ports。
5. Executor 输出 `ContextBundle`。
6. `PromptBuilder` 融合 persona、ContextBundle 和用户消息。
7. `ModelRouter` 调用模型 provider。
8. `MemoryCandidateExtractor` 可在回复后生成候选记忆。
9. `MemoryPolicyEngine` 决定是否写入。

`ContextPlan` 示例：

```json
{
  "read_session": true,
  "read_memory": {
    "enabled": true,
    "types": ["user_preference", "relationship"],
    "limit": 5
  },
  "retrieve_rag": {
    "enabled": true,
    "query": "改写后的检索查询",
    "top_k": 5
  },
  "backend_fetches": [
    {
      "source": "user_profile",
      "required": false
    }
  ]
}
```

第一版 planner 应该用确定性规则实现。模型辅助 planner 放到后续阶段，避免一开始就引入不可控工具调用。

## 后端实现步骤

### 第一步：先实现 ports

先写接口，不写具体 SDK 逻辑。至少包括：

- PersonaRepository
- SessionStore
- MemoryStore
- RagService
- ModelRouter
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

## 配置校验

服务启动时必须校验：

- provider pack 是否存在。
- 当前 pack 必需的环境变量是否完整。
- `APP_ENV=production` 时不能使用 FakeModel。
- `ENABLE_DEBUG_TRACE=true` 在生产环境必须有权限控制。
- RAG provider 和 embedding provider 维度必须匹配。
- cloud provider 的 secret 只检查是否存在，不打印值。

## 推荐本地配置

| 配置                 | 值                        |
| -------------------- | ------------------------- |
| APP_ENV              | local                     |
| PROVIDER_PACK        | local                     |
| PERSONA_PROVIDER     | file                      |
| SESSION_PROVIDER     | sqlite                    |
| MEMORY_PROVIDER      | sqlite                    |
| RAG_PROVIDER         | local                     |
| VECTOR_PROVIDER      | local                     |
| EMBEDDING_PROVIDER   | local                     |
| MODEL_PROVIDER_REGISTRY | 见 Ollama local 示例    |
| ENABLE_DEBUG_TRACE   | true                      |
| ENABLE_SAFETY_FILTER | true                      |

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

| 配置                 | 值                |
| -------------------- | ----------------- |
| APP_ENV              | production        |
| PROVIDER_PACK        | cloud             |
| PERSONA_PROVIDER     | postgres          |
| SESSION_PROVIDER     | postgres          |
| MEMORY_PROVIDER      | postgres          |
| CACHE_PROVIDER       | redis             |
| RAG_PROVIDER         | qdrant            |
| VECTOR_PROVIDER      | qdrant            |
| EMBEDDING_PROVIDER   | openai_compatible |
| MODEL_PROVIDER       | openai_compatible |
| ENABLE_DEBUG_TRACE   | false             |
| ENABLE_SAFETY_FILTER | true              |

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
