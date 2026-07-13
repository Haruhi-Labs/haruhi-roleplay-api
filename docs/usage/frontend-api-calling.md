# 前端调用完整文档

## 文档定位

这份文档说明前端、业务后端或本地 demo 如何调用 Haruhi Roleplay API。

推荐生产链路：

```text
Frontend -> Your Business Backend -> Haruhi Roleplay API
```

本地开发可以直接打开仓库自带 demo：

```text
http://127.0.0.1:8000/demo
```

普通用户前端不应该持有 `ROLEPLAY_API_KEY`。`ROLEPLAY_API_KEY` 只用于受信任管理面；业务后端应使用 `/v1/access-tokens` 签发的独立服务令牌调用本服务。完整流程见 `docs/usage/access-token-management.md`。

## 快速启动

PowerShell：

```powershell
cd E:\haruhi-roleplay-api
Copy-Item .env.example .env
$env:PYTHONPATH="src"
uv run python -m haruhi_roleplay_api.infrastructure.http_server
```

默认访问：

```text
聊天 demo: http://127.0.0.1:8000/demo
配置 editor: http://127.0.0.1:8000/config
API base: http://127.0.0.1:8000
```

如果 `.env` 中设置了管理密钥：

```env
ROLEPLAY_API_KEY=dev-secret
```

管理接口使用该密钥；业务接口推荐使用签发的 `hrt_...` 服务令牌。两者都使用相同 Header 形状：

```http
Authorization: Bearer dev-secret
```

或：

```http
X-API-Key: dev-secret
```

## 通用约定

### Header

| Header                                     | 必填                                | 说明                |
| ------------------------------------------ | ----------------------------------- | ------------------- |
| `Content-Type: application/json`           | POST/PATCH 必填                     | JSON 请求体         |
| `Authorization: Bearer <token>` | 启用鉴权时必填                 | 管理密钥或服务令牌鉴权 |
| `X-API-Key: <token>`            | 可替代 Authorization           | 管理密钥或服务令牌鉴权 |
| `X-Request-Id`                             | 否                                  | 调用方生成的追踪 ID |

### 响应 envelope

成功：

```json
{
  "ok": true,
  "data": {},
  "request_id": "req-..."
}
```

失败：

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

前端应优先展示 `error.message`，并把 `request_id` 记录到调试日志。

## 前端最小调用流程

### 1. 读取角色和 preset

```http
GET /v1/personas
```

TypeScript：

```ts
const res = await fetch(`${baseUrl}/v1/personas`, {
  headers: { Authorization: `Bearer ${apiKey}` },
});
const body = await res.json();
if (!body.ok) throw new Error(body.error.message);
const characters = body.data.characters;
```

前端应从返回的 catalog 中展示 `character_id` 和 `persona_mode`，不要硬编码固定三种春日模式。

### 2. 可选：创建连续会话

```http
POST /v1/sessions
```

请求：

```json
{
  "app_id": "web-demo",
  "user_id": "user-123",
  "character_id": "haruhi",
  "persona_mode": "mid_late_haruhi"
}
```

响应中的 `session_id` 后续传给 `/v1/chat`，并设置 `capabilities.continuous_session=true`。

### 3. 发送非流式消息

```http
POST /v1/chat
```

请求：

```json
{
  "app_id": "web-demo",
  "user_id": "user-123",
  "session_id": "optional-session-id",
  "character_id": "haruhi",
  "persona_mode": "mid_late_haruhi",
  "message": "今天社团要做什么？",
  "language": "zh-CN",
  "capabilities": {
    "rag": false,
    "memory": false,
    "continuous_session": false,
    "safety_filter": true,
    "debug_trace": false,
    "stream": false
  },
  "generation": {
    "model": "fake-roleplay-model"
  }
}
```

响应：

```json
{
  "ok": true,
  "data": {
    "session_id": "optional-session-id",
    "character_id": "haruhi",
    "persona_mode": "mid_late_haruhi",
    "reply": "...",
    "usage": {
      "provider": "fake",
      "model": "fake-roleplay-model"
    },
    "rag": { "enabled": false },
    "memory": { "enabled": false },
    "debug": null
  },
  "request_id": "req-..."
}
```

前端展示 `data.reply`。如果 `data.rag.sources` 存在，可以在回复下方展示 sources 摘要。

### 4. 发送流式消息

```http
POST /v1/chat/stream
```

请求体与 `/v1/chat` 相同，但服务端会把 `capabilities.stream` 视为 true。

当前 HTTP runtime 返回 `text/event-stream`。事件顺序：

```text
start -> source* -> delta+ -> usage -> done
```

事件类型：

| event    | 前端行为                                             |
| -------- | ---------------------------------------------------- |
| `start`  | 创建 assistant 消息占位                              |
| `source` | 缓存 RAG source                                      |
| `delta`  | 追加 `data.text`                                     |
| `usage`  | 更新 provider/model/usage 摘要                       |
| `done`   | 标记完成，读取完整 `reply`、`rag`、`memory`、`debug` |
| `error`  | 标记失败，展示错误                                   |

POST SSE 不能直接用浏览器原生 `EventSource`。推荐使用 `fetch()` + `ReadableStream`：

```ts
async function streamChat(baseUrl: string, apiKey: string, payload: unknown) {
  const res = await fetch(`${baseUrl}/v1/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok || !res.body) {
    throw new Error(`HTTP ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";
    for (const block of blocks) {
      const event = parseSseBlock(block);
      if (!event) continue;
      // handle event.event and event.data
    }
  }
}

function parseSseBlock(block: string) {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (!dataLines.length) return null;
  return { event, data: JSON.parse(dataLines.join("\n")) };
}
```

## RAG 调用方式

### 导入文档

```http
POST /v1/rag/documents
```

请求：

```json
{
  "app_id": "web-demo",
  "document_id": "demo-note-1",
  "title": "SOS 团活动计划",
  "source_type": "timeline",
  "character_id": "haruhi",
  "persona_mode": "mid_late_haruhi",
  "timeline": "mid_late",
  "spoiler_level": 2,
  "language": "zh-CN",
  "content": "社团活动计划：春日会主动安排调查、招募和临时会议。"
}
```

返回 `status=imported` 表示已写入当前 RAG provider；返回 `validated` 表示只完成 metadata 校验。

### 直接检索

```http
POST /v1/rag/search
```

用于后台调试，不建议普通聊天 UI 暴露。

### 在 chat 中启用 RAG

把 chat 请求中的 capability 打开：

```json
{
  "capabilities": {
    "rag": true
  }
}
```

前端只控制是否请求 RAG，具体使用本地 RAG、Chroma、Qdrant 由服务端配置决定。

## Memory 调用方式

### 在 chat 中启用 memory

```json
{
  "capabilities": {
    "memory": true
  }
}
```

当前 memory store 是服务端进程内实现。chat 只会读取有限记忆，并只写入显式候选。

### 显式写入候选

```json
{
  "metadata": {
    "memory_write": {
      "type": "preference",
      "content": "用户喜欢轻松吐槽风格。",
      "reason": "用户明确表达稳定偏好",
      "confidence": 0.8
    }
  }
}
```

不要让前端从普通聊天内容里自由抽取 memory。业务后端如果要提交候选，必须给出 `reason` 和 `confidence`。

### 查询和删除 memory

```http
GET /v1/memory/{user_id}?app_id=web-demo&character_id=haruhi&persona_mode=mid_late_haruhi
DELETE /v1/memory/{user_id}/{memory_id}?app_id=web-demo&character_id=haruhi&persona_mode=mid_late_haruhi
```

这更适合角色设置页、隐私页或后台管理页，不建议放在普通聊天主流程里。

## 本地 demo 页面调用关系

`/demo` 页面会调用：

| 页面操作    | API                      |
| ----------- | ------------------------ |
| 打开页面    | `GET /v1/personas`       |
| New Session | `POST /v1/sessions`      |
| Send 非流式 | `POST /v1/chat`          |
| Send 流式   | `POST /v1/chat/stream`   |
| Import RAG  | `POST /v1/rag/documents` |

`/config` 页面会调用：

| 页面操作     | API                                                |
| ------------ | -------------------------------------------------- |
| 连接配置服务 | `GET /v1/env-config/schema` + `GET /v1/env-config` |
| 字段 check   | `POST /v1/env-config/check`                        |
| 保存 `.env`  | `PATCH /v1/env-config`                             |

`/config` 是受信任管理页面，不应该给普通用户访问。

## 前端状态建议

| 状态        | 触发条件                                         |
| ----------- | ------------------------------------------------ |
| `idle`      | 尚未发送                                         |
| `sending`   | 请求已发出                                       |
| `streaming` | 已收到 `start` 或 `delta`                        |
| `completed` | 收到普通响应或 stream `done`                     |
| `failed`    | HTTP 错误、envelope `ok=false` 或 stream `error` |

## 前端安全边界

前端可以传：

- `character_id`
- `persona_mode`
- `message`
- `session_id`
- `capabilities.rag`
- `capabilities.memory`
- `capabilities.continuous_session`
- `capabilities.stream`
- 服务端允许的 `generation.model` alias

前端不要传或展示：

- provider 类型，例如 `openai`、`ollama`、`qdrant`
- base URL
- API key、token、secret、`DATABASE_URL`
- 完整 system prompt
- backend context source
- 原始 RAG chunk 全文，除非产品明确需要
- debug trace 给普通用户

## 错误处理建议

| error.code                                     | 前端行为                                      |
| ---------------------------------------------- | --------------------------------------------- |
| `AUTH_INVALID_API_KEY`                         | 本地 demo 提示 API key 错误；生产前端不应看到 |
| `AUTH_PERMISSION_DENIED`                       | 管理接口权限不足                              |
| `VALIDATION_ERROR`                             | 标记表单或请求参数错误                        |
| `REQUEST_BODY_TOO_LARGE`                       | 阻止提交并提示缩短消息或 RAG 文档             |
| `PERSONA_NOT_FOUND` / `PERSONA_MODE_NOT_FOUND` | 重新加载 persona catalog                      |
| `SESSION_NOT_FOUND` / `SESSION_EXPIRED`        | 新建 session 并提示用户                       |
| `RAG_PROVIDER_ERROR`                           | 降级为无 RAG 或提示后台配置错误               |
| `MODEL_PROVIDER_ERROR` / `MODEL_TIMEOUT`       | 展示模型暂不可用                              |
| `MEMORY_ACCESS_DENIED`                         | 不展示 memory 管理操作                        |

## 接入检查清单

- [ ] 页面启动时读取 `GET /v1/personas`。
- [ ] `character_id` 和 `persona_mode` 只来自 catalog。
- [ ] 普通前端不保存 `ROLEPLAY_API_KEY`。
- [ ] 生产环境通过业务后端转发请求。
- [ ] stream 用 `fetch()` + `ReadableStream` 解析 POST SSE。
- [ ] `debug` 只进入开发者面板。
- [ ] RAG source 与角色回复分开展示。
- [ ] session 过期时能重新创建 session。
- [ ] `.env` 管理只放在受信任后台或本地 `/config`。
