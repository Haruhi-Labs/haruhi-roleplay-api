# 生产 API 接入指南

本文是业务接入方的首要入口，描述当前已部署服务的生产地址、鉴权方式、可调用接口、
完整聊天参数、角色目录、SSE 事件和安全边界。

更细的逐接口字段见 [接口参考](interface-reference.md)，稳定响应语义见
[API 契约](../api-contract.md)。本地启动、部署和签发令牌分别见
[快速开始](quickstart.md)、[Docker Compose](docker-compose.md) 和
[访问令牌管理](access-token-management.md)。

## 生产入口与稳定性边界

| 用途 | 地址 | 接入方 |
| --- | --- | --- |
| 生产服务 Origin | `https://roleplay.haruyuki.cn` | 业务后端 |
| 稳定业务 API | `https://roleplay.haruyuki.cn/v1/...` | 持有服务令牌的业务后端 |
| 健康检查 | `https://roleplay.haruyuki.cn/health` | 持有服务令牌的监控或业务后端 |
| 调试工作台 | `https://roleplay.haruyuki.cn/chat/` | 人工体验和联调 |
| 管理后台 | `https://roleplay.haruyuki.cn/admin/` | 受信任管理员 |

只有 `/health` 和 `/v1/...` 的正式业务路由属于服务端接入契约。调试工作台使用的
`/v1/demo/...` 是受限的公开同源代理，只允许随机 `demo-...` 用户作用域，不允许
导入语料或访问管理能力；它可以随工作台调整，不属于外部系统接入契约，外部系统
不得依赖它。

当前没有单独的 OpenAPI 文件或 SDK。HTTP JSON 与 SSE 是规范接入方式，字段名统一
使用 `snake_case`。

## 接入前需要获得什么

管理员会为每个调用服务签发一枚以 `hrt_` 开头的服务令牌，并绑定一个固定
`app_id`。接入方需要保存三项配置：

```env
HARUHI_ROLEPLAY_ORIGIN=https://roleplay.haruyuki.cn
HARUHI_ROLEPLAY_APP_ID=your-assigned-app-id
HARUHI_ROLEPLAY_TOKEN=hrt_replace_with_issued_token
```

服务令牌只放在业务后端的 Secret Manager 或服务端环境变量中，不得放进网页源码、
桌面客户端、移动客户端、URL、Git 或日志。推荐调用链路：

```text
Browser / App -> Your Business Backend -> Haruhi Roleplay API
```

每次请求使用：

```http
Authorization: Bearer hrt_replace_with_issued_token
Content-Type: application/json
X-Request-Id: your-unique-request-id
```

`Authorization` 可替换为 `X-API-Key`，但不建议同一请求同时使用两种方式。服务令牌
调用 Session、Chat、RAG 和 Memory 路由时，请求中的 `app_id` 必须与令牌绑定值
完全一致，否则返回 HTTP 403 `AUTH_PERMISSION_DENIED`。

## 五分钟完成首次调用

### 1. 检查服务

```bash
curl -sS "$HARUHI_ROLEPLAY_ORIGIN/health" \
  -H "Authorization: Bearer $HARUHI_ROLEPLAY_TOKEN"
```

成功响应：

```json
{
  "ok": true,
  "data": {
    "status": "ok"
  },
  "request_id": "req-..."
}
```

### 2. 获取角色和人格模式

```bash
curl -sS "$HARUHI_ROLEPLAY_ORIGIN/v1/personas" \
  -H "Authorization: Bearer $HARUHI_ROLEPLAY_TOKEN"
```

应用启动时读取此接口，用返回的 `character_id` 和该角色 `modes` 中的
`persona_mode` 构造选择器。不要把下文的当前快照当作永久枚举。

### 3. 发送一条消息

```bash
curl -sS "$HARUHI_ROLEPLAY_ORIGIN/v1/chat" \
  -H "Authorization: Bearer $HARUHI_ROLEPLAY_TOKEN" \
  -H "Content-Type: application/json" \
  -H "X-Request-Id: onboarding-001" \
  -d "{
    \"app_id\": \"$HARUHI_ROLEPLAY_APP_ID\",
    \"user_id\": \"your-user-001\",
    \"character_id\": \"haruhi\",
    \"persona_mode\": \"mid_late_haruhi\",
    \"message\": \"今天社团要做什么？\",
    \"language\": \"zh-CN\"
  }"
```

最小请求只需要以上六个业务字段。省略 RAG、Memory 和生成参数时，服务端会组合角色
模式的默认策略与模型路由默认值。

## 业务接口总览

| 方法与路径 | 用途 | 是否需要 `app_id` |
| --- | --- | --- |
| `GET /health` | 服务存活检查 | 否 |
| `GET /v1/personas` | 发现公开角色、模式和默认能力 | 否 |
| `POST /v1/sessions` | 创建连续会话 | 是，JSON body |
| `POST /v1/chat` | 非流式角色对话 | 是，JSON body |
| `POST /v1/chat/stream` | SSE 流式角色对话 | 是，JSON body |
| `POST /v1/rag/documents` | 校验并导入调用方语料 | 是，JSON body |
| `POST /v1/rag/search` | 直接调试检索 | 是，JSON body |
| `GET /v1/memory/{user_id}` | 查询当前用户、角色的长期记忆 | 是，query string |
| `DELETE /v1/memory/{user_id}/{memory_id}` | 删除作用域内的长期记忆 | 是，query string |

令牌、后台角色、系统配置、全局 RAG、审计和管理员 Session 接口不是业务接入面，
不接受普通服务令牌。详见 [接口参考](interface-reference.md)。

## 角色和模式

### 目录返回字段

`GET /v1/personas` 返回 `data.characters`。每个角色包含：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `character_id` | string | Chat 和 Session 使用的稳定角色 ID |
| `display_name` | string | 面向用户的角色名 |
| `description` | string | 目录展示说明，不直接作为模型身份提示词 |
| `default_persona_mode` | string | 未做额外选择时建议使用的模式 |
| `tags` | string[] | 展示和筛选标签 |
| `modes` | object[] | 当前公开模式 |

每个 `modes` 元素包含：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `persona_mode` | string | 请求使用的模式 ID |
| `display_name` | string | 模式展示名 |
| `timeline` | string | 模式所处篇章或时间线 |
| `description` | string | 模式展示说明 |
| `rag_enabled_by_default` | boolean | 未显式设置 `capabilities.rag` 时的默认值 |
| `memory_enabled_by_default` | boolean | 未显式设置 `capabilities.memory` 时的默认值 |

`character_id` 和 `persona_mode` 必须属于同一条目录记录。模式会改变角色所处篇章、
知识边界、关系和 RAG 策略，并不只是前端展示皮肤。

### 当前生产角色快照

以下快照更新于 2026-07-24，用于首次接入核对；运行时始终以
`GET /v1/personas` 返回为准。

| 角色 | `character_id` | 默认 `persona_mode` | 其它公开模式 |
| --- | --- | --- | --- |
| 凉宫春日 | `haruhi` | `mid_late_haruhi` | `melancholy_haruhi`、`sigh_haruhi`、`endless_eight_haruhi`、`disappearance_haruhi`、`surprise_haruhi` |
| 阿虚 | `kyon` | `default_kyon` | `melancholy_kyon`、`sigh_kyon`、`endless_eight_kyon`、`disappearance_kyon`、`surprise_kyon` |
| 朝比奈实玖瑠 | `mikuru` | `default_mikuru` | `melancholy_mikuru`、`sigh_mikuru`、`endless_eight_mikuru`、`disappearance_mikuru`、`surprise_mikuru` |
| 长门有希 | `yuki` | `default_yuki` | `melancholy_yuki`、`sigh_yuki`、`endless_eight_yuki`、`disappearance_yuki`、`surprise_yuki` |
| 古泉一树 | `itsuki` | `default_itsuki` | `melancholy_itsuki`、`sigh_itsuki`、`endless_eight_itsuki`、`disappearance_itsuki`、`surprise_itsuki` |

阿虚的 `narrator_kyon` 当前是草稿模式，不会由公开目录返回，也不能用于正式聊天。

## Chat 完整参数

`POST /v1/chat` 和 `POST /v1/chat/stream` 共用以下 JSON body：

| 字段 | 类型 | 必填 | 默认值或限制 | 建议由谁控制 |
| --- | --- | --- | --- | --- |
| `request_id` | string | 否 | 最长 128 字符；通常改用 `X-Request-Id` | 业务后端 |
| `app_id` | string | 是 | 最长 128 字符，必须匹配令牌作用域 | 业务后端固定 |
| `user_id` | string | 是 | 最长 128 字符；使用业务侧稳定且不含敏感信息的 ID | 业务后端 |
| `session_id` | string | 条件必填 | 开启连续会话时必填，最长 128 字符 | 业务后端 |
| `character_id` | string | 是 | 来自 `/v1/personas` | 用户可选 |
| `persona_mode` | string | 是 | 来自所选角色的 `modes` | 用户可选 |
| `message` | string | 是 | 非空，最长 16,000 字符 | 用户 |
| `language` | string | 是 | `zh-CN`、`ja-JP`、`en-US` | 产品或用户 |
| `capabilities` | object | 否 | 见下表 | 产品策略 |
| `generation` | object | 否 | 见下表 | 高级设置 |
| `metadata` | object | 否 | 当前用于显式 `memory_write` 等受控扩展 | 业务后端 |

### `capabilities`

| 字段 | 类型 | 省略时 | 说明 |
| --- | --- | --- | --- |
| `rag` | boolean | 当前模式的 `rag_enabled_by_default` | 显式 `false` 可强制关闭 |
| `memory` | boolean | 当前模式的 `memory_enabled_by_default` | 显式 `false` 可强制关闭 |
| `continuous_session` | boolean | `false` | 开启后必须提供匹配的 `session_id` |
| `safety_filter` | boolean | `true` | 当前表示安全能力意图和状态；不能替代调用方内容审核 |
| `debug_trace` | boolean | `false` | 仅在服务端允许时返回安全调试摘要 |
| `stream` | boolean | `false` | `/v1/chat` 只能为 `false`；stream 路由会强制为 `true` |

所有 boolean 都必须传 JSON `true` 或 `false`，不能传字符串。

### `generation`

| 字段 | 类型 | 默认值 | 允许值或说明 |
| --- | --- | --- | --- |
| `model` | string | 服务端 default alias | 只能传服务端白名单模型别名；公共目录不暴露真实 Provider |
| `temperature` | number | `0.8` | 0–2 |
| `max_tokens` | integer | `800` | 1–8,192 |
| `top_p` | number | `1.0` | 0–1 |
| `presence_penalty` | number | `0.0` | Provider 支持的数值 |
| `frequency_penalty` | number | `0.0` | Provider 支持的数值 |
| `style_intensity` | number | `0.75` | 0–1，角色演绎强度 |
| `allow_narration` | boolean | `true` | 是否允许角色回复包含旁白 |

普通接入不应让用户选择 `model`。指定未在服务端注册的 alias 会返回
`MODEL_PROVIDER_ERROR`，不会静默回退；业务客户端也不应传 Provider URL、模型密钥、
Embedding 配置或数据库配置。

### 推荐的显式请求

```json
{
  "app_id": "your-assigned-app-id",
  "user_id": "your-user-001",
  "character_id": "haruhi",
  "persona_mode": "mid_late_haruhi",
  "message": "今天社团要做什么？",
  "language": "zh-CN",
  "capabilities": {
    "rag": true,
    "memory": true,
    "continuous_session": false,
    "safety_filter": true,
    "debug_trace": false
  },
  "generation": {
    "temperature": 0.8,
    "max_tokens": 800,
    "top_p": 1.0,
    "presence_penalty": 0.0,
    "frequency_penalty": 0.0,
    "style_intensity": 0.75,
    "allow_narration": true
  }
}
```

## 连续会话

先创建 Session：

```bash
curl -sS "$HARUHI_ROLEPLAY_ORIGIN/v1/sessions" \
  -H "Authorization: Bearer $HARUHI_ROLEPLAY_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"app_id\": \"$HARUHI_ROLEPLAY_APP_ID\",
    \"user_id\": \"your-user-001\",
    \"character_id\": \"haruhi\",
    \"persona_mode\": \"mid_late_haruhi\"
  }"
```

保存响应中的 `data.session_id`，后续 Chat 请求同时传：

```json
{
  "session_id": "session-id-from-create",
  "capabilities": {
    "continuous_session": true
  }
}
```

Session 与 `app_id`、`user_id`、`character_id`、`persona_mode` 严格绑定；切换角色或模式
时应创建新 Session。业务 API 当前不提供查询或关闭 Session 的路由。

## 流式 SSE

使用 `POST /v1/chat/stream`，请求 body 与非流式 Chat 相同：

```bash
curl -N "$HARUHI_ROLEPLAY_ORIGIN/v1/chat/stream" \
  -H "Authorization: Bearer $HARUHI_ROLEPLAY_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d "{
    \"app_id\": \"$HARUHI_ROLEPLAY_APP_ID\",
    \"user_id\": \"your-user-001\",
    \"character_id\": \"haruhi\",
    \"persona_mode\": \"mid_late_haruhi\",
    \"message\": \"今天社团要做什么？\",
    \"language\": \"zh-CN\"
  }"
```

正常事件顺序：

```text
start -> source* -> delta+ -> usage -> done
```

| `event` | `data` 主要内容 | 客户端处理 |
| --- | --- | --- |
| `start` | 请求、Session、角色和模式 ID | 创建一条 assistant 占位消息 |
| `source` | 单条实际检索来源，含 `source.content` | 缓存引用，不要触发消息区逐字重绘 |
| `delta` | `text` 增量 | 合并后按帧或小批次更新 UI |
| `usage` | Token、Provider 和模型摘要 | 记录用量 |
| `done` | 完整 `reply`、RAG、Memory、Safety、Debug 摘要 | 用最终结果收口 |
| `error` | 稳定错误码和消息 | 终止本轮并记录 `request_id` |

POST SSE 不能用只支持 GET 的浏览器原生 `EventSource`，应使用
`fetch()`、`ReadableStream` 和增量 UTF-8 解码。可直接参考
[前端调用完整文档中的解析器](frontend-api-calling.md#4-发送流式消息)。

`source.content` 是本次实际注入模型的语料片段。前端可以优先展示其正文，但必须把它
作为不受信任的纯文本处理，不能写入 `innerHTML`。

## RAG 和 Memory 参数

Chat 中通常只需设置 `capabilities.rag` 和 `capabilities.memory`。直接导入、检索和
记忆管理属于业务后端或调试工具能力，不建议暴露给普通聊天界面。

`POST /v1/rag/search` 的 `top_k` 可省略，默认 5，范围 1–20。`filters` 支持：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `source_types` | string[] | 来源类型 |
| `timelines` | string[] | 时间线 |
| `record_kinds` | string[] | 记录种类，如场景记忆 |
| `perspectives` | string[] | 叙事视角 |
| `corpus_versions` | string[] | 语料版本 |
| `retrieval_channels` | string[] | 检索通道 |
| `knowledge_owners` | string[] | 知识持有者 |
| `usages` | string[] | 语料用途 |
| `spoiler_level_max` | integer | 最大剧透等级，不能为负数 |
| `language` | string | `zh-CN`、`ja-JP`、`en-US` |

当前正式凉宫语料常见值：

| 维度 | 当前值 |
| --- | --- |
| `source_types` | `timeline`、`relationship`、`scene` |
| `timelines` | `mid_late`、`melancholy`、`sigh`、`endless_eight`、`disappearance`、`surprise` |
| `record_kinds` | `scene_memory`、`dialogue_example`、`inner_monologue`、`behavior_observation` |
| `perspectives` | `kyon_first_person`、`spoken_by_character`、`kyon_inner_monologue`、`kyon_observation_not_character_memory` |
| `retrieval_channels` | `canonical_memory`、`dialogue_style`、`internal_voice`、`style_observation` |
| `usages` | `knowledge`、`style_only`、`style_and_memory` |
| `knowledge_owners` | 角色 ID；阿虚视角资料通常为 `kyon` |
| `corpus_versions` | 使用检索结果或语料 manifest 中的实际版本，不硬编码 |

这些是当前生产语料值，不是 HTTP schema 的永久全局枚举。业务聊天通常不应自行拼装
这些过滤条件，服务端会根据目标角色分别检索角色应对素材与导演桥段。

服务端还会强制叠加 `app_id`、角色、模式及 persona policy，调用方不能通过 filters
越过作用域或知识边界。

可查询的 Memory 类型为：

- `user_preference`
- `relationship`
- `roleplay_fact`
- `safety_preference`
- `interaction_summary`

当前 persona 可能只允许其中一部分。显式记忆候选通过
`metadata.memory_write` 传入 `type`、`content`、`reason` 和 0–1 的
`confidence`；默认策略要求置信度至少 0.7，并拒绝临时闲聊和敏感信息。

## 响应、错误和重试

普通 JSON 成功响应：

```json
{
  "ok": true,
  "data": {},
  "request_id": "req-..."
}
```

失败响应：

```json
{
  "ok": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "..."
  },
  "request_id": "req-..."
}
```

| HTTP 状态 | 常见错误 | 建议 |
| --- | --- | --- |
| 400 | `VALIDATION_ERROR`、`SAFETY_BLOCKED` | 修正请求，不自动重试 |
| 401 | `AUTH_INVALID_API_KEY` | 检查或轮换令牌，不重试原凭证 |
| 403 | `AUTH_PERMISSION_DENIED` | 检查 token 与 `app_id` 绑定 |
| 404 | Persona、Session、RAG、Memory 不存在 | 刷新目录或重建对应资源 |
| 410 | `SESSION_EXPIRED` | 新建 Session 后重试 |
| 413 | `REQUEST_BODY_TOO_LARGE` | 缩短消息或语料 |
| 429 | Token 额度、服务限流或模型限流 | 按退避策略重试；额度耗尽需人工处理 |
| 500 | `INTERNAL_ERROR`、`RAG_INGEST_FAILED` | 记录 `request_id`，有限重试 |
| 502/504 | Provider 错误或超时 | 指数退避并设置总重试上限 |

不要只依据 HTTP 状态判断成功；同时检查 envelope 的 `ok`。所有日志应记录
`request_id`，但不要记录令牌、用户消息、完整回复、RAG 正文或 Memory 正文。

## 上线检查清单

- [ ] 使用后端专用服务令牌，并确认它绑定正确的 `app_id`。
- [ ] 业务端只调用 `/health` 和正式 `/v1/...`，不依赖 `/v1/demo/...`。
- [ ] 启动时或定期调用 `/v1/personas`，不硬编码角色和模式。
- [ ] 切换角色或模式时创建新的 Session。
- [ ] POST SSE 使用增量 UTF-8 解析，并处理 `error` 事件。
- [ ] RAG source 正文以纯文本渲染。
- [ ] 对 429、502、504 使用有界指数退避，不无限重试。
- [ ] 日志保留 `request_id`，不保存凭证和对话正文。
- [ ] 为消息长度、生成参数和请求超时设置客户端上限。
- [ ] 不向普通用户暴露模型 alias、Provider、RAG 导入或管理 API。
