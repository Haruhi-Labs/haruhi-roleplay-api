# 访问令牌管理

## 能力边界

本服务把凭证分成两类：

- `ROLEPLAY_API_KEY`：部署时设置的管理密钥，用于创建、查询、调整和吊销服务令牌，也用于配置管理。
- 服务令牌：通过管理 API 创建，格式以 `hrt_` 开头，并绑定单一 `app_id`，供对应业务后端调用角色、会话、聊天、RAG 和 Memory API。

服务令牌不能调用 `/v1/access-tokens`、`/v1/runtime-config` 或 `/v1/env-config/*`。普通用户前端不应持有管理密钥或服务令牌，推荐链路仍然是：

```text
Frontend -> Business Backend -> Haruhi Roleplay API
```

## 服务端配置

```env
ROLEPLAY_API_KEY=replace-with-strong-admin-secret
ACCESS_TOKEN_SQLITE_PATH=.data/access-tokens.sqlite3
```

`ROLEPLAY_API_KEY` 是签发令牌所需的 bootstrap 管理凭证。`ACCESS_TOKEN_SQLITE_PATH` 默认是 `.data/access-tokens.sqlite3`，修改后需要重启。

令牌明文只在创建响应中返回一次。SQLite 只保存 SHA-256 哈希和可识别前缀，不保存可恢复的令牌明文。

## 创建令牌

```bash
curl -X POST http://127.0.0.1:8000/v1/access-tokens \
  -H 'Authorization: Bearer replace-with-strong-admin-secret' \
  -H 'Content-Type: application/json' \
  -d '{"app_id":"order-app","name":"order-service","quota_tokens":100000,"daily_quota_tokens":10000,"weekly_quota_tokens":50000}'
```

请求字段：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `app_id` | 是 | 令牌绑定的唯一业务应用 ID，创建后不可修改 |
| `name` | 是 | 令牌用途或服务名称 |
| `quota_tokens` | 否 | 生命周期模型 Token 总额度；省略或设为 `null` 表示不限额 |
| `daily_quota_tokens` | 否 | UTC 自然日模型 Token 额度；省略或设为 `null` 表示不限额 |
| `weekly_quota_tokens` | 否 | UTC ISO 周模型 Token 额度；省略或设为 `null` 表示不限额 |
| `expires_at` | 否 | 带时区的 ISO-8601 过期时间 |

三种额度可以只设置一项、设置任意两项、全部设置，或全部留空。它们互不替代；所有已设置的额度会同时生效。

创建响应中的 `token` 只显示一次：

```json
{
  "ok": true,
  "data": {
    "token_id": "tok-...",
    "app_id": "order-app",
    "name": "order-service",
    "prefix": "hrt_...",
    "token": "hrt_完整令牌只在这里出现",
    "quota_tokens": 100000,
    "daily_quota_tokens": 10000,
    "weekly_quota_tokens": 50000,
    "total_tokens": 0,
    "daily_tokens": 0,
    "weekly_tokens": 0,
    "remaining_tokens": 100000,
    "daily_remaining_tokens": 10000,
    "weekly_remaining_tokens": 50000,
    "daily_reset_at": "2026-07-15T00:00:00+00:00",
    "weekly_reset_at": "2026-07-20T00:00:00+00:00",
    "exhausted_quota_scopes": []
  },
  "request_id": "req-..."
}
```

## 其它服务配置令牌

把创建时返回的令牌保存在调用方的 Secret Manager 或服务端环境变量中：

```env
HARUHI_ROLEPLAY_TOKEN=hrt_replace_with_issued_token
```

调用时使用任一 Header：

```http
Authorization: Bearer hrt_replace_with_issued_token
```

或：

```http
X-API-Key: hrt_replace_with_issued_token
```

服务端会校验令牌哈希、状态和过期时间。未知、已吊销或已过期令牌返回 `401 AUTH_INVALID_API_KEY`。

HTTP runtime 会在业务 handler 和模型调用前比较服务令牌 scope 与请求 `app_id`：

- session、chat、chat stream、RAG ingest/search 从 JSON body 读取 `app_id`。
- Memory 查询和删除从 query string 读取 `app_id`。
- scope 不匹配或令牌为 legacy unscoped 时返回 `403 AUTH_PERMISSION_DENIED`。
- `/health`、`/v1/personas` 没有 app scope，服务令牌仍可调用。
- `ROLEPLAY_API_KEY` 是管理主体，可跨 app 调用和管理；客户端自定义 Header 不能覆盖 token scope。

缺失或类型错误的 `app_id` 仍由业务 DTO 返回 `VALIDATION_ERROR`。拒绝结果会进入令牌审计日志，但日志不保存 body、query 值或用户内容。

## 旧数据库迁移

服务启动时会检查 `access_tokens` 表。旧表缺少 `app_id`、`daily_quota_tokens` 或 `weekly_quota_tokens` 时会原地增加 nullable 列，不重建表，因此令牌哈希、状态、已有总额度、累计用量和请求日志都会保留。迁移后的旧令牌默认不设置日、周额度。

- 迁移前的令牌返回 `"app_id": null`，表示 legacy unscoped。
- legacy unscoped token 只能访问 `/health`、`/v1/personas` 等无 app route；访问 app-scoped route 返回 `AUTH_PERMISSION_DENIED`。
- 所有新令牌都必须提供非空 `app_id`，不能再创建 unscoped token。
- 升级后应为旧调用方签发绑定 app 的新令牌并吊销旧令牌。

## 额度和用量

本项目自己完成多周期额度控制，不要求上游模型 Provider 原生支持日额度或周额度。Provider 只需返回本次模型用量；没有完整 usage 时，项目沿用回退估算。

| 尺度 | 限额字段 | 已用字段 | 剩余字段 | 窗口 |
| --- | --- | --- | --- | --- |
| 生命周期 | `quota_tokens` | `total_tokens` | `remaining_tokens` | 从令牌创建到吊销，永不自动重置 |
| 每日 | `daily_quota_tokens` | `daily_tokens` | `daily_remaining_tokens` | 每日 00:00 UTC 重置 |
| 每周 | `weekly_quota_tokens` | `weekly_tokens` | `weekly_remaining_tokens` | ISO 周，每周一 00:00 UTC 重置 |

`daily_reset_at` 和 `weekly_reset_at` 给出下一次 UTC 重置时间。周期用量从逐请求日志按当前窗口聚合，窗口切换不会删除历史日志或生命周期累计值。未设置某项额度时，其 quota 和 remaining 字段返回 `null`，已用量与下一次重置时间仍会返回。

聊天完成后，服务端从模型 Provider 的统一 `usage` 中读取：

- `prompt_tokens`
- `completion_tokens`
- `total_tokens`

这些值会同时写入本次请求日志并原子累计到令牌账本。OpenAI-compatible Provider 没有返回 usage 时，会使用项目现有的回退估算。

`POST /v1/chat/stream` 保持惰性 SSE 输出，不会为了计费预先收集完整回复。HTTP runtime 在流中读取 `usage` 事件，并在事件流消费完成后写入用量和审计日志；因此直接调用 runtime 的测试或适配器也必须消费 `response.events` 才会完成本次流式结算。

额度在每次 `POST /v1/chat` 和 `POST /v1/chat/stream` 前检查。所有已配置尺度同时参与判断，只要生命周期、每日或每周任一剩余值为 0，下一次模型请求就会返回：

```json
{
  "ok": false,
  "error": {
    "code": "ACCESS_TOKEN_QUOTA_EXCEEDED",
    "message": "Access token quota has been exhausted."
  },
  "request_id": "req-..."
}
```

HTTP 状态为 `429`。角色目录、会话创建、RAG 和 Memory 等不调用聊天模型的接口不消耗模型 Token 额度。

令牌摘要的 `exhausted_quota_scopes` 会列出当前耗尽的尺度，值可能包含 `total`、`daily`、`weekly` 中的一项或多项，方便管理端说明拒绝原因。

额度按 Provider 报告的实际用量在请求完成后结算，因此最后一个已被接受的请求可能让累计值超过剩余额度；其后的聊天请求会被拒绝。这不是并发预留式硬上限。

管理员可以调整额度：

```http
PATCH /v1/access-tokens/{token_id}
Content-Type: application/json

{
  "quota_tokens": 200000,
  "daily_quota_tokens": 20000,
  "weekly_quota_tokens": null
}
```

PATCH 必须至少包含 `quota_tokens`、`daily_quota_tokens`、`weekly_quota_tokens` 中的一项。省略某项会保留其当前设置；显式设为 `null` 会清除该尺度的限制。降低到当前窗口已用量以下会立即阻止后续聊天，但不会删除历史用量。

## 管理和日志接口

以下接口接受 `ROLEPLAY_API_KEY`，或 `/admin/` 登录后获得的安全后台会话；业务服务令牌不能访问：

| 接口 | 用途 |
| --- | --- |
| `POST /v1/access-tokens` | 创建绑定 `app_id` 的令牌并一次性返回明文 |
| `GET /v1/access-tokens` | 列举 app scope、安全摘要和累计用量 |
| `GET /v1/access-tokens/{token_id}` | 查询 app scope 和令牌详情 |
| `PATCH /v1/access-tokens/{token_id}` | 调整额度 |
| `DELETE /v1/access-tokens/{token_id}` | 吊销令牌 |
| `GET /v1/access-tokens/{token_id}/logs?limit=50` | 查询逐令牌请求日志 |

日志按时间倒序返回，`limit` 默认为 50，最大为 200。每条日志包含令牌 ID、请求 ID、HTTP 方法、路径、状态码、耗时、错误码和模型 Token 用量。日志不保存 Header、令牌明文、请求正文、用户消息或模型回复。

Token 用量优先使用模型 provider 返回的真实 usage。OpenAI-compatible provider 未返回某个 usage 字段时，服务会根据输入消息或回复长度进行轻量估算；该值用于额度保护，不等同于厂商 tokenizer 的账单精度。负数或不可解析字段按 `0` 处理。SSE 流中出现 provider 错误时，审计日志会记录 `data.error.code`。

## 运维建议

- 为每个调用服务和 `app_id` 创建独立令牌，不要跨应用共享。
- 使用清晰的 `name` 标明环境和服务，例如 `prod-order-service`。
- 定期查询用量和日志，发现异常后立即吊销。
- 令牌泄露时创建新令牌、更新调用方 Secret，再吊销旧令牌。
- 备份 `.data/access-tokens.sqlite3`；它同时保存令牌校验数据、额度、累计用量、业务请求日志和管理员审计日志。
- 不要把令牌写入仓库、前端代码、URL、日志或错误信息。
