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

## 请求资源上限

| 输入 | 上限 |
| ---- | ---- |
| HTTP request body | 1 MiB（1,048,576 bytes） |
| Chat/RAG 请求中的 ID | 128 字符 |
| `message` | 16,000 字符 |
| `generation.max_tokens` | 8,192 |
| RAG `title` | 256 字符 |
| RAG search `query` | 4,000 字符 |
| RAG document `content` | 500,000 字符 |
| RAG `top_k` | 20 |

超过 HTTP body 字节上限时返回 HTTP 413 和 `REQUEST_BODY_TOO_LARGE`。JSON 已被读取后发现字段长度、数值范围或类型错误时返回 HTTP 400 和 `VALIDATION_ERROR`。`capabilities.*`、`generation.allow_narration` 和 RAG `debug` 必须是真正的 JSON boolean，字符串 `"true"`、`"false"` 不会被隐式转换。

## Chat

### POST /v1/chat

发送一次非流式角色扮演请求。

请求字段：

| 字段         | 必填 | 说明           |
| ------------ | ---- | -------------- |
| app_id       | 是   | 调用方应用 ID  |
| user_id      | 是   | 调用方用户 ID  |
| session_id   | 否   | 连续会话 ID    |
| character_id | 是   | 角色 ID        |
| persona_mode | 是   | 角色 preset    |
| message      | 是   | 用户输入       |
| language     | 是   | 输出语言       |
| capabilities | 否   | 能力开关       |
| generation   | 否   | 生成参数       |
| metadata     | 否   | 调用方透传对象 |

省略 `capabilities` 或其中的 `rag`、`memory` 时，这两项遵循当前 persona 的 `enabledByDefault`；显式传入 `false` 可强制关闭。连续会话和 debug 默认关闭，`safety_filter` 默认开启。省略 `generation` 或 `generation.model` 时使用服务端 router 的 default alias；普通前端不需要知道 provider、base URL、token 或 model alias。

当 `capabilities.continuous_session=true` 时，`session_id` 必须来自 `POST /v1/sessions` 创建的 active session，并且与当前 `app_id`、`user_id`、`character_id`、`persona_mode` 匹配。

当调用方显式传入 `capabilities.rag=true` 时，服务端必须已注入 `RagService`。当前实现支持 fake、本地文本、本地向量（memory/Chroma/Faiss）和 Qdrant 检索，并使用 persona policy 过滤、混合候选重排、去重和类型配额。

当 `capabilities.memory=true` 时，服务端必须已注入 `MemoryStore`。服务会读取同一 `app_id`、`user_id`、`character_id`、`persona_mode` 下的有限记忆，并按 persona `memoryPolicy.allowedTypes` 过滤。

写入长期记忆时，调用方必须在 `metadata.memory_write` 中提供显式候选。候选必须包含 `type`、`content`、`reason`、`confidence`。默认策略只接受稳定偏好、关系或约定类信息，并拒绝临时闲聊和敏感信息。

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

`sources` 至少包含 `document_id`、`chunk_id`、`content`、`source_type`、`character_id`、`timeline`、`spoiler_level`、`language` 和 `score`。`content` 是本次实际注入提示词的检索 chunk，前端应按不受信任的纯文本渲染，不要作为 HTML 插入页面。

`memory` 字段：

| 字段        | 说明                   |
| ----------- | ---------------------- |
| enabled     | 是否执行长期记忆读取   |
| read_count  | 本次读入 Prompt 的数量 |
| write_count | 本次写入长期记忆的数量 |

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
| streamEnabled       | 是否启用流式输出           |
| safetyAction        | 安全处理动作               |
| latencyMs           | 请求总耗时毫秒             |
| events              | 请求阶段名称列表           |

`debug` 不返回完整 prompt、完整用户输入、完整模型输出、secret、连接串或原始 RAG 文档。

当前 `capabilities.safety_filter` 和 debug 中的 safety 字段只记录调用意图与结果占位，规则型 `SafetyGuard` 尚未接入，不应把它视为已经执行输入/输出内容审核。

### POST /v1/chat/stream

发送一次流式角色扮演请求。请求字段与 `/v1/chat` 一致，服务端会把 `capabilities.stream` 视为 true。流式接口复用同一个 Orchestrator 和 PromptBuilder，不改变 session、RAG、memory 或 safety 语义。

框架无关 API handler 可用 `data.events` 数组表达事件；当前 HTTP runtime 已把 provider 增量惰性编码为端到端 SSE，不会先缓存完整回复再发送。

事件格式：

| event  | data 说明                                                  |
| ------ | ---------------------------------------------------------- |
| start  | `request_id`、`session_id`、`character_id`、`persona_mode` |
| source | 单条 RAG source，包含实际检索 chunk 的 `content`           |
| delta  | `text` 增量文本                                            |
| usage  | token 使用、provider 和 model                              |
| done   | 完整 chat 结果摘要，包含最终 `reply`                       |
| error  | `error.code` 和 `error.message`                            |

正常事件顺序为 `start -> source* -> delta+ -> usage -> done`。模型开始前失败时返回普通错误响应；模型开始后失败时返回 `error` event。正常结束后服务端会累积完整 assistant reply，并按连续会话规则保存完整消息。

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

每个 character 的 `modes` 已包含该角色当前公开的 preset，不另提供 modes 子路由。

## Session

### POST /v1/sessions

创建连续会话。

当前不提供 session 查询或关闭接口。调用方保存 `POST /v1/sessions` 返回的 `session_id`；过期和清理由具体 `SessionStore` 负责。

## RAG

### POST /v1/rag/documents

校验 RAG 文档 metadata，并在注入 RAG ingest provider 时写入本地或云端索引。

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

未注入 ingest provider 时只返回 `validated`，用于 metadata 校验。注入 RAG provider 时返回 `imported`，服务会按文本切分 chunk 并保留 metadata。当前支持 `local` 文本检索、`local_vector` 标准库向量检索、可选 Chroma/Faiss 本地向量后端，以及 Qdrant REST 云端 provider。

顶层 `app_id` 会由服务端写入每个 RAG chunk 的 metadata。检索只返回同一 `app_id` 下的数据，且 source 摘要包含 `app_id`。不同应用可以复用同一个 `document_id`，服务端生成的内部 chunk/point ID 仍然不同。缺少 `app_id` 的旧 Chroma/Qdrant 记录不会参与检索，不会被自动归属到当前应用。

### POST /v1/rag/search

调试 RAG 检索。

请求字段：

| 字段         | 必填 | 说明             |
| ------------ | ---- | ---------------- |
| app_id       | 是   | 调用方应用       |
| user_id      | 是   | 用户 ID          |
| character_id | 是   | 角色 ID          |
| persona_mode | 是   | 角色 preset      |
| query        | 是   | 检索 query       |
| top_k        | 是   | 返回数量         |
| filters      | 否   | metadata filter  |
| debug        | 否   | 是否返回调试信息 |

`filters` 字段：

| 字段              | 说明                    |
| ----------------- | ----------------------- |
| source_types      | 允许的 source type 列表 |
| timelines         | 允许的 timeline 列表    |
| spoiler_level_max | 最大剧透等级            |
| language          | 文档语言                |

响应字段：

| 字段               | 说明                                          |
| ------------------ | --------------------------------------------- |
| provider           | RAG provider 名称                             |
| hit_count          | 返回 chunk 数量                               |
| raw_hit_count      | provider 原始命中数量                         |
| filtered_hit_count | metadata filter 后数量                        |
| rerank_applied     | 是否执行 rerank                               |
| chunks             | 命中的 chunk 列表，包含 source 摘要和 content |

`app_id` 是强制存储过滤条件，不属于调用方可覆盖的 `filters` 字段。它会与 character、persona、timeline、spoiler、language 和 source type 过滤共同生效。

## Memory

### GET /v1/memory/{user_id}

查询用户记忆。

查询参数：

| 字段         | 必填 | 说明                             |
| ------------ | ---- | -------------------------------- |
| app_id       | 是   | 调用方应用 ID                    |
| character_id | 是   | 角色 ID                          |
| persona_mode | 否   | 角色 preset；不传只查通用记忆    |
| type         | 否   | 记忆类型，例如 `user_preference` |
| limit        | 否   | 返回数量上限，默认 50，最大 100  |

响应字段：

| 字段         | 说明           |
| ------------ | -------------- |
| app_id       | 调用方应用 ID  |
| user_id      | 用户 ID        |
| character_id | 角色 ID        |
| persona_mode | 角色 preset    |
| count        | 返回的记忆数量 |
| items        | 记忆列表       |

memory item 字段：

| 字段         | 说明        |
| ------------ | ----------- |
| memory_id    | 记忆 ID     |
| app_id       | 调用方应用  |
| user_id      | 用户 ID     |
| character_id | 角色 ID     |
| persona_mode | 角色 preset |
| type         | 记忆类型    |
| content      | 记忆内容    |
| confidence   | 置信度      |
| reason       | 写入原因    |
| created_at   | 创建时间    |
| updated_at   | 更新时间    |

该接口用于管理和展示记忆。`/v1/chat` 在 `capabilities.memory=true` 时会通过服务端注入的 `MemoryStore` 读取和写入记忆，但不会通过该查询接口反向调用。

### DELETE /v1/memory/{user_id}/{memory_id}

删除指定记忆。

查询参数：

| 字段         | 必填 | 说明                        |
| ------------ | ---- | --------------------------- |
| app_id       | 是   | 调用方应用 ID               |
| character_id | 是   | 角色 ID                     |
| persona_mode | 否   | 角色 preset；必须与记忆匹配 |

删除只会影响同一个 `app_id`、`user_id`、`character_id`、`persona_mode` 下的记忆。上下文不匹配或记忆不存在时统一返回 `MEMORY_NOT_FOUND`，避免暴露其它用户或角色的记忆是否存在。

## Access Token

### POST /v1/access-tokens

使用 `ROLEPLAY_API_KEY` 创建服务令牌。请求必须包含非空 `app_id` 和 `name`，可选 `quota_tokens`、`daily_quota_tokens`、`weekly_quota_tokens`、`expires_at`。一个令牌只绑定一个 `app_id`，创建后不可修改。三种额度可以任意组合；`null` 表示对应尺度不限额。

创建、列表、详情、额度调整和吊销响应中的安全摘要都包含 `app_id`。令牌明文 `token` 只在创建响应出现一次，SQLite 只保存哈希和安全前缀。

旧 SQLite 账本会原地增加 nullable `app_id`、`daily_quota_tokens`、`weekly_quota_tokens` 列；旧令牌返回 `app_id=null`，日、周额度默认不限额。

服务令牌调用以下 app-scoped route 时，HTTP runtime 必须在业务 handler 前比较 token scope 与请求 `app_id`：

- body：`POST /v1/sessions`、`POST /v1/chat`、`POST /v1/chat/stream`、`POST /v1/rag/documents`、`POST /v1/rag/search`。
- query：`GET /v1/memory/{user_id}`、`DELETE /v1/memory/{user_id}/{memory_id}`。

不匹配或 legacy unscoped token 统一返回 `AUTH_PERMISSION_DENIED`，不暴露目标资源是否存在。管理密钥仍可跨 app 调用；额外 Header 不能声明或覆盖 app scope。

聊天用量优先采用模型 provider 返回的 `prompt_tokens` 和 `completion_tokens`。OpenAI-compatible provider 未返回某个 usage 字段时，服务使用消息或回复长度进行轻量估算；估算不是 tokenizer 精确结果。provider 返回负数或不可解析字段时，该字段按 `0` 记账。SSE provider 错误从 `data.error.code` 写入请求日志，日志不保存 prompt 或回复正文。

生命周期额度持续累计；每日额度按 UTC 自然日，每日 00:00 重置；每周额度按 ISO 周，每周一 00:00 UTC 重置。所有已配置尺度同时生效，任一尺度耗尽都会使下一次 chat 或 chat stream 返回 429 `ACCESS_TOKEN_QUOTA_EXCEEDED`。响应通过 `exhausted_quota_scopes` 暴露当前耗尽的 `total`、`daily`、`weekly`，并返回各周期用量、剩余量和下一次重置时间。

`PATCH /v1/access-tokens/{token_id}` 接受上述三种额度中的一项或多项。省略字段保留当前设置，显式 `null` 清除对应限制。用量在模型请求结束后结算，因此最后一个已接纳请求可能越过阈值；本契约不提供并发请求的额度预留。

## HTTP 生产门禁

- loopback 监听允许本地无密钥开发；非 loopback 监听要求至少 32 字符且不是示例占位值的 `ROLEPLAY_API_KEY`。
- 未携带 `Origin` 的服务间调用不受 CORS 影响，继续执行 API Key 或 Access Token 鉴权。
- 浏览器同源请求自动允许；跨域请求的 Origin 必须精确匹配 `ROLEPLAY_CORS_ORIGINS`，否则返回 `403 AUTH_PERMISSION_DENIED`。
- CORS 响应只回显当前允许的具体 Origin，不返回 `Access-Control-Allow-Origin: *`。

## 错误码

| 错误码                 | 说明               |
| ---------------------- | ------------------ |
| VALIDATION_ERROR       | 参数错误           |
| REQUEST_BODY_TOO_LARGE | HTTP 请求体超过 1 MiB |
| AUTH_INVALID_API_KEY   | API Key 无效       |
| AUTH_PERMISSION_DENIED | 权限不足           |
| PERSONA_NOT_FOUND      | 角色不存在         |
| PERSONA_MODE_NOT_FOUND | preset 不存在      |
| SESSION_NOT_FOUND      | session 不存在     |
| SESSION_PROVIDER_ERROR | session provider 失败 |
| RAG_PROVIDER_ERROR     | RAG provider 失败  |
| MODEL_PROVIDER_ERROR   | 模型 provider 失败 |
| MODEL_TIMEOUT          | 模型超时           |
| MEMORY_NOT_FOUND       | 记忆不存在         |
| MEMORY_ACCESS_DENIED   | 记忆访问被拒绝     |
| SAFETY_BLOCKED         | 预留安全策略错误码；当前尚未主动产生 |
| INTERNAL_ERROR         | 内部错误           |

## 字段命名

- 对外 HTTP API 使用 `snake_case`。
- 内部 application/domain DTO 使用 `camelCase`。
- API 层负责转换。

详细字段以 `docs/usage/interface-reference.md` 为准。
