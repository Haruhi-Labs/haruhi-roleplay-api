# 后端接入说明

## 适用场景

其它后端服务、Bot Server、游戏服务器、活动页面后端可以把本服务作为 Roleplay API 中转层调用。

## 接入前准备

1. 申请或配置 `app_id`。
2. 获取 API Key。
3. 调用 `GET /v1/personas` 或读取后端配置，确认要使用的 `character_id` 和 `persona_mode`。
4. 确认是否需要连续会话。
5. 确认是否需要 RAG 和 memory。

## 后端推荐调用流程

### 单轮对话

1. 调用方收到用户输入。
2. 生成或透传 `user_id`。
3. 调用 `POST /v1/chat`。
4. 展示或转发 `data.reply`。
5. 保存调用方自己的业务记录。

适合：

- 活动页临时对话。
- Bot 简单问答。
- 不需要上下文的角色互动。

### 连续会话

1. 调用 `POST /v1/sessions` 创建 session。
2. 保存 `session_id` 到调用方业务系统。
3. 后续每次 `POST /v1/chat` 都传 `session_id`。
4. `capabilities.continuousSession` 设置为 true。
5. 对话结束时调用 `DELETE /v1/sessions/{session_id}`。

适合：

- Web 聊天窗口。
- App 内长期对话。
- 游戏 NPC 连续交互。

### 启用 RAG

1. 先通过 `POST /v1/rag/documents` 导入资料。
2. 确认 metadata 中 `timeline`、`spoiler_level`、`character_id` 正确。
3. Chat 请求中设置 `capabilities.rag=true`。
4. 从响应 `data.rag.sources` 获取引用来源。

当前 `POST /v1/rag/documents` 最小实现只校验 metadata，不切 chunk、不写 vector index、不调用 embedding。完整检索链路需要后续 RAG retrieve 和 local RAG 步骤完成后才能启用。

适合：

- 角色设定资料。
- 时间线资料。
- 活动专属知识。
- 世界观规则。

### 启用 Memory

1. Chat 请求中设置 `capabilities.memory=true`。
2. 服务端根据策略读取相关记忆。
3. 服务端根据策略决定是否写入新记忆。
4. 调用方可通过 Memory API 展示或删除记忆。

注意：

- Memory 不是 session 消息。
- 不要把用户每句话都当成记忆。
- 删除记忆后后续请求不应继续引用。

## 推荐默认参数

| 场景 | character_id | persona_mode | rag | memory | continuousSession | temperature | styleIntensity |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 首次体验 | haruhi | entrance_haruhi | false | false | false | 0.8 | 0.75 |
| 长期聊天 | haruhi | mid_late_haruhi | true | true | true | 0.8 | 0.7 |
| 日常轻互动 | haruhi | disappearance_haruhi | false | true | true | 0.7 | 0.55 |
| 温和陪伴 | asahina_mikuru | default_mikuru | false | true | true | 0.7 | 0.55 |
| 吐槽叙述 | kyon | default_kyon | true | false | true | 0.6 | 0.6 |

## 后端错误处理建议

- `VALIDATION_ERROR`: 调用方修正参数。
- `AUTH_INVALID_API_KEY`: 检查密钥配置。
- `RATE_LIMIT_EXCEEDED`: 做重试退避或提示稍后再试。
- `SESSION_NOT_FOUND`: 重新创建 session。
- `PERSONA_NOT_FOUND`: 重新拉取 catalog 或回退到默认角色。
- `PERSONA_MODE_NOT_FOUND`: 回退到该角色的默认 persona mode。
- `MODEL_TIMEOUT`: 允许重试一次。
- `SAFETY_BLOCKED`: 向用户展示安全提示，不自动重试。

## 后端不要做什么

- 不要直接拼接系统 prompt。
- 不要绕过本服务直接调用模型并假装同一 session。
- 不要把完整用户隐私写进 metadata。
- 不要把 provider 错误原样透传给前端。
- 不要在调用方硬编码 RAG 文档过滤规则，应该通过 persona mode 和 filters 控制。

## 本项目内部如何调度具体后端实现

业务后端调用本项目时，不需要也不应该指定具体 provider。调用方只传 `app_id`、`user_id`、`character_id`、`persona_mode`、`capabilities` 和 `generation`。本项目根据启动配置、app 权限、能力开关和 persona 策略选择具体后端实现。

调度链路：

1. API Controller 接收请求。
2. AuthService 校验调用方。
3. SendChatMessageUseCase 调用 RoleplayOrchestrator。
4. Orchestrator 根据 `capabilities` 决定是否调用 SessionStore、MemoryStore、RagService。
5. ModelRouter 根据环境配置和 `generation.model` 的白名单别名选择模型。
6. 具体实现由 Provider Pack 在服务启动时注入。

详细配置和实现方式见 [中转服务后端调度与配置说明](backend-dispatch-and-configuration.md)。
