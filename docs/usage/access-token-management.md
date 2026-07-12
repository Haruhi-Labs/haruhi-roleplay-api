# 访问令牌管理

## 能力边界

本服务把凭证分成两类：

- `ROLEPLAY_API_KEY`：部署时设置的管理密钥，用于创建、查询、调整和吊销服务令牌，也用于配置管理。
- 服务令牌：通过管理 API 创建，格式以 `hrt_` 开头，供其它后端服务调用角色、会话、聊天、RAG 和 Memory API。

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
  -d '{"name":"order-service","quota_tokens":100000}'
```

请求字段：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `name` | 是 | 令牌用途或服务名称 |
| `quota_tokens` | 否 | 模型 Token 总额度；省略表示不限额 |
| `expires_at` | 否 | 带时区的 ISO-8601 过期时间 |

创建响应中的 `token` 只显示一次：

```json
{
  "ok": true,
  "data": {
    "token_id": "tok-...",
    "name": "order-service",
    "prefix": "hrt_...",
    "token": "hrt_完整令牌只在这里出现",
    "quota_tokens": 100000,
    "total_tokens": 0,
    "remaining_tokens": 100000
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

## 额度和用量

聊天完成后，服务端从模型 Provider 的统一 `usage` 中读取：

- `prompt_tokens`
- `completion_tokens`
- `total_tokens`

这些值会同时写入本次请求日志并原子累计到令牌账本。OpenAI-compatible Provider 没有返回 usage 时，会使用项目现有的回退估算。

`POST /v1/chat/stream` 保持惰性 SSE 输出，不会为了计费预先收集完整回复。HTTP runtime 在流中读取 `usage` 事件，并在事件流消费完成后写入用量和审计日志；因此直接调用 runtime 的测试或适配器也必须消费 `response.events` 才会完成本次流式结算。

额度在每次 `POST /v1/chat` 和 `POST /v1/chat/stream` 前检查。已用量达到额度后返回：

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

额度按 Provider 报告的实际用量在请求完成后结算，因此最后一个已被接受的请求可能让累计值超过剩余额度；其后的聊天请求会被拒绝。这不是并发预留式硬上限。

管理员可以调整额度：

```http
PATCH /v1/access-tokens/{token_id}
Content-Type: application/json

{"quota_tokens": 200000}
```

`quota_tokens` 设为 `null` 表示不限额。降低到已用量以下会立即阻止后续聊天，但不会删除历史用量。

## 管理和日志接口

以下接口只接受 `ROLEPLAY_API_KEY`：

| 接口 | 用途 |
| --- | --- |
| `POST /v1/access-tokens` | 创建令牌并一次性返回明文 |
| `GET /v1/access-tokens` | 列举安全摘要和累计用量 |
| `GET /v1/access-tokens/{token_id}` | 查询一个令牌 |
| `PATCH /v1/access-tokens/{token_id}` | 调整额度 |
| `DELETE /v1/access-tokens/{token_id}` | 吊销令牌 |
| `GET /v1/access-tokens/{token_id}/logs?limit=50` | 查询逐令牌请求日志 |

日志按时间倒序返回，`limit` 默认为 50，最大为 200。每条日志包含令牌 ID、请求 ID、HTTP 方法、路径、状态码、耗时、错误码和模型 Token 用量。日志不保存 Header、令牌明文、请求正文、用户消息或模型回复。

## 运维建议

- 为每个调用服务创建独立令牌，不要跨服务共享。
- 使用清晰的 `name` 标明环境和服务，例如 `prod-order-service`。
- 定期查询用量和日志，发现异常后立即吊销。
- 令牌泄露时创建新令牌、更新调用方 Secret，再吊销旧令牌。
- 备份 `.data/access-tokens.sqlite3`；它同时保存令牌校验数据、额度、累计用量和审计日志。
- 不要把令牌写入仓库、前端代码、URL、日志或错误信息。
