# 全量 .env 编辑器使用与设计说明

## 定位

全量 `.env` 编辑器是受信任管理 UI，用于本地开发、联调和受控后台环境。它不是普通用户聊天页面，也不是让前端直接选择真实 provider 的入口。

它解决的问题不是“把 `.env` 文件搬到网页里编辑”，而是让配置有 schema、类型、依赖关系、字段 check、secret 处理和保存前预览。

当前 `GET /v1/runtime-config` 和 `PATCH /v1/runtime-config` 只适合非敏感热更新配置。全量 `.env` 编辑器需要独立 API：

- `GET /v1/env-config/schema`
- `GET /v1/env-config`
- `POST /v1/env-config/check`
- `PATCH /v1/env-config`

当前仓库已提供最小受信任页面：

```text
http://127.0.0.1:8000/config
```

当前不新增配置 profile CRUD API。面板里的“创建”指创建一份待提交的 `.env` 配置草稿；如果后续需要保存多套命名配置方案，应单独设计服务端 profile 存储。

## 使用边界

- 必须携带 `ROLEPLAY_API_KEY` 对应的 `Authorization: Bearer <key>` 或 `X-API-Key`。
- 可以编辑 `.env` 中的普通字段、restart-required 字段和 secret 字段。
- `DATABASE_URL`、`REDIS_URL`、`OPENAI_API_KEY`、`DEEPSEEK_API_KEY`、`GEMINI_API_KEY` 等 secret 可以设置新值，但接口响应和 UI 保存后只能显示状态，不回显原文。
- `ROLEPLAY_HOST`、`ROLEPLAY_PORT`、`SESSION_PROVIDER`、`SESSION_SQLITE_PATH`、`SESSION_POSTGRES_SCHEMA` 等启动级或有状态配置可以写入 `.env`，但必须提示需要重启服务后生效。
- 普通聊天前端不展示该面板入口。
- 不把 `.env` 原文完整返回给浏览器。
- 不在浏览器 localStorage 保存 API key、secret 或连接串。

## 页面结构

推荐页面分为三块：

1. 顶部环境栏：显示 API base URL、config source、是否支持写回、是否有未保存草稿、最后一次 check 结果。
2. 左侧分组导航：默认展示 HTTP、Storage、Simple LLM、Simple RAG、Simple Embedding；Advanced 入口默认折叠专家字段。
3. 右侧配置表单：按 schema 展示控件，支持创建字段、修改字段、清空字段和保存前 preview。

Simple 不是一套会覆盖用户配置的 profile。它只是按当前 API type 隐藏无关输入：fake 不要求 base URL 和 token，Ollama 不要求 token，OpenAI、DeepSeek、Gemini 显示各自需要的 base URL、model 和 token，Qdrant 显示 RAG endpoint、index 和 token。展开 Advanced 后，原有 registry、兼容字段和底层 provider 参数仍可编辑。

## 字段分组

| 分组            | 字段                                                                                                              | 说明                                             |
| --------------- | ----------------------------------------------------------------------------------------------------------------- | ------------------------------------------------ |
| HTTP            | `ROLEPLAY_HOST`、`ROLEPLAY_PORT`、`ROLEPLAY_API_KEY`                                                              | 服务监听和管理鉴权                               |
| Storage         | `ACCESS_TOKEN_SQLITE_PATH`、`SESSION_PROVIDER`、`SESSION_SQLITE_PATH`、`MEMORY_PROVIDER`、`MEMORY_SQLITE_PATH`     | 默认 SQLite 路径和本地持久化                     |
| Simple LLM      | `LLM_API_TYPE`、`LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`                                                        | 单模型最小接入面                                 |
| Simple RAG      | `RAG_API_TYPE`、`RAG_BASE_URL`、`RAG_INDEX`、`RAG_API_KEY`                                                        | local、vector store 或云端 RAG 最小接入面        |
| Simple Embedding | `EMBEDDING_API_TYPE`、`EMBEDDING_BASE_URL`、`EMBEDDING_MODEL`、`EMBEDDING_API_KEY`、`EMBEDDING_DIMENSIONS`        | embedding 最小接入面                             |
| Model           | `MODEL_PROVIDER`、`MODEL_NAME`、`MODEL_ALIAS`、`MODEL_TIMEOUT_MS`                                                 | fake/local/cloud model 调试                      |
| Model Registry  | `MODEL_PROVIDER_REGISTRY`                                                                                         | 高级 JSON 编辑，默认折叠，必须做 JSON 校验       |
| RAG             | `RAG_PROVIDER`、`RAG_CHUNK_SIZE`、`RAG_VECTOR_BACKEND`、`CHROMA_COLLECTION`、`QDRANT_COLLECTION`                  | RAG provider 和 collection 配置                  |
| Embedding       | `EMBEDDING_PROVIDER`、`EMBEDDING_MODEL`、`EMBEDDING_DIMENSIONS`、`EMBEDDING_TIMEOUT_MS`                           | embedding provider 配置                          |
| Agent           | `AGENT_CONTEXT_PLANNER`                                                                                           | `deterministic` 可用；`model` 只显示预留状态     |
| Backend Context | `BACKEND_CONTEXT_PROVIDER`、`BACKEND_CONTEXT_SOURCES`                                                             | 只用于受控调试                                   |
| Session         | `SESSION_PROVIDER`、`SESSION_RECENT_LIMIT`、`SESSION_SQLITE_PATH`、`SESSION_POSTGRES_SCHEMA`、`DATABASE_URL` 状态 | session store 和 recent limit                    |
| Memory          | `MEMORY_PROVIDER`、`MEMORY_SQLITE_PATH`、`MEMORY_SQLITE_BUSY_TIMEOUT_MS`                                         | 长期 memory store                                |
| Secrets         | `*_API_KEY`、`DATABASE_URL`、`REDIS_URL`                                                                          | 只显示 set/empty/missing，允许 set/replace/clear |
| Diff / Check    | 草稿 diff 和校验结果                                                                                              | 保存前确认                                       |

## 控件规则

- provider 类型使用 select 或 segmented control。
- boolean 使用 switch。
- 数字使用 number input，并显示推荐范围。
- JSON 配置使用 textarea 或 code editor，并在提交前解析校验。
- restart-required 字段可以编辑，但必须显示“保存后需要重启”。
- secret 字段使用 write-only input，保存后清空输入框，只显示状态。
- 字段旁边提供 check 按钮，能在保存前检查当前值。

## 字段 check

字段级 check 至少覆盖：

- key 是否是已知配置项。
- value 是否符合字段类型：string、int、float、bool、enum、json、url、path、csv。
- 数字是否在合理范围内，例如 timeout、dimensions、top_k。
- enum 是否是当前支持值。
- JSON 是否能解析，并符合最小结构要求。
- URL 是否是合法 URL。
- path 是否是相对路径或明确允许的本地路径。
- PostgreSQL schema、table prefix 等 identifier 是否安全。
- secret 字段是否不会被响应回显。

整体验证至少覆盖：

- provider 依赖字段是否完整。
- secret 是否已设置或由 `*_API_KEY_ENV` 指向。
- restart-required 字段变更是否正确提示。
- `MODEL_PROVIDER_REGISTRY` alias 是否能解析到 provider。
- RAG provider 和 embedding dimensions 是否一致。
- 当前未实现能力是否标记为风险，例如 `AGENT_CONTEXT_PLANNER=model`。

## 提交流程

1. 页面加载时调用 `GET /v1/env-config/schema` 和 `GET /v1/env-config`。
2. 根据 schema 生成表单，secret 字段只显示状态。
3. 用户修改后生成 `.env` 草稿。
4. 单字段可调用 `POST /v1/env-config/check` 做即时 check。
5. 保存前对整份候选配置调用 `POST /v1/env-config/check`。
6. check 通过后调用 `PATCH /v1/env-config`。
7. 服务端写回 `.env`，返回 redacted snapshot、hot reload 结果和 restart-required 提示。
8. 失败时展示 `error.code`、`error.message` 和字段级错误，不覆盖本地草稿。

## 当前实现状态

- 已实现 `/config` 零构建页面。
- 已实现 Simple/Advanced 视图；默认页面只显示 HTTP、Storage、LLM、RAG 和 Embedding 的最小字段。
- 已实现 fake、Ollama、OpenAI、DeepSeek、Gemini 和 Qdrant 字段矩阵，API type 变化时自动隐藏无关输入。
- 已保留 registry 和旧 provider 字段，展开 Advanced 后可继续编辑。
- Simple 配置默认使用 `.data/sessions.sqlite3` 和 `.data/memories.sqlite3`；显式 storage 配置优先。
- 已实现 schema、redacted snapshot、单字段 check、整份草稿 check 和 PATCH 写回。
- 已实现 secret write-only：保存后只显示 `set`、`empty` 或 `missing`。
- 已实现 `.env` 注释和未知 key 保留；未知 key 只展示 key 和状态，不允许通过 UI 修改。
- 已实现保存后的 hot reload 结果提示；`ROLEPLAY_HOST`、`ROLEPLAY_PORT`、`SESSION_PROVIDER`、数据库路径、PostgreSQL schema 等 restart-required 字段仍需要重启。
- 未实现命名 profile CRUD、真实云服务连通性 smoke、用户权限系统和多租户后台。

## 验收标准

- 可以查看完整 `.env` 配置摘要。
- 可以创建、修改、清空和删除已知配置字段。
- 可以检查单字段和整份候选配置。
- 可以保存 secret，但不会回显 secret 原文。
- 可以区分 hot reload、restart required 和 unsupported。
- 后端校验失败时，用户能看到明确错误。
- `.env` 编辑器与普通聊天 demo 分离。
