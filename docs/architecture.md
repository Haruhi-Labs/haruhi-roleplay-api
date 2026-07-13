# Architecture

## 定位

本服务是面向前端和业务后端的 Roleplay API Orchestration Service，不是单一聊天 Bot。它负责通过 HTTP/Stream 接口接收请求，在本项目内部解析和分析用户意图，再把请求编排为角色 preset、会话上下文、RAG、记忆、业务后端上下文、prompt、模型调用和统一响应。

## 请求链路

前端 -> 业务后端 -> Roleplay API HTTP Adapter -> Orchestrator/Agent -> Ports -> Adapters -> Provider

HTTP Adapter 在进入 Orchestrator 前完成 `ROLEPLAY_API_KEY` 或服务 Access Token 鉴权与聊天额度预检。普通 JSON 响应返回前结算用量；SSE 响应由惰性事件包装器在流消费完成后结算，避免鉴权和审计逻辑破坏端到端流式输出。

服务 Access Token 绑定单一 `app_id`。HTTP runtime 在 DTO handler、RAG/session/memory provider 和模型调用前统一比较 body/query 中的 `app_id`；不匹配和 legacy unscoped token 返回 `AUTH_PERMISSION_DENIED`，并记录不含正文的拒绝审计。`ROLEPLAY_API_KEY` 代表管理主体，不受服务 token scope 限制。

RAG 还在存储层执行独立的 app 隔离。文档导入时，顶层 `app_id` 会写入每个 chunk 的 metadata；local、内存向量和 Faiss 在统一 metadata filter 中比较 app，Chroma 和 Qdrant 同时在持久化 payload 与查询 filter 中使用 `app_id`。内部 chunk/point ID 也包含 app scope，因此不同应用可以使用相同的公开 `document_id`，但不会覆盖或检索到彼此的数据。缺少 `app_id` 的旧向量记录不会自动归属或参与检索。

HTTP runtime 还提供最小资源边界。标准库 server 在读取请求体前检查 `Content-Length`，超过 1 MiB 直接返回 413；runtime 对直接 adapter 调用执行同一字节检查。Chat/RAG domain DTO 再限制消息、文档、ID、`max_tokens` 和 `top_k`，并严格要求 JSON boolean，确保超限请求在 session、RAG、memory 和模型 provider 调用前失败。当前使用集中代码常量，不引入分布式 rate limit 或额外配置面。

前端只选择业务参数：

- `character_id`
- `persona_mode`
- `message`
- `session_id`
- 真正启用的 `capabilities`
- 高级调用方可选的 `generation`

普通前端不直接选择数据库、向量库、embedding provider、真实模型厂商或 model alias；省略 generation 时由 model router 选择 default alias。

## 分层

| 层             | 职责                                     |
| -------------- | ---------------------------------------- |
| api            | HTTP / Stream 入口，做参数校验和响应映射 |
| application    | Use case 和 Orchestrator                 |
| domain         | DTO、实体、值对象和策略名词              |
| ports          | 外部能力接口                             |
| adapters       | provider 的具体实现                      |
| infrastructure | 配置、依赖注入、启动                     |

更完整的分层含义、依赖方向和开发加入方式见 `layered-architecture.md`。

## 核心模块

| 模块                        | 职责                                                               |
| --------------------------- | ------------------------------------------------------------------ |
| PersonaRepository           | 读取 `CharacterProfile` 和 `PersonaPreset`                         |
| RoleplayOrchestrator        | 编排 persona、session、RAG、memory、backend context、prompt、model |
| AgentContextPlanner         | 分析本次请求需要哪些上下文和能力                                   |
| ContextExecutor             | 按计划调用 session、memory、RAG、业务后端 context port             |
| PromptBuilder               | 把已准备好的上下文组装成模型 messages                              |
| ChatModelRouter             | application 依赖的模型路由 port                                    |
| ModelProviderRegistryRouter | 根据服务端 alias 白名单选择模型 provider                           |
| ChatModelProvider           | 调用具体模型                                                       |
| SessionStore                | 管理连续会话                                                       |
| SessionStoreFactory         | 根据服务端配置装配 session store，并暴露 session 运行参数          |
| RagService                  | 文档接入和检索                                                     |
| TextEmbeddingProvider       | 把文本转成向量，供本地/云端 RAG provider 使用                      |
| MemoryStore                 | 长期记忆存取                                                       |
| BackendContextProvider      | 从业务后端或其它数据库读取受控上下文                               |
| SafetyGuard                 | 规划中的输入、输出和越界检查；当前尚未接入请求链路                 |
| AccessTokenStore            | 服务令牌 app scope、校验、额度核算和逐令牌审计日志                   |

角色字段的含义见 `character-schema.md`。其中 `ToneConfig`、`IdentityConfig`、`KnowledgeBoundary` 会被 Orchestrator 读取，并由 PromptBuilder 融合进模型上下文。

## Prompt 融合点

RAG、memory、session 和业务后端 context 不直接调用模型。它们先由 Orchestrator 或 ContextExecutor 读取，再交给 PromptBuilder 统一融合。

PromptBuilder 的推荐顺序：

1. 系统安全边界。
2. character 基础身份。
3. persona preset 语气和行为规则。
4. 时间线和知识边界。
5. session summary。
6. recent messages。
7. memory items。
8. RAG chunks。
9. backend context facts。
10. 当前用户消息。

当前 session 上下文只实现 `recent messages`，尚未实现 `session summary`。`SESSION_RECENT_LIMIT` 控制每次 chat 最多读取多少条最近会话消息进入 prompt，用于限制 prompt 长度、成本和延迟。

暂时不做 `memory.md` 式滚动摘要或会话笔记，原因是它会引入额外的摘要生成、摘要更新时机、过期纠错和持久化一致性问题；当前 MVP 更需要可审核、可回放的原始 recent messages。后续可以在 `SessionStore` 之外增加 `SessionSummaryStore` 或 `SessionCompactor`，把旧消息压缩成 session summary，再按“session summary -> recent messages -> memory items”的顺序融合进 PromptBuilder。

## Agent 编排定位

Agent 编排不是让模型自由调用任意工具。当前项目应采用受控 Agent：

1. `AgentContextPlanner` 根据 `ChatInput`、persona policy、capabilities 和 app 权限生成 `ContextPlan`。
2. `ContextPlan` 只能引用服务端白名单里的能力，例如 session、memory、RAG、backend context。
3. `ContextExecutor` 按 plan 调用 ports，拿到 `ContextBundle`。
4. `PromptBuilder` 把 `ContextBundle` 和 persona 信息融合成模型 messages。
5. 模型 provider 只负责生成文本，不决定数据库、RAG provider 或业务后端 URL。
6. `MemoryCandidateExtractor` 后续可以从输入和回复中生成候选记忆，再交给 `MemoryPolicyEngine` 审核。

这样可以保留 Agent 的分析能力，同时避免 provider、密钥、数据库和业务系统暴露给模型或前端。

### 当前实现状态

当前已实现 `AgentContextPlanner` 的确定性版本：

- 默认配置：`AGENT_CONTEXT_PLANNER=deterministic`。
- 输出：`ContextPlan`，包含是否读取 session、memory、RAG、backend context 以及安全 notes。
- 调度：`RoleplayOrchestrator` 根据 `ContextPlan` 决定是否读取 session、memory、RAG 和 backend context。
- Debug：`debug.contextPlan` 返回安全摘要，不包含用户原文、prompt、query、URL、SQL 或 secret。

当前也已实现最小 `BackendContextProvider`：

- 默认配置：`BACKEND_CONTEXT_PROVIDER=none`，不读取业务后端上下文。
- 本地实现：`BACKEND_CONTEXT_PROVIDER=fake`，可返回 `user_profile` 和 `game_state` 两类示例 fact。
- Source 配置：`BACKEND_CONTEXT_SOURCES=user_profile,game_state`，由服务端配置决定，普通前端不传真实 source。
- Prompt 融合：`PromptBuilder` 将 `BackendContextFact` 插入“业务后端上下文摘要”段。
- Debug：只返回 `backendContextFactCount` 和 `backendContextSources`，不返回 fact 内容或原始业务 JSON。

当前 session store 装配状态：

- 简单配置和项目模板默认：`SESSION_PROVIDER=sqlite`；显式设置 `memory` 仍可用于无持久化测试。
- 已实现：`SessionStoreSettings` 和 `build_session_store_from_env`，HTTP runtime 不再直接创建 `InMemorySessionStore`。
- 本地持久化：`SESSION_PROVIDER=sqlite` 已可用，使用标准库 `sqlite3` 和 `SQLiteSessionStore` 保存 session / session messages。
- 云端持久化：`SESSION_PROVIDER=postgres` 已可用，使用可选 `psycopg` v3 和 `PostgresSessionStore` 保存 session / session messages。
- 已接入：`SESSION_RECENT_LIMIT` 控制 Orchestrator 读取最近消息数量，并可通过 runtime config 热更新。
- 只展示不热切换：`SESSION_PROVIDER`、`SESSION_SQLITE_PATH`、`SESSION_TTL_SECONDS`、`SESSION_POSTGRES_SCHEMA` 等有状态配置会出现在 runtime config 的 `restart_required_keys`，但不能通过 `PATCH /v1/runtime-config` 热切换。
- 敏感边界：`DATABASE_URL` 只从服务端环境或 `.env` 读取，不进入 runtime config public snapshot、debug trace 或普通前端请求。

当前 memory store 装配状态：

- 简单配置和项目模板默认：`MEMORY_PROVIDER=sqlite`；显式设置 `memory` 仍可使用进程内实现。
- 已实现：`MemoryStoreSettings` 和 `build_memory_store_from_env`，HTTP runtime 不再直接创建 `InMemoryMemoryStore`。
- 本地持久化：`MEMORY_PROVIDER=sqlite` 已可用，使用标准库 `sqlite3` 和 `SQLiteMemoryStore` 保存长期 memory。
- 只展示不热切换：`MEMORY_PROVIDER`、`MEMORY_SQLITE_PATH`、`MEMORY_SQLITE_BUSY_TIMEOUT_MS` 是有状态配置，会出现在 runtime config 的 `restart_required_keys`，但不能通过 `PATCH /v1/runtime-config` 热切换。

当前配置管理边界：

- 普通聊天前端不访问 runtime config。
- `GET /v1/runtime-config` 和 `PATCH /v1/runtime-config` 只负责非敏感热更新配置。
- 受信任 `.env` 编辑器通过独立 Env Config Editor API 查看 redacted `.env` 摘要、字段 check、草稿 diff 和写回 `.env`。
- `.env` 编辑器可以设置 secret 和 restart-required 字段，但响应只能返回 secret 状态，不能回显原文。
- `.env` 编辑器中的“创建”表示创建 `.env` 配置草稿，不表示创建 provider、数据库或云端资源。
- restart-required 字段保存后只写入 `.env`，需要重启服务才能完整生效。
- 本地受信任页面入口是 `/config`，普通聊天 demo 不提供该入口。
- `/config` 默认只显示 Simple LLM、Simple Embedding、Simple RAG、HTTP 和 Storage essentials；legacy provider、registry、planner 和数据库参数进入折叠的 Advanced。
- `MODEL_PROVIDER_REGISTRY` 优先于 simple LLM facade；简单配置只生成内部 alias，不要求用户额外填写 `MODEL_ALIAS`。

同时预留了基于后端大模型的 planner：

- 配置入口：`AGENT_CONTEXT_PLANNER=model`。
- 当前状态：只保留 port、factory 和占位 planner，未实现真实模型规划。
- 当前行为：如果配置为 `model` 并发起 chat，会返回 `MODEL_PROVIDER_ERROR`，提示 model-backed planner 未实现。
- 后续实现前提：需要先定义 planner prompt、结构化输出 schema、权限边界、失败回退和评测集。

## Provider 替换原则

- application 层只依赖 ports。
- adapter 层才允许出现具体 SDK。
- provider 类型不能泄露到 DTO。
- 切换 fake、local、cloud provider 不应修改 Orchestrator。
- `application/models.py` 只保留 registry 路由逻辑，不写具体厂商构造。
- `infrastructure/model_registry.py` 只解析 `MODEL_PROVIDER_REGISTRY` 和兼容环境变量。
- `infrastructure/model_provider_factory.py` 负责 provider factory 注册、默认 URL/API key env 和启动期校验。
- 每个模型厂商放在 `adapters/models/<provider>.py`，共享 OpenAI-compatible 逻辑时继承或包装 `openai_compatible.py`。
- embedding provider 通过 `ports/embeddings.py`、`adapters/embeddings/` 和 `infrastructure/embedding_provider_factory.py` 独立装配，再注入 RAG provider。

## 当前实现边界

已形成可运行闭环：persona catalog、PromptBuilder、模型 provider 路由、session、RAG、memory、deterministic planner、HTTP/SSE runtime、前端 demo、配置编辑器和 Docker Compose。

尚未实现的主要边界：

- 规则型 `SafetyGuard`。
- `BackendContextProvider` 的真实业务后端 adapter。
- model-backed Agent planner。
- session summary / compaction。
- 额外公开角色和 persona preset。

后续优先级以 `roadmap.md` 和 `docs/agent-dev/cards/00.00.cards-index.md` 为准。
