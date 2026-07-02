# API Contract

## 通用响应

成功响应：

| 字段       | 说明          |
| ---------- | ------------- |
| ok         | 固定为 `true` |
| data       | 业务数据      |
| request_id | 请求 ID       |

失败响应：

| 字段          | 说明           |
| ------------- | -------------- |
| ok            | 固定为 `false` |
| error.code    | 稳定错误码     |
| error.message | 错误说明       |
| error.details | 可选调试信息   |
| request_id    | 请求 ID        |

## Chat

### POST /v1/chat

发送一次非流式角色扮演请求。

请求字段：

| 字段         | 必填 | 说明          |
| ------------ | ---- | ------------- |
| app_id       | 是   | 调用方应用 ID |
| user_id      | 是   | 调用方用户 ID |
| session_id   | 否   | 连续会话 ID   |
| character_id | 是   | 角色 ID       |
| persona_mode | 是   | 角色 preset   |
| message      | 是   | 用户输入      |
| language     | 是   | 输出语言      |
| capabilities | 是   | 能力开关      |
| generation   | 否   | 生成参数      |

当 `capabilities.continuous_session=true` 时，`session_id` 必须来自 `POST /v1/sessions` 创建的 active session，并且与当前 `app_id`、`user_id`、`character_id`、`persona_mode` 匹配。

当 `capabilities.rag=true` 时，服务端必须已注入 `RagService`。当前实现支持 Fake RAG retrieve，用 persona policy 过滤固定 chunks，并返回 source 摘要；真实 embedding、向量库和 rerank 尚未接入。

响应字段：

| 字段         | 说明        |
| ------------ | ----------- |
| request_id   | 请求 ID     |
| session_id   | 会话 ID     |
| character_id | 角色 ID     |
| persona_mode | 角色 preset |
| reply        | 回复文本    |
| usage        | 模型用量    |
| rag          | RAG 摘要    |
| memory       | 记忆摘要    |
| debug        | 调试摘要    |

`rag` 字段：

| 字段               | 说明                      |
| ------------------ | ------------------------- |
| enabled            | 是否执行 RAG              |
| provider           | RAG provider 名称         |
| hit_count          | 返回给 PromptBuilder 的数 |
| raw_hit_count      | provider 原始候选数       |
| filtered_hit_count | metadata 过滤后候选数     |
| sources            | source 摘要列表           |

`sources` 至少包含 `document_id`、`chunk_id`、`source_type`、`character_id`、`timeline`、`spoiler_level`、`language` 和 `score`。

当 `capabilities.debug_trace=true` 且服务端允许返回 debug 时，`debug` 只返回安全摘要：

| 字段                | 说明                       |
| ------------------- | -------------------------- |
| requestId           | 请求 ID                    |
| characterId         | 角色 ID                    |
| personaMode         | 角色 preset                |
| personaSource       | persona 来源摘要           |
| sessionEnabled      | 是否启用连续会话           |
| sessionReadCount    | 本次读取的最近会话消息数量 |
| memoryEnabled       | 是否启用长期记忆           |
| memoryReadCount     | 本次读取的记忆数量         |
| memoryWriteCount    | 本次写入的记忆数量         |
| ragEnabled          | 是否启用 RAG               |
| ragProvider         | RAG provider 摘要          |
| ragRawHitCount      | RAG 原始命中数量           |
| ragFilteredHitCount | RAG 过滤后命中数量         |
| modelProvider       | 模型 provider              |
| modelRoute          | 实际模型路由结果           |
| safetyEnabled       | 是否启用安全检查           |
| safetyAction        | 安全处理动作               |
| latencyMs           | 请求总耗时毫秒             |
| events              | 请求阶段名称列表           |

`debug` 不返回完整 prompt、完整用户输入、完整模型输出、secret、连接串或原始 RAG 文档。

## Persona

### GET /v1/personas

返回前端可展示的角色和 preset catalog。

响应字段：

| 字段       | 说明     |
| ---------- | -------- |
| characters | 角色列表 |

character 字段：

| 字段                 | 说明             |
| -------------------- | ---------------- |
| character_id         | 角色 ID          |
| display_name         | 展示名           |
| description          | 简短说明         |
| default_persona_mode | 默认 preset      |
| tags                 | 前端筛选标签     |
| modes                | 可选 preset 摘要 |

### GET /v1/personas/{character_id}/modes

返回指定角色的可用 preset。

## Session

### POST /v1/sessions

创建连续会话。

### GET /v1/sessions/{session_id}

查询 session 状态。

### DELETE /v1/sessions/{session_id}

关闭 session。

## RAG

### POST /v1/rag/documents

校验 RAG 文档 metadata。当前最小实现不切 chunk、不写 vector index、不调用 embedding。

请求字段：

| 字段          | 必填 | 说明                                                  |
| ------------- | ---- | ----------------------------------------------------- |
| app_id        | 是   | 调用方应用                                            |
| document_id   | 否   | 文档 ID；不传由服务端生成                             |
| title         | 是   | 文档标题                                              |
| source_type   | 是   | 来源类型，必须符合 persona 的 `ragPolicy.sourceTypes` |
| character_id  | 是   | 角色 ID                                               |
| persona_mode  | 否   | 模式专属文档                                          |
| timeline      | 是   | 时间线，必须符合 persona policy                       |
| spoiler_level | 是   | 剧透等级，不能超过 persona policy                     |
| language      | 是   | `zh-CN`、`ja-JP`、`en-US`                             |
| content       | 是   | 文档文本或解析后文本                                  |
| metadata      | 否   | 扩展 metadata                                         |

响应字段：

| 字段        | 说明                       |
| ----------- | -------------------------- |
| document_id | 文档 ID                    |
| status      | `validated` 或 `imported`  |
| chunk_count | 写入的 chunk 数量          |
| metadata    | 通过校验后的 metadata 摘要 |

未注入本地 ingest provider 时只返回 `validated`，用于 metadata 校验。注入 `LocalRagService` 时返回 `imported`，服务会按文本切分 chunk 并保留 metadata。当前本地检索使用简单文本匹配，不做 embedding、向量库或 rerank。

### POST /v1/rag/search

调试 RAG 检索。

## Memory

### GET /v1/memory/{user_id}

查询用户记忆。

### DELETE /v1/memory/{user_id}/{memory_id}

删除指定记忆。

## 错误码

| 错误码                 | 说明               |
| ---------------------- | ------------------ |
| VALIDATION_ERROR       | 参数错误           |
| AUTH_INVALID_API_KEY   | API Key 无效       |
| AUTH_PERMISSION_DENIED | 权限不足           |
| PERSONA_NOT_FOUND      | 角色不存在         |
| PERSONA_MODE_NOT_FOUND | preset 不存在      |
| SESSION_NOT_FOUND      | session 不存在     |
| RAG_PROVIDER_ERROR     | RAG provider 失败  |
| MODEL_PROVIDER_ERROR   | 模型 provider 失败 |
| MODEL_TIMEOUT          | 模型超时           |
| SAFETY_BLOCKED         | 安全策略阻断       |
| INTERNAL_ERROR         | 内部错误           |

## 字段命名

- 对外 HTTP API 使用 `snake_case`。
- 内部 application/domain DTO 使用 `camelCase`。
- API 层负责转换。

详细字段以 `docs/usage/interface-reference.md` 为准。
