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

| 能力 | 实现 |
| --- | --- |
| PersonaRepository | 本地 YAML 或 JSON，包含角色和 preset catalog |
| SessionStore | InMemory 或 SQLite |
| MemoryStore | InMemory 或 SQLite |
| RagService | LocalRagService |
| VectorIndex | LocalVectorIndex |
| EmbeddingProvider | LocalEmbeddingProvider |
| ModelProvider | Ollama 或本地 OpenAI-compatible |
| Logger | ConsoleLogger |

### test

用于单元测试、契约测试和 CI。

| 能力 | 实现 |
| --- | --- |
| PersonaRepository | InMemoryPersonaRepository，包含测试角色和 preset |
| SessionStore | InMemorySessionStore |
| MemoryStore | InMemoryMemoryStore |
| RagService | FakeRagService |
| VectorIndex | FakeVectorIndex |
| EmbeddingProvider | FakeEmbeddingProvider |
| ModelProvider | FakeModelProvider |
| Logger | NoopLogger 或 TestLogger |

### cloud

用于生产环境。

| 能力 | 实现 |
| --- | --- |
| PersonaRepository | PostgresPersonaRepository，存储角色和 preset catalog |
| SessionStore | PostgresSessionStore |
| MemoryStore | PostgresMemoryStore |
| CacheStore | RedisCacheStore |
| RagService | QdrantRagService、PgVectorRagService 或 OpenAIVectorStoreRagService |
| EmbeddingProvider | OpenAI-compatible EmbeddingProvider |
| ModelProvider | OpenAI-compatible ChatModelProvider |
| Logger | StructuredLogger 或 OpenTelemetryLogger |

## 配置项

### 基础环境

| 配置 | 示例 | 说明 |
| --- | --- | --- |
| APP_ENV | local | 运行环境 |
| PROVIDER_PACK | local | provider pack 名称 |
| PORT | 3000 | HTTP 服务端口 |
| ENABLE_DEBUG_TRACE | true | 是否允许 debug trace |
| ENABLE_SAFETY_FILTER | true | 是否默认启用安全过滤 |

### Persona

| 配置 | 示例 | 说明 |
| --- | --- | --- |
| PERSONA_PROVIDER | file | persona 来源 |
| PERSONA_CONFIG_DIR | ./personas | 本地 persona 配置目录 |

### Session

| 配置 | 示例 | 说明 |
| --- | --- | --- |
| SESSION_PROVIDER | sqlite | session provider |
| SESSION_RECENT_LIMIT | 12 | 读取最近消息数量 |
| SESSION_TTL_SECONDS | 604800 | session 过期时间 |

### Memory

| 配置 | 示例 | 说明 |
| --- | --- | --- |
| MEMORY_PROVIDER | sqlite | memory provider |
| MEMORY_READ_LIMIT | 8 | 最多读取记忆数量 |
| MEMORY_WRITE_ENABLED | true | 是否允许自动写入 |

### RAG

| 配置 | 示例 | 说明 |
| --- | --- | --- |
| RAG_PROVIDER | local | RAG provider |
| VECTOR_PROVIDER | local | vector index provider |
| EMBEDDING_PROVIDER | local | embedding provider |
| RAG_TOP_K_DEFAULT | 5 | 默认检索数量 |
| RAG_TOP_K_MAX | 10 | 最大检索数量 |

### Model

| 配置 | 示例 | 说明 |
| --- | --- | --- |
| MODEL_PROVIDER | ollama | 模型 provider |
| MODEL_BASE_URL | http://localhost:11434 | 模型服务地址 |
| MODEL_NAME | qwen3:8b | 默认模型 |
| MODEL_TIMEOUT_MS | 60000 | 模型超时 |

### Cloud

| 配置 | 说明 |
| --- | --- |
| DATABASE_URL | PostgreSQL 连接串 |
| REDIS_URL | Redis 连接串 |
| QDRANT_URL | Qdrant 地址 |
| QDRANT_API_KEY | Qdrant API Key |
| OPENAI_API_KEY | OpenAI-compatible provider key |
| OBJECT_STORAGE_BUCKET | 对象存储 bucket |

不要在日志、debug trace、接口响应中输出这些敏感配置值。

## Chat 请求内部调度

收到 `POST /v1/chat` 后的推荐调度：

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
13. ChatModelProvider 生成回复。
14. SafetyGuard 检查输出。
15. SessionStore 写入完整消息。
16. MemoryPolicyEngine 判断是否写入记忆。
17. Logger 写入请求摘要。
18. API 层把内部 `camelCase` 转成外部 `snake_case` 响应。

## 能力开关如何影响调度

| capability | false 时 | true 时 |
| --- | --- | --- |
| continuousSession | 不读写 session 上下文 | 读最近消息，回复后写入消息 |
| rag | 不执行 RAG | 根据 persona filter 检索 chunks |
| memory | 不读写长期记忆 | 读取相关记忆，并按 policy 写入 |
| safetyFilter | 只做基础校验 | 执行输入和输出安全检查 |
| debugTrace | 不返回 debug | 返回裁剪后的调试摘要 |
| stream | 返回完整 reply | 返回 stream event |

## ModelRouter 调度

模型选择不应该由前端直接决定 provider。

推荐策略：

| 条件 | 模型路由 |
| --- | --- |
| `APP_ENV=test` | FakeModel |
| `APP_ENV=local` | Ollama 或本地 OpenAI-compatible |
| `generation.model` 有合法别名 | 使用别名映射 |
| RAG query rewrite | cheap_fast_model |
| memory policy 判断 | cheap_fast_model |
| 高质量角色扮演 | high_quality_model |
| provider 失败 | fallback_model |

`generation.model` 应该是服务端定义的模型别名，不是直接暴露真实厂商模型名。

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

## Memory 调度

Memory 调度需要避免污染：

1. `capabilities.memory` 必须为 true。
2. 当前 app 必须允许 memory。
3. MemoryPolicyEngine 判断是否读取。
4. MemoryStore 按 app、user、character、persona 查询。
5. PromptBuilder 只接收通过 policy 的 memory items。
6. 回复完成后 MemoryPolicyEngine 判断是否写入。
7. 写入时必须记录 type、reason、confidence。

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

### 第四步：实现 cloud provider

最后接 PostgreSQL、Redis、Qdrant 或其它云服务。

验收重点：

- 只改配置，不改 application。
- provider 错误会转换成统一 AppError。
- debug trace 不泄露敏感配置。

## 配置校验

服务启动时必须校验：

- provider pack 是否存在。
- 当前 pack 必需的环境变量是否完整。
- `APP_ENV=production` 时不能使用 FakeModel。
- `ENABLE_DEBUG_TRACE=true` 在生产环境必须有权限控制。
- RAG provider 和 embedding provider 维度必须匹配。
- cloud provider 的 secret 只检查是否存在，不打印值。

## 推荐本地配置

| 配置 | 值 |
| --- | --- |
| APP_ENV | local |
| PROVIDER_PACK | local |
| PERSONA_PROVIDER | file |
| SESSION_PROVIDER | sqlite |
| MEMORY_PROVIDER | sqlite |
| RAG_PROVIDER | local |
| VECTOR_PROVIDER | local |
| EMBEDDING_PROVIDER | local |
| MODEL_PROVIDER | ollama |
| ENABLE_DEBUG_TRACE | true |
| ENABLE_SAFETY_FILTER | true |

## 推荐测试配置

| 配置 | 值 |
| --- | --- |
| APP_ENV | test |
| PROVIDER_PACK | test |
| SESSION_PROVIDER | memory |
| MEMORY_PROVIDER | memory |
| RAG_PROVIDER | fake |
| MODEL_PROVIDER | fake |
| ENABLE_DEBUG_TRACE | true |

## 推荐生产配置

| 配置 | 值 |
| --- | --- |
| APP_ENV | production |
| PROVIDER_PACK | cloud |
| PERSONA_PROVIDER | postgres |
| SESSION_PROVIDER | postgres |
| MEMORY_PROVIDER | postgres |
| CACHE_PROVIDER | redis |
| RAG_PROVIDER | qdrant |
| VECTOR_PROVIDER | qdrant |
| EMBEDDING_PROVIDER | openai_compatible |
| MODEL_PROVIDER | openai_compatible |
| ENABLE_DEBUG_TRACE | false |
| ENABLE_SAFETY_FILTER | true |

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
