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
| stream | boolean | `/v1/chat` 必须为 false；`/v1/chat/stream` 会强制视为 true |

当前最小 `/v1/chat` 实现支持非流式请求、连续会话、RAG retrieve、memory read policy 和保守 memory write policy。`continuous_session=true` 时必须传入 `session_id`，且 session 必须匹配同一个 `app_id`、`user_id`、`character_id` 和 `persona_mode`。`rag=true` 时服务端必须注入 `RagService`。`memory=true` 时服务端必须注入 `MemoryStore`，并按 persona 的 `memoryPolicy.allowedTypes` 和服务端读取上限筛选记忆。非流式 `/v1/chat` 不接受 `stream=true`，需要流式输出时使用 `/v1/chat/stream`。

### generation

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| model | string | 服务端白名单模型别名，例如 `haruhi-ollama`；不能传 provider 名、base URL 或真实密钥 |
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

`rag.enabled=false` 时只返回 `{"enabled": false}`。`rag.enabled=true` 时返回 `provider`、`hit_count`、`raw_hit_count`、`filtered_hit_count` 和 `sources`。每个 source 至少包含 `document_id`、`chunk_id`、`source_type`、`character_id`、`timeline`、`spoiler_level`、`language` 和 `score`。

`memory.enabled=false` 时只返回 `{"enabled": false}`。`memory.enabled=true` 时返回 `read_count` 和 `write_count`。当前不会从普通聊天内容中自由抽取记忆，只有显式候选才可能写入。

如果需要写入记忆，调用方必须在 `metadata.memory_write` 传入显式候选：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| type | 是 | 记忆类型，必须符合 persona `memoryPolicy.allowedTypes` |
| content | 是 | 候选记忆内容 |
| reason | 是 | 写入原因，例如“用户明确表达稳定偏好” |
| confidence | 是 | 置信度，默认策略要求不低于 0.7 |

`metadata.memory_write` 可以是单个对象或对象列表。默认策略会拒绝临时闲聊、敏感信息、低置信度和不被当前 persona 允许的类型。写入结果通过 `memory.write_count` 返回。

`debug_trace=false` 或服务端禁用 debug 时，`debug` 为 null。`debug_trace=true` 时，当前只返回安全摘要字段，包括 `requestId`、`personaSource`、`sessionReadCount`、`memoryReadCount`、`memoryWriteCount`、`ragProvider`、`ragRawHitCount`、`ragFilteredHitCount`、`backendContextFactCount`、`backendContextSources`、`modelProvider`、`modelRoute`、`contextPlan`、`safetyAction`、`streamEnabled`、`latencyMs` 和 `events`。`modelRoute` 返回服务端模型别名，不返回 provider 侧真实模型配置。

`debug.contextPlan` 当前由确定性 planner 生成，字段包括 `planner`、`status`、`readSession`、`readMemory`、`retrieveRag`、`backendFetches` 和 `notes`。它只描述本次是否读取 session、memory、RAG 和 backend context，不包含用户原文、完整 prompt、检索 query、URL、SQL 或 secret。

`backendContextFactCount` 和 `backendContextSources` 只用于调试后端上下文是否被读取，不返回 fact 内容或原始业务 JSON。

前端只能把 `debug` 用于开发者面板或联调日志，不要展示给普通用户。`debug` 不包含完整 prompt、完整用户输入、完整模型输出、secret、连接串或原始 RAG 文档。

## Chat Stream: POST /v1/chat/stream

用途：发送一次流式角色扮演请求。请求参数与 `/v1/chat` 一致，服务端会把 `capabilities.stream` 强制视为 true。模型开始前失败时返回普通错误响应；模型开始后失败时返回 `error` event。

当前框架无关 handler 返回 `data.events` 数组；真实 HTTP adapter 应逐条编码为 SSE 或等价流式协议。

### Stream Event

| event | data |
| --- | --- |
| start | `request_id`、`session_id`、`character_id`、`persona_mode` |
| source | `source`，单条 RAG source 摘要 |
| delta | `text`，模型增量文本 |
| usage | `prompt_tokens`、`completion_tokens`、`total_tokens`、`provider`、`model` |
| done | `request_id`、`session_id`、`character_id`、`persona_mode`、`reply`、`rag`、`memory`、`safety`、`debug` |
| error | `request_id` 和 `error.code`、`error.message` |

正常事件顺序：

```text
start -> source* -> delta+ -> usage -> done
```

中途 provider 失败时：

```text
start -> source* -> delta* -> error
```

流式请求仍复用同一个 Orchestrator、PromptBuilder、RAG、memory 和 session 语义。正常结束后服务端会累积完整 assistant reply，并按连续会话规则写入完整消息。

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

用途：校验 RAG 文档 metadata，并在服务端注入 RAG provider 时写入本地或云端索引。

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
| status | `validated` 或 `imported` |
| metadata | 通过校验后的 metadata 摘要 |

未注入 ingest provider 时只返回 `validated`，用于 metadata 校验。注入 RAG provider 时返回 `imported`，并把文本切成本地或云端 chunks，供 `/v1/chat` 的 RAG 分支检索。

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

### filters 字段

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| source_types | 否 | 来源类型列表，例如 `["timeline"]` |
| timelines | 否 | 时间线列表，例如 `["mid_late"]` |
| spoiler_level_max | 否 | 最大剧透等级 |
| language | 否 | `zh-CN`、`ja-JP`、`en-US` |

### 响应 data

| 字段 | 说明 |
| --- | --- |
| provider | RAG provider 名称，例如 `local-vector-rag` 或 `qdrant-rag` |
| hit_count | 返回 chunk 数量 |
| raw_hit_count | provider 原始命中数量 |
| filtered_hit_count | metadata filter 后数量 |
| rerank_applied | 是否执行 rerank |
| chunks | 命中的 chunk，包含 source 摘要和 `content` |

## Memory: GET /v1/memory/{user_id}

用途：查询用户记忆。

### 查询参数

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| app_id | 是 | 调用方应用 |
| character_id | 是 | 角色 ID |
| persona_mode | 否 | 角色 preset；不传只查通用记忆 |
| type | 否 | 记忆类型 |
| limit | 否 | 返回数量上限，默认 50，最大 100 |

### 响应 data

| 字段 | 说明 |
| --- | --- |
| app_id | 调用方应用 |
| user_id | 用户 ID |
| character_id | 角色 ID |
| persona_mode | 角色 preset |
| count | 返回数量 |
| items | 记忆列表 |

item 字段：

| 字段 | 说明 |
| --- | --- |
| memory_id | 记忆 ID |
| app_id | 调用方应用 |
| user_id | 用户 ID |
| character_id | 角色 ID |
| persona_mode | 角色 preset |
| type | 记忆类型 |
| content | 记忆内容 |
| confidence | 置信度 |
| reason | 写入原因 |
| created_at | 创建时间 |
| updated_at | 更新时间 |

当前查询只返回同一个 `app_id`、`user_id`、`character_id`、`persona_mode` 下的记忆。

## Memory: DELETE /v1/memory/{user_id}/{memory_id}

用途：删除指定记忆。

### 查询参数

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| app_id | 是 | 调用方应用 |
| character_id | 是 | 角色 ID |
| persona_mode | 否 | 角色 preset；必须与记忆匹配 |

上下文不匹配或记忆不存在时返回 `MEMORY_NOT_FOUND`。当前删除是手动管理能力；chat 只会在 `capabilities.memory=true` 时读取有限记忆，并只写入通过 policy 的显式候选。

## Runtime Config: GET /v1/runtime-config

用途：读取当前运行时后端配置摘要，供受信任的管理前端或后台面板展示。

该接口要求服务端配置 `ROLEPLAY_API_KEY`，并且请求携带 `Authorization: Bearer <key>` 或 `X-API-Key`。普通用户前端不应该调用该接口。

### 响应 data

| 字段 | 说明 |
| --- | --- |
| source | 配置来源，默认是项目根目录 `.env`，测试中可为 `memory` |
| persists_updates | 是否会把 PATCH 写回配置文件 |
| configurable_keys | 允许热更新的 key 列表 |
| values | 当前非敏感配置摘要 |

`MODEL_PROVIDER_REGISTRY` 不会原样返回，只返回 provider type、alias 和默认 alias 摘要，避免把连接信息或误写入的敏感内容暴露给前端。

## Runtime Config: PATCH /v1/runtime-config

用途：热更新允许的后端配置，并在不重启服务的情况下重建 model router、RAG service、agent context planner 和 backend context provider。

该接口同样要求 `ROLEPLAY_API_KEY`。只允许更新非敏感配置；`API_KEY`、`TOKEN`、`SECRET`、`PASSWORD`、`DATABASE_URL`、`REDIS_URL` 等敏感 key 会被拒绝。云端密钥应放在服务端环境变量或 `.env` 中，并通过 `*_API_KEY_ENV` 间接引用。

### 请求参数

```json
{
  "values": {
    "MODEL_PROVIDER": "fake",
    "MODEL_NAME": "fake-roleplay-model",
    "MODEL_ALIAS": "fake-roleplay-model",
    "RAG_PROVIDER": "local",
    "AGENT_CONTEXT_PLANNER": "deterministic",
    "BACKEND_CONTEXT_PROVIDER": "fake",
    "BACKEND_CONTEXT_SOURCES": "user_profile,game_state"
  }
}
```

字段值传 `null` 表示从 `.env` 托管配置中移除该 key。移除只影响 `.env` 中的覆盖值，不能删除进程启动时已经存在的系统环境变量。

服务端会先用候选配置构建 model router、RAG service、agent context planner 和 backend context provider；如果构建失败，不会写回 `.env`，当前运行配置也不会改变。

`AGENT_CONTEXT_PLANNER=model` 当前只是预留入口。它可以通过 runtime config 设置，但真实模型辅助 planner 未实现；设置后 chat 会返回 `MODEL_PROVIDER_ERROR`，直到后续补齐 planner prompt、结构化输出解析和安全校验。

## 错误响应

| error.code | 说明 |
| --- | --- |
| VALIDATION_ERROR | 参数错误 |
| AUTH_INVALID_API_KEY | API Key 无效 |
| AUTH_PERMISSION_DENIED | 权限不足 |
| PERSONA_MODE_NOT_FOUND | persona mode 不存在 |
| SESSION_NOT_FOUND | session 不存在 |
| RAG_PROVIDER_ERROR | RAG provider 失败 |
| MODEL_PROVIDER_ERROR | 模型 provider 失败 |
| MEMORY_NOT_FOUND | 记忆不存在 |
| SAFETY_BLOCKED | 安全策略阻断 |
| PERSONA_NOT_FOUND | 角色不存在 |
