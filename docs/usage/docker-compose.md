# Docker Compose 使用说明

本项目提供一个最小 `docker-compose.yml`：只启动 `roleplay-api` 一个服务，不内置 Qdrant、PostgreSQL、Ollama、Chroma 或前端构建链。

## 启动

```bash
cp .env.compose.example .env
docker compose up -d --build
docker compose logs -f roleplay-api
```

检查服务：

```bash
curl -H "Authorization: Bearer change-me" http://127.0.0.1:8000/health
```

静态 demo：

```text
http://127.0.0.1:8000/demo
http://127.0.0.1:8000/config
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

容器内会绑定 `0.0.0.0:$ROLEPLAY_PORT`，Compose 会映射同一个宿主机端口。

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

## 数据位置

Compose 只挂载一个本地数据目录：

```text
./.data:/app/.data
```

SQLite session 默认写入：

```text
.data/sessions.sqlite3
```

运行时配置面板保存的配置会写入容器内 `/app/.data/runtime.env`，因此也会落在宿主机 `./.data/runtime.env`。

## 停止

```bash
docker compose down
```

这不会删除 `./.data`。
