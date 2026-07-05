# Roleplay API 设计规范

## 设计定位

本服务是 Roleplay API Orchestration Service，不是单一聊天 Bot。它把调用方请求统一编排为 persona、session、memory、RAG、prompt、model、safety 和 response。

## 架构原则

1. 业务层不直接依赖云 SDK。
2. 所有外部能力必须通过 port。
3. adapter 可以替换，port 契约要稳定。
4. composition root 是唯一绑定具体实现的位置。
5. DTO、domain entity、database row 分离。
6. PromptBuilder 不查数据，只组织上下文。
7. RAG、Memory、Session 是三个不同能力，不混用。
8. 角色和 preset 必须可配置，并且必须有时间线和知识边界。
9. HTTP 运行层只负责协议和响应格式，不写业务编排。
10. Agent 只能通过白名单 port 调度上下文，不能直接拼 URL、SQL 或 provider 参数。
11. 前端 demo 只验证接入体验，不承担业务后端、安全策略或 provider 配置职责。

## 推荐分层

| 层             | 职责                       | 是否允许外部 SDK              |
| -------------- | -------------------------- | ----------------------------- |
| domain         | 核心实体、值对象、策略名词 | 不允许                        |
| application    | use case 和 orchestrator   | 不允许                        |
| ports          | 接口定义                   | 不允许                        |
| adapters       | 外部服务实现               | 允许                          |
| infrastructure | 配置、启动、依赖注入       | 允许                          |
| api            | HTTP、SSE、WebSocket 入口  | 只依赖 application            |
| tests          | 单元、集成、契约、评测     | 按测试类型决定                |
| frontend-demo  | 最简接入示例               | 只调用业务后端或本地 demo API |

## 依赖方向

允许：

- api -> application
- application -> domain
- application -> ports
- adapters -> ports
- infrastructure -> adapters
- infrastructure -> application

禁止：

- domain -> adapters
- application -> adapters
- application -> model SDK
- application -> vector DB SDK
- application -> ORM entity
- PromptBuilder -> SessionStore
- MemoryStore -> ModelProvider

## Persona 设计规范

- 角色必须通过 `character_id` 参数选择。
- 角色 preset 必须通过 `persona_mode` 参数选择。
- 前端必须通过 catalog 接口读取可用角色和 preset，不能硬编码三种春日模式。
- 每个 preset 必须定义 timeline。
- 每个 preset 必须定义 allowed timelines 和 spoiler max。
- 角色语气用参数和规则控制，不依赖长段原文台词。
- 不复刻长段版权文本。
- 不主动暴露系统设定或内部 prompt。
- 自定义角色必须经过配置校验后才允许暴露给前端。
- 新增角色不能要求改 Orchestrator 或 ModelProvider。

## Capability 设计规范

| 能力              | 规则                                 |
| ----------------- | ------------------------------------ |
| rag               | 默认关闭，开启后必须返回 source 摘要 |
| memory            | 默认关闭，开启后必须经过 policy      |
| continuousSession | 默认关闭，开启后读写 session         |
| safetyFilter      | 默认开启                             |
| debugTrace        | 本地可开启，生产必须裁剪敏感信息     |
| stream            | 只改变输出方式，不改变编排语义       |

## HTTP API 运行层规范

- 对外入口优先实现 `GET /v1/personas`、`POST /v1/sessions`、`POST /v1/chat`、`POST /v1/chat/stream`、RAG ingest/search、memory query/delete。
- HTTP adapter 只做 request/response 映射、SSE 编码、错误 envelope 和 request id。
- HTTP adapter 不直接创建具体 provider。
- SSE event 必须来自 application 层的统一 stream event，不在 HTTP 层重组业务字段。
- 本地 demo 可以直连本项目本地 HTTP 服务；真实产品前端必须经过业务后端。

## RAG 设计规范

- 所有 RAG chunk 必须有 metadata。
- metadata 至少包含 `characterId`、`timeline`、`spoilerLevel`、`language`、`sourceType`。
- retrieve 必须先按角色和时间线过滤。
- source 必须能追溯到 documentId 和 chunkId。
- RAG 不写 session，不写 memory。
- 本地 RAG 和云端 RAG 必须共享同一个 `RagService` port。
- 云端 RAG provider 只出现在 adapter/infrastructure 层。
- 先实现 provider smoke test，再接 rerank 和复杂 query rewrite。

## Memory 设计规范

- 记忆不是聊天记录。
- 写入记忆必须经过 MemoryPolicy。
- 用户可以删除记忆。
- persona mode 专属记忆不能污染其它模式。
- 不保存敏感个人信息，除非产品策略明确允许且用户授权。
- 自动候选生成必须和写入策略分离：Extractor 只生成候选，Policy 决定是否写入。

## Agent 编排规范

- Agent planner 的输出必须是结构化 `ContextPlan`，不能是自由文本指令。
- `ContextPlan` 只能包含白名单 source，例如 `session`、`memory`、`rag`、`backend_context`。
- ContextExecutor 负责执行 plan，模型 provider 不直接访问工具。
- planner v1 优先使用确定性规则，不先依赖大模型自我规划。
- 模型辅助 planner 只能作为后续增强，并且必须保留可观测 debug trace。
- agent debug 只能返回计划摘要、source 数量和阶段，不返回完整 prompt、secret 或原始业务数据。

## API 设计规范

- 所有响应带 requestId。
- 错误响应使用稳定 error.code。
- 对外 HTTP API 字段统一使用 `snake_case`，例如 `persona_mode`、`session_id`。
- 内部 application/domain DTO 字段统一使用 `camelCase`，例如 `personaMode`、`sessionId`。
- API 层负责 `snake_case` 和 `camelCase` 的转换，转换不能泄露到 domain。
- 对外字段不能出现 SDK 专属类型。
- debug 字段不返回完整 prompt、密钥、完整 RAG 文档。

## Done Definition

一个能力完成必须满足：

- 接口文档已更新。
- 入参、出参、错误码清楚。
- 能力开关行为清楚。
- 本地 provider 或 test provider 可验证。
- 不破坏已有契约。
- 不绕过 ports。

## Provider 调度规范

- 前端和业务后端只传业务参数，不直接选择具体 provider。
- 具体 provider 由 Provider Pack 在启动时注入。
- 调度依据依次是环境配置、app 权限、capabilities、persona policy、generation 白名单和 fallback 策略。
- Orchestrator 运行时只调用 ports，不创建具体 adapter。
- `generation.model` 只能是服务端白名单模型别名，不能直接等同于厂商模型名。
- debug trace 可以返回 provider 名称，但不能返回 secret、连接串或完整 prompt。

## 前端 Demo 规范

- Demo 首屏就是聊天体验，不做营销页。
- 必须支持角色和 preset catalog 选择。
- 必须支持非流式和流式两种调用。
- 必须能展示 RAG source 摘要。
- 可以展示开发者 debug 面板，但默认折叠。
- 不在前端保存 API key。
- 优先使用项目内约定的 Haruhi UI 风格；如果引入外部框架，只能作为 demo 工程依赖，不能反向污染 API 核心层。

