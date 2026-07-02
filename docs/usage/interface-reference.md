# Interface Reference

## 通用约定

Base URL 由部署环境决定，文档中统一写作 `{base_url}`。

所有请求建议携带：

| Header | 说明 |
| --- | --- |
| Authorization | API Key 或 Bearer Token |
| Content-Type | `application/json` |
| X-Request-Id | 可选，调用方生成的请求 ID |

所有响应建议使用统一结构：

| 字段 | 说明 |
| --- | --- |
| ok | true 或 false |
| data | 成功时返回 |
| error | 失败时返回 |
| requestId | 请求追踪 ID |

## Chat: POST /v1/chat

用途：发送一次非流式角色扮演请求。

### 请求参数

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| app_id | 是 | 调用方应用 ID |
| user_id | 是 | 调用方用户 ID |
| session_id | 否 | 连续会话 ID |
| character_id | 是 | 角色 ID，例如 `haruhi`、`asahina_mikuru`、`kyon` |
| persona_mode | 是 | 角色 preset，例如 `entrance_haruhi` |
| message | 是 | 用户输入 |
| language | 是 | `zh-CN`、`ja-JP`、`en-US` |
| capabilities | 是 | 能力开关 |
| generation | 否 | 模型生成参数 |
| metadata | 否 | 调用方透传对象 |

### capabilities

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| rag | boolean | 是否启用 RAG |
| memory | boolean | 是否启用长期记忆 |
| continuous_session | boolean | 是否启用连续会话 |
| safety_filter | boolean | 是否启用安全检查 |
| debug_trace | boolean | 是否返回调试信息 |
| stream | boolean | 非流式接口通常为 false |

当前最小 `/v1/chat` 实现支持非流式请求和连续会话。`continuous_session=true` 时必须传入 `session_id`，且 session 必须匹配同一个 `app_id`、`user_id`、`character_id` 和 `persona_mode`。`rag`、`memory`、`stream` 当前仍必须为 false。

### generation

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| model | string | 模型别名 |
| temperature | number | 随机性 |
| max_tokens | number | 最大输出 token |
| top_p | number | nucleus sampling 参数 |
| presence_penalty | number | 话题重复惩罚 |
| frequency_penalty | number | 词频重复惩罚 |
| style_intensity | number | 角色演绎强度，0 到 1 |
| allow_narration | boolean | 是否允许旁白 |

### 响应 data

| 字段 | 说明 |
| --- | --- |
| request_id | 请求 ID |
| session_id | 会话 ID |
| character_id | 角色 ID |
| persona_mode | 角色 preset |
| reply | 回复文本 |
| usage | 模型和 token 使用 |
| rag | RAG 结果摘要 |
| memory | 记忆结果摘要 |
| safety | 安全检查结果 |
| debug | 调试信息 |

`debug_trace=false` 或服务端禁用 debug 时，`debug` 为 null。`debug_trace=true` 时，当前只返回安全摘要字段，包括 `requestId`、`personaSource`、`sessionReadCount`、`memoryReadCount`、`memoryWriteCount`、`ragProvider`、`ragRawHitCount`、`ragFilteredHitCount`、`modelProvider`、`modelRoute`、`safetyAction`、`latencyMs` 和 `events`。

前端只能把 `debug` 用于开发者面板或联调日志，不要展示给普通用户。`debug` 不包含完整 prompt、完整用户输入、完整模型输出、secret、连接串或原始 RAG 文档。

## Chat Stream: POST /v1/chat/stream

用途：发送一次流式角色扮演请求。请求参数与 `/v1/chat` 一致，但 `capabilities.stream` 应为 true。

### Stream Event

| event | data |
| --- | --- |
| start | request_id、session_id |
| source | RAG source 摘要 |
| delta | 增量文本 |
| usage | token 使用 |
| done | 完成标记 |
| error | 错误码和错误信息 |

## Session: POST /v1/sessions

用途：创建连续会话。

创建后，调用方可在 `/v1/chat` 中传入返回的 `session_id`，并设置 `capabilities.continuous_session=true`。

### 请求参数

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| app_id | 是 | 调用方应用 ID |
| user_id | 是 | 用户 ID |
| character_id | 是 | 角色 ID |
| persona_mode | 是 | 角色 preset |
| metadata | 否 | 透传信息 |

### 响应 data

| 字段 | 说明 |
| --- | --- |
| session_id | 会话 ID |
| status | active |
| created_at | 创建时间 |

## Session: GET /v1/sessions/{session_id}

用途：查询 session 状态和摘要。

### 查询参数

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| app_id | 是 | 调用方应用 ID |
| user_id | 是 | 用户 ID |

## Session: DELETE /v1/sessions/{session_id}

用途：关闭 session。关闭后不可继续写入。

## Persona: GET /v1/personas

用途：列出前端可展示的角色和默认 preset。

角色和 preset 的完整字段含义见 `../character-schema.md`。

### 响应 data

| 字段 | 说明 |
| --- | --- |
| characters | 角色列表 |

character 字段：

| 字段 | 说明 |
| --- | --- |
| character_id | 角色 ID |
| display_name | 展示名 |
| description | 简短说明 |
| default_persona_mode | 默认 preset |
| tags | 前端筛选标签 |
| modes | 可选 preset 摘要 |

## Persona: GET /v1/personas/{character_id}/modes

用途：列出指定角色可用 preset。

### 响应 data

| 字段 | 说明 |
| --- | --- |
| character_id | 角色 ID |
| modes | 模式列表 |

mode 字段：

| 字段 | 说明 |
| --- | --- |
| persona_mode | 模式 ID |
| display_name | 显示名 |
| timeline | 时间线 |
| description | 简短说明 |

内置示例：

| character_id | persona_mode | 显示名 |
| --- | --- | --- |
| haruhi | entrance_haruhi | 刚入学的春日 |
| haruhi | mid_late_haruhi | 中后期的春日 |
| haruhi | disappearance_haruhi | 消失春日 |
| asahina_mikuru | default_mikuru | 朝比奈学姐 |
| kyon | default_kyon | 阿虚 |

## RAG: POST /v1/rag/documents

用途：校验 RAG 文档 metadata。当前最小实现不切 chunk、不写 vector index、不调用 embedding。

### 请求参数

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| app_id | 是 | 调用方应用 |
| title | 是 | 文档标题 |
| source_type | 是 | 来源类型 |
| character_id | 是 | 角色 ID |
| persona_mode | 否 | 模式专属文档 |
| timeline | 是 | 时间线 |
| spoiler_level | 是 | 剧透等级 |
| language | 是 | 文档语言 |
| content | 是 | 文档文本 |
| metadata | 否 | 扩展 metadata |

### 响应 data

| 字段 | 说明 |
| --- | --- |
| document_id | 文档 ID |
| chunk_count | chunk 数量 |
| status | 当前为 validated |
| metadata | 通过校验后的 metadata 摘要 |

当前校验规则：

- 必须提供 `character_id`、`timeline`、`spoiler_level`、`language`、`source_type`。
- `persona_mode` 存在时，`timeline`、`spoiler_level` 和 `source_type` 必须符合该 persona policy。
- `persona_mode` 不存在时，metadata 必须符合该角色至少一个公开 persona 的 policy。
- 缺字段或 policy 越界返回统一 `VALIDATION_ERROR`。

## RAG: POST /v1/rag/search

用途：直接检索 RAG，用于调试和后台联调。

### 请求参数

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| app_id | 是 | 调用方应用 |
| user_id | 是 | 用户 ID |
| character_id | 是 | 角色 ID |
| persona_mode | 是 | 角色 preset |
| query | 是 | 检索 query |
| top_k | 是 | 返回数量 |
| filters | 否 | metadata filter |
| debug | 否 | 是否返回调试信息 |

## Memory: GET /v1/memory/{user_id}

用途：查询用户记忆。

### 查询参数

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| app_id | 是 | 调用方应用 |
| character_id | 否 | 角色 ID |
| persona_mode | 否 | 角色 preset |
| type | 否 | 记忆类型 |

## Memory: DELETE /v1/memory/{user_id}/{memory_id}

用途：删除指定记忆。

### 查询参数

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| app_id | 是 | 调用方应用 |

## 错误响应

| error.code | 说明 |
| --- | --- |
| VALIDATION_ERROR | 参数错误 |
| AUTH_INVALID_API_KEY | API Key 无效 |
| PERSONA_MODE_NOT_FOUND | persona mode 不存在 |
| SESSION_NOT_FOUND | session 不存在 |
| RAG_PROVIDER_ERROR | RAG provider 失败 |
| MODEL_PROVIDER_ERROR | 模型 provider 失败 |
| SAFETY_BLOCKED | 安全策略阻断 |
| PERSONA_NOT_FOUND | 角色不存在 |
