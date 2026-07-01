# Architecture

## 定位

本服务是 Roleplay API Orchestration Service，不是单一聊天 Bot。它负责把前端或业务后端请求编排为角色 preset、会话上下文、RAG、记忆、prompt、模型调用和统一响应。

## 请求链路

前端 -> 业务后端 -> Roleplay API -> Orchestrator -> Ports -> Adapters -> Provider

前端只选择业务参数：

- `character_id`
- `persona_mode`
- `message`
- `session_id`
- `capabilities`
- `generation`

前端不直接选择数据库、向量库、embedding provider 或真实模型厂商。

## 分层

| 层 | 职责 |
| --- | --- |
| api | HTTP / Stream 入口，做参数校验和响应映射 |
| application | Use case 和 Orchestrator |
| domain | DTO、实体、值对象和策略名词 |
| ports | 外部能力接口 |
| adapters | provider 的具体实现 |
| infrastructure | 配置、依赖注入、启动 |

## 核心模块

| 模块 | 职责 |
| --- | --- |
| PersonaRepository | 读取 `CharacterProfile` 和 `PersonaPreset` |
| RoleplayOrchestrator | 编排 persona、session、RAG、memory、prompt、model |
| PromptBuilder | 把已准备好的上下文组装成模型 messages |
| ModelRouter | 根据配置选择模型 provider |
| ChatModelProvider | 调用具体模型 |
| SessionStore | 管理连续会话 |
| RagService | 文档接入和检索 |
| MemoryStore | 长期记忆存取 |
| SafetyGuard | 输入、输出和越界检查 |

角色字段的含义见 `character-schema.md`。其中 `ToneConfig`、`IdentityConfig`、`KnowledgeBoundary` 会被 Orchestrator 读取，并由 PromptBuilder 融合进模型上下文。

## Prompt 融合点

RAG、memory、session 不直接调用模型。它们先由 Orchestrator 读取，再交给 PromptBuilder 统一融合。

PromptBuilder 的推荐顺序：

1. 系统安全边界。
2. character 基础身份。
3. persona preset 语气和行为规则。
4. 时间线和知识边界。
5. session summary。
6. recent messages。
7. memory items。
8. RAG chunks。
9. 当前用户消息。

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
