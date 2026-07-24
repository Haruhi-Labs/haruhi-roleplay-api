# Docker Compose 使用说明

本项目提供一个最小 `docker-compose.yml`：只启动 `roleplay-api` 一个服务，不内置 Qdrant、PostgreSQL、Ollama、Chroma 或前端构建链。

## 启动

```bash
cp .env.compose.example .env
python -c "import secrets; print(secrets.token_urlsafe(32))"
# 将输出写入 .env 的 ROLEPLAY_API_KEY 后再启动
docker compose up -d --build
docker compose logs -f roleplay-api
```

检查服务：

```bash
curl -H "Authorization: Bearer <ROLEPLAY_API_KEY>" http://127.0.0.1:8000/health
```

调试页面：

```text
调试工作台: http://127.0.0.1:8000/chat/
原始开发页: http://127.0.0.1:8000/demo
配置编辑器: http://127.0.0.1:8000/config
```

## 端口

宿主机端口由 `.env` 的 `ROLEPLAY_PORT` 控制：

```env
ROLEPLAY_PORT=8010
```

重启后访问：

```text
http://127.0.0.1:8010/health
```

容器内会绑定 `0.0.0.0:$ROLEPLAY_PORT`，因此启动前必须把 `ROLEPLAY_API_KEY` 替换为至少 32 字符的非占位密钥。Compose 默认只把端口映射到宿主机 `127.0.0.1`，避免应用 server 直接暴露公网。

## 配置

默认 `.env.compose.example` 使用 fake LLM 和本地 RAG，目的是让容器先能启动。接入真实服务时，改 `.env` 中的 provider 字段即可。

Gemini + Qdrant 示例：

```env
LLM_API_TYPE=gemini
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
LLM_MODEL=gemini-2.5-flash
LLM_API_KEY=replace-with-token

EMBEDDING_API_TYPE=openai_compatible
EMBEDDING_BASE_URL=https://your-embedding-endpoint.example/v1
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_API_KEY=replace-with-token
EMBEDDING_DIMENSIONS=1536

RAG_API_TYPE=qdrant
RAG_BASE_URL=https://your-qdrant.example
RAG_INDEX=haruhi_rag
RAG_API_KEY=replace-with-token
```

修改 `.env` 后重建或重启：

```bash
docker compose up -d --build
```

浏览器跨域访问时配置精确 Origin；同源部署留空即可：

```env
ROLEPLAY_CORS_ORIGINS=https://app.example.com,https://admin.example.com
```

不支持 `*`。修改后需要重启容器。

## 公网入口边界

生产环境应由宿主机 Caddy、Nginx 或云入口代理到 `127.0.0.1:$ROLEPLAY_PORT`。反向代理负责：

- TLS 证书和 HTTPS。
- 公网请求速率限制、并发连接上限和请求超时。
- 可信代理链中的真实客户端 IP。
- 只公开业务 API；`/config`、`/v1/env-config/*`、`/v1/runtime-config` 和 `/v1/access-tokens/*` 应额外限制来源。

应用自身继续负责 API Key、服务 Access Token、app scope、请求大小和模型额度。不要把 Compose 端口改成公网映射后绕过反向代理。

当前标准库 HTTP server 始终以 TCP 对端地址作为客户端 IP，并覆盖调用方传入的同名内部 Header；它不会信任 `X-Forwarded-For` 等转发头。经反向代理部署时，应用内的后台登录失败限流会把代理视为同一来源，因此反向代理必须再按其可信代理链解析出的真实客户端 IP，对 `/v1/admin/login` 实施独立限流和来源限制。项目目前没有受信任代理名单配置，不要把任意公网转发头直接当作可信客户端地址传入应用。

## 数据位置

Compose 只挂载一个本地数据目录：

```text
./.data:/app/.data
```

SQLite session 默认写入：

```text
.data/sessions.sqlite3
```

SQLite memory 默认写入：

```text
.data/memories.sqlite3
```

访问令牌账本、逐令牌用量和请求日志默认写入：

```text
.data/access-tokens.sqlite3
```

运行时配置面板保存的配置会写入容器内 `/app/.data/runtime.env`，因此也会落在宿主机 `./.data/runtime.env`。

## 停止

```bash
docker compose down
```

这不会删除 `./.data`。
