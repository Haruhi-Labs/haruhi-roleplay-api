# 快速开始：从后端配置到前端第一条回复

本文面向第一次使用本项目的人。目标是用最少步骤完成一条真实链路：

```text
前端 -> 业务后端 -> Haruhi Roleplay API -> LLM / RAG / SQLite -> 统一响应
```

完成本文后，你会得到：

- 一个可访问的 Roleplay API 服务。
- 一个绑定 `app_id` 的业务服务令牌。
- 一次角色目录查询和一次聊天回复。
- 一段可以放进业务后端的最小调用代码。

## 先选启动方式

| 目的 | 推荐方式 | 需要准备 |
| --- | --- | --- |
| 先确认项目能跑 | 本地 fake | Python 3.12+、uv |
| 本地接真实模型 | 本地 Python | uv、模型或云 API 凭证 |
| Linux 单机部署 | Docker Compose | Docker、Docker Compose、云端 LLM/RAG 地址 |

第一次使用建议先跑 fake。fake 会走完整 HTTP、角色、Agent、Prompt、Session 和 Memory 装配链路，但不会访问真实模型，也不会产生模型费用。

## 1. 写后端配置文件

在项目根目录复制模板：

PowerShell：

```powershell
Copy-Item .env.example .env
```

Bash：

```bash
cp .env.example .env
```

先保留模板中的本地配置：

```env
ROLEPLAY_HOST=127.0.0.1
ROLEPLAY_PORT=8000
ROLEPLAY_API_KEY=change-me-local-admin-key
ROLEPLAY_CORS_ORIGINS=

LLM_API_TYPE=fake
LLM_MODEL=fake-roleplay-model
EMBEDDING_API_TYPE=hash
EMBEDDING_DIMENSIONS=384
RAG_API_TYPE=local

SESSION_PROVIDER=sqlite
SESSION_SQLITE_PATH=.data/sessions.sqlite3
MEMORY_PROVIDER=sqlite
MEMORY_SQLITE_PATH=.data/memories.sqlite3
ACCESS_TOKEN_SQLITE_PATH=.data/access-tokens.sqlite3
```

`change-me-local-admin-key` 只适合绑定 `127.0.0.1` 的本地体验。非 loopback 监听会拒绝占位密钥和少于 32 字符的密钥。

## 2. 启动服务

PowerShell：

```powershell
$env:PYTHONPATH="src"
uv run python -m haruhi_roleplay_api.infrastructure.http_server
```

Bash：

```bash
PYTHONPATH=src uv run python -m haruhi_roleplay_api.infrastructure.http_server
```

看到以下输出表示 HTTP server 已监听：

```text
haruhi-roleplay-api listening on http://127.0.0.1:8000
```

保持这个终端运行，另开一个终端完成后续请求。

## 3. 验证健康状态

PowerShell：

```powershell
$baseUrl = "http://127.0.0.1:8000"
$adminKey = "change-me-local-admin-key"
$adminHeaders = @{ Authorization = "Bearer $adminKey" }
Invoke-RestMethod -Uri "$baseUrl/health" -Headers $adminHeaders
```

Bash：

```bash
curl -H 'Authorization: Bearer change-me-local-admin-key' \
  http://127.0.0.1:8000/health
```

成功响应的顶层字段是 `ok: true`。如果返回 `AUTH_INVALID_API_KEY`，检查请求 Header 是否与 `.env` 的 `ROLEPLAY_API_KEY` 一致。

## 4. 创建业务服务令牌

管理密钥只用于配置和令牌管理。业务后端应使用绑定 `app_id` 的 `hrt_...` 服务令牌。

PowerShell：

```powershell
$adminHeaders = @{
  Authorization = "Bearer $adminKey"
  "Content-Type" = "application/json"
}
$tokenBody = @{
  app_id = "web-demo"
  name = "local-business-backend"
  quota_tokens = 100000
} | ConvertTo-Json
$issued = Invoke-RestMethod `
  -Method POST `
  -Uri "$baseUrl/v1/access-tokens" `
  -Headers $adminHeaders `
  -Body $tokenBody
$serviceToken = $issued.data.token
```

Bash：

```bash
curl -X POST http://127.0.0.1:8000/v1/access-tokens \
  -H 'Authorization: Bearer change-me-local-admin-key' \
  -H 'Content-Type: application/json' \
  -d '{"app_id":"web-demo","name":"local-business-backend","quota_tokens":100000}'
```

响应中的 `data.token` 只返回一次。生产环境应把它放进业务后端的 Secret Manager 或环境变量，不要放进浏览器代码、Git 或日志。

## 5. 查询角色并发送消息

PowerShell：

```powershell
$serviceHeaders = @{
  Authorization = "Bearer $serviceToken"
  "Content-Type" = "application/json"
}
Invoke-RestMethod -Uri "$baseUrl/v1/personas" -Headers $serviceHeaders

$chatBody = @{
  app_id = "web-demo"
  user_id = "user-001"
  character_id = "haruhi"
  persona_mode = "mid_late_haruhi"
  message = "今天社团要做什么？"
  language = "zh-CN"
} | ConvertTo-Json

$reply = Invoke-RestMethod `
  -Method POST `
  -Uri "$baseUrl/v1/chat" `
  -Headers $serviceHeaders `
  -Body $chatBody
$reply.data.reply
```

Bash：

```bash
curl -X POST http://127.0.0.1:8000/v1/chat \
  -H 'Authorization: Bearer hrt_replace_with_issued_token' \
  -H 'Content-Type: application/json' \
  -d '{"app_id":"web-demo","user_id":"user-001","character_id":"haruhi","persona_mode":"mid_late_haruhi","message":"今天社团要做什么？","language":"zh-CN"}'
```

普通聊天只需要这 6 个业务字段。不要从前端传 provider、base URL、模型密钥或数据库配置；这些都由本项目读取 `.env` 后调度。

## 6. 打开自带前端 Demo

浏览器访问：

```text
http://127.0.0.1:8000/demo
```

本地体验时，在 Demo 的 API Key 输入框填入刚签发的 `hrt_...` 服务令牌，并保持 `App ID` 为 `web-demo`。然后选择接口返回的角色和 preset，发送消息即可。

配置编辑器位于：

```text
http://127.0.0.1:8000/config
```

配置编辑器必须使用 `ROLEPLAY_API_KEY`，不能使用服务令牌。它只应部署在受信任管理网络中。

## 7. 接入自己的前端

生产环境推荐让浏览器只调用你的业务后端：

```text
Browser -> POST /api/roleplay/chat -> Business Backend -> POST /v1/chat
```

业务后端保存以下环境变量：

```env
HARUHI_ROLEPLAY_BASE_URL=http://127.0.0.1:8000
HARUHI_ROLEPLAY_TOKEN=hrt_replace_with_issued_token
HARUHI_ROLEPLAY_APP_ID=web-demo
```

Node.js 18+ 业务后端的最小转发函数：

```js
export async function sendRoleplayMessage({ userId, characterId, personaMode, message }) {
  const response = await fetch(`${process.env.HARUHI_ROLEPLAY_BASE_URL}/v1/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${process.env.HARUHI_ROLEPLAY_TOKEN}`,
    },
    body: JSON.stringify({
      app_id: process.env.HARUHI_ROLEPLAY_APP_ID,
      user_id: userId,
      character_id: characterId,
      persona_mode: personaMode,
      message,
      language: "zh-CN",
    }),
  });
  const body = await response.json();
  if (!response.ok || !body.ok) throw new Error(body.error?.message || `HTTP ${response.status}`);
  return body.data;
}
```

浏览器只提交 `message` 和选择结果；`app_id`、服务令牌以及真实 `user_id` 应由业务后端根据登录状态补齐。角色选择应来自 `GET /v1/personas`，不要在前端硬编码角色名单。

## 8. 切换到真实后端

先停止服务，修改 `.env`，再重新启动。

### 标准云模型

OpenAI、DeepSeek、Gemini 已有内置 API base URL，最少填写 API type、模型名和令牌：

```env
LLM_API_TYPE=gemini
LLM_MODEL=<provider-model-name>
LLM_API_KEY=<secret>
```

只有使用代理、私有网关或兼容服务时才填写 `LLM_BASE_URL`。

### OpenAI-compatible 模型

```env
LLM_API_TYPE=openai_compatible
LLM_BASE_URL=https://your-provider.example/v1
LLM_MODEL=<provider-model-name>
LLM_API_KEY=<secret-if-required>
```

### Ollama

```env
LLM_API_TYPE=ollama
LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_MODEL=qwen2.5:7b
```

### Qdrant 向量 RAG

向量 RAG 必须同时配置 embedding，并保证 embedding 维度与 Qdrant collection 一致：

```env
EMBEDDING_API_TYPE=openai_compatible
EMBEDDING_BASE_URL=https://your-embedding-provider.example/v1
EMBEDDING_MODEL=<embedding-model-name>
EMBEDDING_API_KEY=<secret>
EMBEDDING_DIMENSIONS=1024

RAG_API_TYPE=qdrant
RAG_BASE_URL=https://your-qdrant.example
RAG_INDEX=haruhi_rag
RAG_API_KEY=<secret-if-required>
```

配置真实 provider 后，先用 `/config` 的 Check 检查字段，再分别做一次 `/v1/chat`、RAG 导入和 RAG chat。字段校验成功只证明配置结构有效，不证明外部服务、模型名、权限或向量维度正确。

## 9. Docker Compose 启动

Compose 只封装本服务，不自动启动 LLM、Qdrant 或 PostgreSQL：

```bash
cp .env.compose.example .env
python -c "import secrets; print(secrets.token_urlsafe(32))"
# 把输出写入 .env 的 ROLEPLAY_API_KEY
docker compose up -d --build
docker compose logs -f roleplay-api
```

容器默认只映射到宿主机 `127.0.0.1`。容器访问宿主机模型时，`127.0.0.1` 指向容器自身；请改用容器可访问的宿主机地址或外部 provider URL。

SQLite 数据保存在宿主机 `./.data/`。默认 `RAG_API_TYPE=local` 的文本索引只在当前进程内，不是持久化生产 RAG；需要持久化检索时使用 Qdrant，或在安装对应可选依赖后使用 Chroma。

## 常见失败

| 现象 | 检查项 |
| --- | --- |
| 启动时报强密钥错误 | 非 loopback 监听必须使用至少 32 字符的非占位 `ROLEPLAY_API_KEY` |
| `401 AUTH_INVALID_API_KEY` | Header 中令牌是否正确，令牌是否已吊销或过期 |
| `403 AUTH_PERMISSION_DENIED` | 服务令牌的 `app_id` 是否与请求 body 中的 `app_id` 一致 |
| `PERSONA_NOT_FOUND` | 重新调用 `GET /v1/personas`，不要硬编码不存在的角色 |
| `MODEL_PROVIDER_ERROR` | API type、模型名、base URL、令牌和外部服务连通性 |
| `RAG_PROVIDER_ERROR` | embedding 维度、collection 维度、Qdrant URL、权限和 `app_id` 数据隔离 |
| 浏览器跨域失败 | 把完整 Origin 写入 `ROLEPLAY_CORS_ORIGINS`，不能写 `*` 或路径，并重启服务 |
| 配置保存后没生效 | 查看 `restart_required_keys`；HTTP、CORS、Session、Memory 和数据路径需要重启 |

## 下一步文档

- 后端全部简单配置：[backend-config.md](backend-config.md)
- 前端非流式和 SSE 调用：[frontend-api-calling.md](frontend-api-calling.md)
- 服务令牌管理：[access-token-management.md](access-token-management.md)
- 完整接口参数：[interface-reference.md](interface-reference.md)
- Docker Compose 生产边界：[docker-compose.md](docker-compose.md)
