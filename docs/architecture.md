# Architecture

## 定位

本服务是面向前端和业务后端的 Roleplay API Orchestration Service，不是单一聊天 Bot。它负责通过 HTTP/Stream 接口接收请求，在本项目内部解析和分析用户意图，再把请求编排为角色 preset、会话上下文、RAG、记忆、业务后端上下文、prompt、模型调用和统一响应。

## 请求链路

前端 -> 业务后端 -> Roleplay API HTTP Adapter -> Orchestrator/Agent -> Ports -> Adapters -> Provider

前端只选择业务参数：

- `character_id`
- `persona_mode`
- `message`
- `session_id`
- `capabilities`
- `generation`

前端不直接选择数据库、向量库、embedding provider 或真实模型厂商。

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

| 模块                   | 职责                                                               |
| ---------------------- | ------------------------------------------------------------------ |
| PersonaRepository      | 读取 `CharacterProfile` 和 `PersonaPreset`                         |
| RoleplayOrchestrator   | 编排 persona、session、RAG、memory、backend context、prompt、model |
| AgentContextPlanner    | 分析本次请求需要哪些上下文和能力                                   |
| ContextExecutor        | 按计划调用 session、memory、RAG、业务后端 context port             |
| PromptBuilder          | 把已准备好的上下文组装成模型 messages                              |
| ModelRouter            | 根据配置选择模型 provider                                          |
| ChatModelProvider      | 调用具体模型                                                       |
| SessionStore           | 管理连续会话                                                       |
| RagService             | 文档接入和检索                                                     |
| MemoryStore            | 长期记忆存取                                                       |
| BackendContextProvider | 从业务后端或其它数据库读取受控上下文                               |
| SafetyGuard            | 输入、输出和越界检查                                               |

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

## Agent 编排定位

Agent 编排不是让模型自由调用任意工具。当前项目应采用受控 Agent：

1. `AgentContextPlanner` 根据 `ChatInput`、persona policy、capabilities 和 app 权限生成 `ContextPlan`。
2. `ContextPlan` 只能引用服务端白名单里的能力，例如 session、memory、RAG、backend context。
3. `ContextExecutor` 按 plan 调用 ports，拿到 `ContextBundle`。
4. `PromptBuilder` 把 `ContextBundle` 和 persona 信息融合成模型 messages。
5. 模型 provider 只负责生成文本，不决定数据库、RAG provider 或业务后端 URL。
6. `MemoryCandidateExtractor` 后续可以从输入和回复中生成候选记忆，再交给 `MemoryPolicyEngine` 审核。

这样可以保留 Agent 的分析能力，同时避免 provider、密钥、数据库和业务系统暴露给模型或前端。

## Provider 替换原则

- application 层只依赖 ports。
- adapter 层才允许出现具体 SDK。
- provider 类型不能泄露到 DTO。
- 切换 fake、local、cloud provider 不应修改 Orchestrator。

## 第一阶段实现建议

先实现：

- PersonaRepository 本地配置实现。
- PromptBuilder v1。
- FakeModelProvider。
- 最小 RoleplayOrchestrator。

后实现：

- SessionStore。
- RagService。
- MemoryStore。
- LocalModelProvider。
- CloudProviderPack。
- HTTP runtime adapter。
- AgentContextPlanner。
- BackendContextProvider。
- Frontend demo。
