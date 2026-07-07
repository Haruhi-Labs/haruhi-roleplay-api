# Docker Compose 使用说明

## 文档定位

本文只说明未来 Docker Compose 封装完成后的使用方式。实现计划和任务拆分在 `docs/agent-dev/cards/10.*.md`。

当前状态：酒馆式 provider 配置字段已经实现；Docker Compose 封装仍在后续 `10.01` 中实现。

目标是让个人用户用一个 compose 服务启动 Haruhi Roleplay API，再通过类似酒馆的配置方式接入 LLM、Embedding 和 RAG：

- 选择 API type / provider。
- 填写 base URL。
- 填写模型名或 RAG index。
- 填写 token。

这里的“预设”只表示 API 类型/provider 选择器，不表示一整套部署方案。

## 最小启动

实现后推荐使用：

```bash
cp .env.compose.example .env
docker compose up -d
docker compose logs -f roleplay-api
curl http://127.0.0.1:8000/health
```

如果修改宿主机端口：

```env
ROLEPLAY_PORT=8010
```

则访问：

```text
http://127.0.0.1:8010/health
http://127.0.0.1:8010/demo
http://127.0.0.1:8010/config
```

## 最小配置形状

```env
ROLEPLAY_API_KEY=change-me
ROLEPLAY_PORT=8000

LLM_API_TYPE=openai
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4.1-mini
LLM_API_KEY=replace-with-token

EMBEDDING_API_TYPE=openai
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_API_KEY=replace-with-token

RAG_API_TYPE=qdrant
RAG_BASE_URL=https://your-qdrant.example
RAG_INDEX=haruhi_rag
RAG_API_KEY=replace-with-token

SESSION_PROVIDER=sqlite
SESSION_SQLITE_PATH=/app/data/sessions.sqlite3
SESSION_RECENT_LIMIT=12
ENABLE_DEBUG_TRACE=false
AGENT_CONTEXT_PLANNER=deterministic
```

## 字段含义

| 字段                  | 含义                                                                              |
| --------------------- | --------------------------------------------------------------------------------- |
| `ROLEPLAY_API_KEY`    | 本项目管理接口和受保护 API 的 key。                                               |
| `ROLEPLAY_PORT`       | 宿主机暴露端口，默认 `8000`。                                                     |
| `LLM_API_TYPE`        | LLM API 类型/provider，例如 `openai`、`openai_compatible`、`deepseek`、`gemini`。 |
| `LLM_BASE_URL`        | LLM API base URL。                                                                |
| `LLM_MODEL`           | LLM 模型名。                                                                      |
| `LLM_API_KEY`         | LLM token。                                                                       |
| `EMBEDDING_API_TYPE`  | Embedding API 类型/provider，例如 `openai`、`openai_compatible`、`ollama`。       |
| `EMBEDDING_BASE_URL`  | Embedding API base URL。                                                          |
| `EMBEDDING_MODEL`     | Embedding 模型名。                                                                |
| `EMBEDDING_API_KEY`   | Embedding token。                                                                 |
| `RAG_API_TYPE`        | RAG / vector API 类型/provider，例如 `qdrant` 或后续云端 RAG provider。           |
| `RAG_BASE_URL`        | RAG 服务 base URL。                                                               |
| `RAG_INDEX`           | collection、index 或 vector store id。                                            |
| `RAG_API_KEY`         | RAG token。                                                                       |
| `SESSION_PROVIDER`    | 默认 `sqlite`。                                                                   |
| `SESSION_SQLITE_PATH` | 容器内 SQLite 文件位置，默认放在 `/app/data`。                                    |

普通前端仍然不传 provider、base URL 或 token。前端只调用本项目 HTTP API，并传 `character_id`、`persona_mode`、`message`、`session_id`、`capabilities` 和可选的服务端模型 alias。

## Provider 示例

### OpenAI

```env
LLM_API_TYPE=openai
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4.1-mini
LLM_API_KEY=replace-with-token
```

### OpenAI-Compatible

```env
LLM_API_TYPE=openai_compatible
LLM_BASE_URL=https://your-gateway.example/v1
LLM_MODEL=your-model-name
LLM_API_KEY=replace-with-token
```

### DeepSeek

```env
LLM_API_TYPE=deepseek
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
LLM_API_KEY=replace-with-token
```

### Gemini

```env
LLM_API_TYPE=gemini
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
LLM_MODEL=gemini-2.5-flash
LLM_API_KEY=replace-with-token
```

### Qdrant RAG

```env
RAG_API_TYPE=qdrant
RAG_BASE_URL=https://your-qdrant.example
RAG_INDEX=haruhi_rag
RAG_API_KEY=replace-with-token
```

### OpenAI Embedding

```env
EMBEDDING_API_TYPE=openai
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_API_KEY=replace-with-token
```

## 数据位置

Compose 第一版默认只持久化本项目数据目录：

```text
./data:/app/data
```

SQLite session 默认写入：

```text
/app/data/sessions.sqlite3
```

不要删除宿主机 `./data`，否则本地 session 历史会丢失。

## 和当前高级配置的关系

酒馆式字段是一层更简单的配置外观，后续实现时会映射到当前已有配置：

- `LLM_*` 映射到现有 model provider registry 或单 provider 配置。
- `EMBEDDING_*` 映射到现有 embedding provider 配置。
- `RAG_*` 映射到现有 RAG provider 配置。
- session 默认映射到 SQLite。

高级字段仍保留，用于本地开发、复杂 provider registry、多模型 alias 和特殊调试。Compose 使用文档只讲最小使用方式，不承载实现细节。
