# Devlog

## 2026-07-01

### 完成

- 初始化 Python 本地开发环境。
- 使用 `uv` 管理 Python 版本、锁文件和虚拟环境。
- 新增 `pyproject.toml`、`.python-version`、`uv.lock`。
- 根目录 `README.md` 保持极简，只说明项目目的和前端文档入口。
- `.gitignore` 忽略 `docs/agent-dev/`、`.venv/`、`.uv-cache/`、`.uv-python/`。
- 补齐公开文档结构：
  - `docs/roadmap.md`
  - `docs/architecture.md`
  - `docs/api-contract.md`
  - `docs/devlog.md`

### 验证

- `uv lock` 成功。
- `uv sync` 成功。
- `uv run python --version` 输出 Python 3.12.13。
- `git check-ignore` 确认 `docs/agent-dev/` 被忽略。

### 下一步

- 从 Chat DTO 契约开始实现最小 API 骨架。
- 优先完成 `GET /v1/personas` 和 FakeModel 版 `POST /v1/chat`。

## 2026-07-01：Persona Catalog Schema

### 完成

- 添加了 `CharacterProfile`、`PersonaPreset`、`ToneConfig`、`KnowledgeBoundary`。
- 添加了本地 JSON persona 示例配置，覆盖 `haruhi` 和 `kyon`。
- 增加了 draft preset 过滤辅助函数。
- 补充 `docs/character-schema.md`，说明角色、preset、tone、knowledge boundary 和 policy 字段含义。

### 验证

- `uv run python -m unittest discover -s tests` 通过。
- `$env:PYTHONPYCACHEPREFIX='.uv-cache\compile-pycache'; uv run python -m compileall -q src tests` 通过。

### 下一步

- 实现 `GET /v1/personas`，读取公开角色和 preset catalog。

## 2026-07-01：Personas Catalog API

### 完成

- 添加 `PersonaRepository` port。
- 添加本地 JSON persona repository。
- 添加 `ListPublicPersonas` use case。
- 添加框架无关的 `get_personas` API handler。
- 返回公开角色和公开 preset，过滤 `draft` / `private` preset。

### 验证

- `uv run python -m unittest discover -s tests` 通过。
- `uv run python -m compileall -q src tests` 通过。

### 下一步

- 实现 PromptBuilder v1，为 `POST /v1/chat` 准备 prompt 输入。

## 2026-07-01：PromptBuilder v1

### 完成

- 添加 `PromptBuildInput`、`PromptBuildOutput` 和 `PromptMessage`。
- 添加 `PromptBuilder` port。
- 添加默认 `PersonaPromptBuilder`。
- 组装基础安全边界、角色设定、时间线知识边界、输出规则和当前用户消息。
- 保持 RAG、memory、session 不参与 v1 prompt 构建。

### 验证

- `uv run python -m unittest discover -s tests` 通过。
- `$env:PYTHONPYCACHEPREFIX='.uv-cache\compile-pycache'; uv run python -m compileall -q src tests` 通过。

### 下一步

- 实现 FakeModelProvider，让 PromptBuilder 输出可以进入最小 chat 流程。

## 2026-07-01：Layered Architecture Docs

### 完成

- 添加 `docs/layered-architecture.md`。
- 说明 `domain`、`application`、`ports`、`adapters`、`api`、`infrastructure` 的含义。
- 补充开发新功能时的推荐落层顺序和测试方式。
- 在 `docs/README.md` 和 `docs/architecture.md` 中加入入口。

### 验证

- `rg -n "layered-architecture|Layered Architecture|domain|application|ports|adapters|infrastructure|如何加入开发|判断代码应该放哪一层" docs\README.md docs\architecture.md docs\layered-architecture.md docs\devlog.md` 通过。
- `uv run python -m unittest discover -s tests` 通过。
- `$env:PYTHONPYCACHEPREFIX='.uv-cache\compile-pycache'; uv run python -m compileall -q src tests` 通过。

### 下一步

- 继续实现 FakeModelProvider。

## 2026-07-02：FakeModelProvider

### 完成

- 添加 `ModelMessage`、`ModelRequest`、`ModelResponse` 和 `ModelUsage`。
- 添加 `ChatModelProvider` port。
- 添加 `FakeModelProvider`。
- 添加最小 `ModelRouter`，支持 fake provider 和模型别名选择。
- 支持 fake usage 统计和 debug trace 中的 `modelProvider=fake`。

### 验证

- `uv run python -m unittest discover -s tests` 通过。
- `$env:PYTHONPYCACHEPREFIX='.uv-cache\compile-pycache'; uv run python -m compileall -q src tests` 通过。

### 下一步

- 实现最小 `POST /v1/chat`，串联 ChatInput、PersonaRepository、PromptBuilder、ModelRouter 和 FakeModelProvider。

## 2026-07-02：Chat API v1

### 完成

- 添加 `SendChatMessageUseCase`。
- 添加最小 `RoleplayOrchestrator`。
- 添加框架无关的 `post_chat` API handler。
- 支持 `snake_case` API body 到内部 `camelCase` DTO 的映射。
- 串联 PersonaRepository、PromptBuilder、ModelRouter 和 FakeModelProvider。
- 非法角色和非法 preset 会返回统一错误响应。

### 验证

- `uv run python -m unittest discover -s tests` 通过。
- `$env:PYTHONPYCACHEPREFIX='.uv-cache\compile-pycache'; uv run python -m compileall -q src tests` 通过。

### 下一步

- 实现 Local Model Provider，在不改 Orchestrator 的前提下替换 FakeModelProvider。

## 2026-07-02：Local Model Provider

### 完成

- 添加 OpenAI-compatible 本地模型 provider。
- 添加模型 provider 配置和 `build_model_router` 工厂。
- 支持通过 `MODEL_PROVIDER=fake|local|openai_compatible` 切换模型实现。
- 支持 `MODEL_BASE_URL`、`MODEL_NAME`、`MODEL_TIMEOUT_MS` 和可选 `MODEL_API_KEY`。
- 将本地 provider 请求失败和响应格式错误转换为统一 `AppError`。

### 验证

- `uv run python -m unittest discover -s tests` 通过。
- `$env:PYTHONPYCACHEPREFIX='.uv-cache\compile-pycache'; uv run python -m compileall -q src tests` 通过。

### 下一步

- 添加最小运行入口或 provider pack wiring，让本地启动时自动装配 persona、prompt 和 model provider。

## 2026-07-02：Continuous Session v1

### 完成

- 添加 `Session` 和 `SessionMessage`。
- 添加 `SessionStore` port。
- 添加 `InMemorySessionStore`。
- 添加框架无关的 `post_session` API handler。
- Chat 开启 `continuous_session=true` 时读取最近消息，并在回复后写入 user / assistant 消息。
- PromptBuilder 接收 Orchestrator 提供的 recent messages。

### 验证

- `uv run python -m unittest discover -s tests` 通过。
- `$env:PYTHONPYCACHEPREFIX='.uv-cache\compile-pycache'; uv run python -m compileall -q src tests` 通过。

### 下一步

- 实现 `03.03 Debug Trace v1`，记录请求阶段、provider、capability 开关和耗时摘要。

## 2026-07-02：Debug Trace v1

### 完成

- 添加 `DebugTrace` 领域结构。
- Chat Orchestrator 返回安全裁剪后的 debug 摘要。
- 支持服务端通过 `debug_trace_enabled=false` 禁用 debug 返回。
- debug 显示 persona、model、capability、session 读取数量、请求阶段和耗时。
- 裁剪 provider debug 中的 prompt、secret、连接串等敏感字段。
- 错误路径记录带 `request_id` 和错误码的安全日志。

### 验证

- `uv run python -m unittest discover -s tests` 通过。
- `$env:PYTHONPYCACHEPREFIX='.uv-cache\compile-pycache'; uv run python -m compileall -q src tests` 通过。

### 下一步

- 实现 `04.01 RAG Metadata Validation`，先定义 RAG 文档 metadata 的最小校验边界。

## 2026-07-02：RAG Metadata Validation

### 完成

- 添加 `RagDocumentMetadata`、`RagIngestInput` 和 `RagIngestResult`。
- 添加 `ValidateRagDocumentMetadata` 用例，校验 RAG metadata 不越过 persona policy。
- 添加框架无关的 `post_rag_document` API handler。
- 支持校验 `characterId`、`timeline`、`spoilerLevel`、`language`、`sourceType`。
- 当前只返回 `validated`，不切 chunk、不写 vector index、不调用 embedding。

### 验证

- `uv run python -m unittest discover -s tests` 通过。
- `$env:PYTHONPYCACHEPREFIX='.uv-cache\compile-pycache'; uv run python -m compileall -q src tests` 通过。

### 下一步

- 实现 `04.02 Fake RAG Retrieve`，用固定 chunks 验证 RAG 开关、filter 和 PromptBuilder 融合。

## 2026-07-02：Fake RAG Retrieve

### 完成

- 添加 `RagService` port。
- 添加 `RagRetrieveInput`、`RagRetrieveFilters`、`RagChunk` 和 `RagRetrieveOutput`。
- 添加 `FakeRagService`，用固定 chunks 验证 metadata filter。
- Chat Orchestrator 在 `rag=true` 时调用 RagService，并把 chunks 交给 PromptBuilder。
- PromptBuilder 支持插入 RAG chunk 摘要段。
- ChatOutput 返回 RAG provider、hit count 和 source 摘要。

### 验证

- `uv run python -m unittest discover -s tests` 通过。
- `$env:PYTHONPYCACHEPREFIX='.uv-cache\compile-pycache'; uv run python -m compileall -q src tests` 通过。

### 下一步

- 实现 `04.03 Local RAG v1`，在本地 provider 中接入真实文档、chunk 和检索。

## 2026-07-02：Local RAG v1

### 完成

- 添加 `RagIngestService` port。
- 添加 `LocalRagService`，支持本地文档导入、文本 chunk 和简单检索。
- `POST /v1/rag/documents` 支持注入本地 ingest provider 后写入 chunks。
- Chat RAG 分支可直接使用 `LocalRagService` 返回 source 摘要。
- 本地检索按 character、timeline、spoilerLevel、language 和 sourceType 过滤。

### 验证

- `uv run python -m unittest discover -s tests` 通过。
- `$env:PYTHONPYCACHEPREFIX='.uv-cache\compile-pycache'; uv run python -m compileall -q src tests` 通过。

### 下一步

- 进入 Memory 模块，继续实现 `05.01 Memory CRUD`。

## 2026-07-02：Memory CRUD

### 完成

- 添加 `MemoryItem`、`MemoryType`、`MemoryQuery` 和 `MemoryDeleteCommand`。
- 添加 `MemoryStore` port。
- 添加 `InMemoryMemoryStore`，支持按 app、user、character、persona 精确隔离查询。
- 添加框架无关的 `GET /v1/memory/{user_id}` 和 `DELETE /v1/memory/{user_id}/{memory_id}` handler。
- 删除不存在或上下文不匹配的记忆时返回 `MEMORY_NOT_FOUND`，避免泄漏其它上下文。
- 当前只做手动查询和删除，不接入 `/v1/chat`，也不做自动写入。

### 验证

- `uv run python -m unittest discover -s tests` 通过。

### 下一步

- 实现 `05.02 Memory Read Policy`，在 chat 编排中按策略读取有限记忆。

## 2026-07-02：Memory Read Policy

### 完成

- 添加 `MemoryReadPolicyInput`。
- 添加 `MemoryPolicyEngine` port 和 `DefaultMemoryPolicyEngine`。
- Chat 在 `capabilities.memory=true` 时通过 MemoryStore 读取有限记忆。
- Memory 查询按 app、user、character、persona、persona allowedTypes 和服务端 limit 过滤。
- PromptBuilder 增加“长期记忆摘要”段，包含 type、confidence 和 content。
- ChatOutput 返回 `memory.enabled` 和 `memory.read_count`。
- Debug trace 返回 `memoryEnabled` 和 `memoryReadCount`。
- 当前仍不自动写入新记忆。

### 验证

- `uv run python -m unittest discover -s tests` 通过。

### 下一步

- 实现 `05.03 Memory Write Policy`，为自动写入记忆增加明确策略和测试。

## 2026-07-02：Memory Write Policy

### 完成

- 添加 `MemoryWriteCandidate`、`MemoryWritePolicyInput` 和 `MemoryWriteCommand`。
- `MemoryStore` 增加 `add_memory`。
- `InMemoryMemoryStore` 支持写入 policy-approved memory，并保存 reason。
- `DefaultMemoryPolicyEngine` 增加 `should_write`。
- Chat 在模型回复完成后读取 `metadata.memory_write` 显式候选，经过策略后写入。
- ChatOutput 返回 `memory.write_count`。
- Debug trace 返回 `memoryWriteCount`。
- 默认策略拒绝临时闲聊、敏感信息、低置信度和 persona 不允许的类型。

### 验证

- `uv run python -m unittest discover -s tests` 通过。

### 下一步

- 进入 `06.01 Stream Chat` 或先补充更完整的 memory 持久化 adapter。

## 2026-07-02：Stream Chat

### 完成

- 添加 `ModelStreamEvent` 和 `ChatStreamEvent`。
- `ChatModelProvider` 和 `ModelRouter` 增加 `stream` 契约。
- `FakeModelProvider` 支持确定性 delta 输出。
- `LocalOpenAICompatibleModelProvider` 支持最小 OpenAI-compatible SSE delta 解析。
- 添加 `POST /v1/chat/stream` 框架无关 handler，返回 `data.events`。
- 流式 Chat 复用同一 Orchestrator 前置编排，不改变 session、RAG、memory 语义。
- 正常流式结束后写入完整 assistant message，中途 provider 失败时返回 `error` event。

### 验证

- `uv run python -m unittest tests.test_stream_chat tests.test_local_model_provider tests.test_debug_trace_v1` 通过。

### 下一步

- 进入 `06.02 Cloud Provider Pack`，或先补真实 HTTP/SSE adapter。

## 2026-07-03：产品化路线重审

### 完成

- 重新确认项目定位：面向前端和业务后端的凉宫春日 Roleplay API 中转服务。
- 明确 HTTP 运行层、模型/RAG provider、Agent 编排和前端 demo 都合理，但必须拆阶段实现。
- 更新 roadmap、architecture、design spec 和 backend dispatch 文档。
- 新增 HTTP runtime、provider registry、DeepSeek、OpenAI、Cloud RAG、Agent context、Backend context、Frontend demo 实现卡片。

### 验证

- 本次只修改文档，使用 `rg` 检查关键章节和卡片索引。

### 下一步

- 优先实现 `06.03 HTTP Runtime Adapter`，让当前 framework-agnostic handler 通过真实 HTTP/SSE 暴露。

## 2026-07-03：HTTP Runtime Adapter

### 完成

- 添加标准库 HTTP runtime 和本地 server 入口。
- 暴露 `GET /health`、`GET /v1/personas`、`POST /v1/sessions`、`POST /v1/chat`、`POST /v1/chat/stream`、`POST /v1/rag/documents`、memory 查询和删除接口。
- `POST /v1/chat/stream` 将框架无关 stream events 编码为 SSE。
- 本地 runtime 共享 Session、Memory 和 Local RAG 实例，便于前端和 curl 进行端到端验证。
- 支持可选 `ROLEPLAY_API_KEY`，允许使用 `Authorization: Bearer ...` 或 `X-API-Key`。
- 补充本地启动命令和 curl 示例。

### 验证

- 新增 HTTP runtime adapter 单元测试，覆盖 personas、chat、SSE、RAG 共享状态、API key 和 404。
- 本地 smoke test 通过标准库 HTTP server 调用 health、personas、chat 和 stream。

### 下一步

- 进入 provider registry / cloud provider pack，逐步接入 DeepSeek、OpenAI-compatible 和云端 RAG。

## 2026-07-03：Model Provider Registry

### 完成

- 添加模型 provider registry router，支持 `generation.model` 作为服务端白名单 alias。
- 支持 alias 映射到具体 provider 和 provider 侧真实模型名。
- 保留旧的 `MODEL_PROVIDER`、`MODEL_BASE_URL`、`MODEL_NAME` 单 provider 配置。
- 新增 `MODEL_PROVIDER_REGISTRY` JSON 配置，支持 `fake`、`local_openai_compatible`、`openai_compatible` 和 `ollama` provider type。
- Ollama 通过 OpenAI-compatible `/v1/chat/completions` 接口接入。
- API usage 和 debug trace 返回模型 alias，不要求前端知道真实 provider/model。

### 验证

- `uv run python -m unittest tests.test_model_provider_registry tests.test_local_model_provider` 通过。
- `uv run python -m unittest discover -s tests` 通过。
- `$env:PYTHONPYCACHEPREFIX='.uv-cache\compile-pycache'; uv run python -m compileall -q src tests` 通过。
- 本地 HTTP 服务使用 `haruhi-ollama -> qwen2.5:7b` registry 调用 Ollama 成功，返回完整中文回复。

### 下一步

- 继续实现 DeepSeek provider 配置模板，或补 provider registry 的生产环境配置校验。

## 2026-07-03：DeepSeek / Gemini Provider

### 完成

- 在 provider registry 中新增 `deepseek` provider type。
- 在 provider registry 中新增 `gemini` provider type。
- 拆分模型 provider 结构：`application/models.py` 保留 `ModelProviderRegistryRouter`，`ports/models.py` 保留模型 port，具体 provider 移入 `adapters/models/`。
- 新增 `infrastructure/model_registry.py` 解析 `MODEL_PROVIDER_REGISTRY`，新增 `infrastructure/model_provider_factory.py` 注册 provider factory。
- 保留 `infrastructure/models.py` 作为兼容导出，避免旧 import 立即断裂。
- DeepSeek 默认使用 OpenAI-compatible `https://api.deepseek.com/chat/completions`。
- Gemini 默认使用 OpenAI-compatible `https://generativelanguage.googleapis.com/v1beta/openai/chat/completions`。
- 支持从 `DEEPSEEK_API_KEY` 和 `GEMINI_API_KEY` 读取 secret，也支持 registry 中配置 `api_key_env`。
- 云端 provider 缺少 API key 时启动装配阶段直接返回统一 `MODEL_PROVIDER_ERROR`。
- provider HTTP error 映射为 `MODEL_PROVIDER_ERROR`，超时映射为 `MODEL_TIMEOUT`。
- provider debug 只保留 provider 名称和模型 alias，不泄露 secret。

### 验证

- `uv run python -m unittest tests.test_cloud_model_providers` 通过。
- `uv run python -m unittest tests.test_model_provider_registry tests.test_local_model_provider` 通过。
- `uv run python -m unittest tests.test_model_provider_registry tests.test_local_model_provider tests.test_fake_model_provider tests.test_chat_api_v1 tests.test_debug_trace_v1 tests.test_cloud_model_providers` 通过。
- `uv run python -m unittest discover -s tests` 通过。
- `$env:PYTHONPYCACHEPREFIX='.uv-cache\compile-pycache'; uv run python -m compileall -q src tests` 通过。

### 下一步

- 继续实现 `07.03.openai-provider.md`。

## 2026-07-04：OpenAI Provider

### 完成

- 新增 OpenAI 官方 provider preset，复用 OpenAI-compatible chat completions 传输实现。
- 支持 `MODEL_PROVIDER_REGISTRY` 中配置 `"type": "openai"`。
- OpenAI 默认使用 `https://api.openai.com/v1/chat/completions`。
- OpenAI 默认从 `OPENAI_API_KEY` 读取 secret，也支持 registry 中配置 `api_key_env`。
- 旧兼容配置 `MODEL_PROVIDER=openai` 会使用 `openai` 作为 provider id。
- debug trace 只返回 provider 名称和模型 alias，不暴露 secret。

### 验证

- `uv run python -m unittest tests.test_cloud_model_providers` 通过。
- `uv run python -m unittest tests.test_model_provider_registry tests.test_local_model_provider` 通过。
- `uv run python -m unittest discover -s tests` 通过。
- `$env:PYTHONPYCACHEPREFIX='.uv-cache\compile-pycache'; uv run python -m compileall -q src tests` 通过。

### 下一步

- 继续实现 `07.04.cloud-rag-provider.md`。

## 2026-07-04：Cloud / Vector RAG Provider

### 完成

- 新增 `LocalVectorRagService`，使用标准库 hash embedding + 内存向量索引跑通本地向量 RAG。
- 预留可选 Chroma/Faiss backend；本地安装 `chromadb` 或 `faiss-cpu` 后可通过 `RAG_PROVIDER=chroma|faiss` 切换。
- 新增 `QdrantRagService`，通过 Qdrant REST upsert/search 接入云端向量库。
- 新增 `RagProviderSettings` 和 `build_rag_service`，通过 `RAG_PROVIDER`、`QDRANT_URL` 等环境变量装配 RAG provider。
- HTTP runtime 改为通过 RAG provider factory 装配，并新增 `POST /v1/rag/search` 调试检索入口。
- RAG 输出继续统一为 `RagRetrieveOutput`，source 摘要保持可追溯。

### 验证

- `uv run python -m unittest tests.test_local_vector_rag_provider tests.test_qdrant_rag_provider tests.test_http_runtime_adapter` 通过。
- `uv run python -m unittest tests.test_local_rag_v1 tests.test_rag_metadata_validation tests.test_fake_rag_retrieve` 通过。
- `uv run python -m unittest discover -s tests` 通过。
- `$env:PYTHONPYCACHEPREFIX='.uv-cache\compile-pycache'; uv run python -m compileall -q src tests` 通过。

### 下一步

- 继续实现 `07.05.embedding-provider.md`。

## 2026-07-04：Embedding Provider

### 完成

- 新增 `TextEmbeddingProvider` port，RAG 不再直接依赖具体 embedding 实现。
- 新增 hash、本地 OpenAI-compatible、Ollama 和 OpenAI embedding adapter。
- 新增 `EmbeddingProviderSettings` 和 `build_embedding_provider`，支持 `EMBEDDING_PROVIDER=hash|local_openai_compatible|ollama|openai`。
- `LocalVectorRagService` 和 `QdrantRagService` 改为接收 `TextEmbeddingProvider`。
- `RagProviderSettings` 通过 embedding provider factory 注入向量生成能力。
- 云端 OpenAI embedding 默认使用 `OPENAI_API_KEY`，本地 Ollama 默认使用 `http://localhost:11434/v1/embeddings`。

### 验证

- `uv run python -m unittest tests.test_embedding_providers` 通过。
- `uv run python -m unittest tests.test_local_vector_rag_provider tests.test_qdrant_rag_provider tests.test_http_runtime_adapter` 通过。
- `uv run python -m unittest discover -s tests` 通过。
- `$env:PYTHONPYCACHEPREFIX='.uv-cache\compile-pycache'; uv run python -m compileall -q src tests` 通过。

### 下一步

- 继续实现 `08.01.agent-context-plan.md`。

## 2026-07-05：Ollama + Chroma 手动 Smoke 入口

### 完成

- 新增 `scripts/local_ollama_chroma_smoke.py`，用于手动验证本机 Ollama + Chroma 完整链路。
- smoke 入口会检查 `chromadb`、Ollama tags、chat 模型和 embedding 模型。
- smoke 入口通过 `RoleplayHttpRuntime` 顺序调用 health、personas、RAG ingest、RAG search 和 chat。
- 文档补充 `uv run --with chromadb python scripts/local_ollama_chroma_smoke.py` 运行方式。

### 验证

- `uv run --with chromadb python scripts/local_ollama_chroma_smoke.py` 通过，确认 Ollama chat、Ollama embedding、Chroma 检索和 RAG chat 回复完整跑通。

### 下一步

- 继续实现 `08.01.agent-context-plan.md`。

## 2026-07-05：`.env` Runtime Config 热切换

### 完成

- 新增 `.env` runtime config store，HTTP server 默认读取项目根目录 `.env`，也支持 `ROLEPLAY_CONFIG_FILE` 指定路径。
- 新增 `.env.example` 本地模板，保留 fake model + local RAG 的安全默认配置，并给出 Ollama / Chroma 注释示例。
- 新增 `GET /v1/runtime-config`，返回当前非敏感配置摘要。
- 新增 `PATCH /v1/runtime-config`，允许受信任管理前端热更新白名单内后端配置。
- 热更新会先用候选配置重建 model router 和 RAG service，成功后才写回 `.env`。
- 配置接口要求 `ROLEPLAY_API_KEY`，并拒绝 `API_KEY`、`TOKEN`、`SECRET` 等敏感 key。
- 更新接口文档、前端接入说明和后端调度配置说明。

### 验证

- `uv run python -m unittest tests.test_http_runtime_adapter` 通过。

### 下一步

- 继续实现 `08.01.agent-context-plan.md`。

## 2026-07-05：Agent Context Plan

### 完成

- 新增 `ContextPlan` domain 对象，用于描述本次 chat 是否读取 session、memory 和 RAG。
- 新增 `AgentContextPlanner` port。
- 新增 `DeterministicAgentContextPlanner`，默认通过 capability 和 persona policy 生成确定性 plan。
- 新增 `ModelBackedAgentContextPlanner` 占位实现，保留基于后端大模型的 planner 接口。
- 新增 `AGENT_CONTEXT_PLANNER` 配置入口，支持 `deterministic` 和预留的 `model`。
- Orchestrator 改为先生成 `ContextPlan`，再按 plan 读取 session、memory 和 RAG。
- Debug trace 增加 `contextPlan` 安全摘要，不返回用户原文、prompt、query、URL、SQL 或 secret。
- 更新架构、接口、前端接入和后端调度文档，写明 model-backed planner 未实现。

### 验证

- `uv run python -m unittest tests.test_agent_context_plan` 通过。
- `uv run python -m unittest tests.test_http_runtime_adapter` 通过。

### 下一步

- 继续实现 `08.02.backend-context-provider.md`，把业务后端上下文纳入受控 plan。

## 2026-07-05：Backend Context Provider

### 完成

- 新增 `BackendContextRequest` 和 `BackendContextFact` domain 对象。
- 新增 `BackendContextProvider` port。
- 新增 `FakeBackendContextProvider`，支持 `user_profile` 和 `game_state` 两类示例 source。
- `DeterministicAgentContextPlanner` 支持通过服务端配置生成 `backendFetches`。
- Orchestrator 按 `ContextPlan.backendFetches` 调用 backend context provider。
- PromptBuilder 增加“业务后端上下文摘要”段，把 backend facts 纳入模型输入。
- Debug trace 增加 `backendContextFactCount` 和 `backendContextSources`，不返回 fact 内容。
- HTTP runtime 支持通过 `BACKEND_CONTEXT_PROVIDER` 和 `BACKEND_CONTEXT_SOURCES` 装配 fake backend context。
- 更新架构、接口、前端接入、设计规范和后端调度文档。

### 验证

- `uv run python -m unittest tests.test_backend_context_provider` 通过。
- `uv run python -m unittest tests.test_agent_context_plan tests.test_http_runtime_adapter tests.test_debug_trace_v1 tests.test_prompt_builder_v1` 通过。

### 下一步

- 继续实现真实业务后端 adapter 或进入 `08.03.session-persistence-adapters.md`。

## 2026-07-05：Session Store Factory

### 完成

- 新增 `SessionStoreSettings` 和 `build_session_store_from_env`。
- HTTP runtime 改为通过 session store factory 装配 session store，默认仍使用 `InMemorySessionStore`。
- 新增 `SESSION_PROVIDER`、`SESSION_RECENT_LIMIT`、`SESSION_TTL_SECONDS` 等 `.env.example` 配置入口。
- `SESSION_RECENT_LIMIT` 已接入 chat 编排，可通过 runtime config 热更新。
- runtime config 新增 `restart_required_keys`，用于展示 `SESSION_PROVIDER`、`SESSION_SQLITE_PATH` 等需要重启后生效的配置。
- 当时记录 `postgres` session provider 尚待补齐；本分支后续已在 PostgreSQL Session Store 中实现。

### 验证

- `uv run python -m unittest tests.test_session_store_factory tests.test_http_runtime_adapter tests.test_continuous_session_v1` 通过。

### 下一步

- 后续已实现 `08.03.02 SQLite Session Store`，让本地 session 在服务重启后仍可读取。

## 2026-07-05：Session Recent Limit 文档澄清

### 完成

- 补充 `SESSION_RECENT_LIMIT` 的字段含义：只控制连续会话读取最近 session message 的数量。
- 明确它不限制 session 总保存数量，也不是 memory 读取数量或数据库分页参数。
- 补充说明当前不做 `memory.md` 式滚动摘要的原因：MVP 优先保留可审核、可回放的原始 recent messages。
- 记录未来可优化方向：单独增加 `SessionSummaryStore` 或 `SessionCompactor`，把旧消息压缩成 session summary。

### 验证

- 使用 `rg` 检查 `SESSION_RECENT_LIMIT`、`SessionSummaryStore`、`SessionCompactor` 和 `memory.md` 文档位置。

## 2026-07-05：SQLite Session Store

### 完成

- 新增 `SQLiteSessionStore`，使用标准库 `sqlite3` 实现本地 session 持久化。
- SQLite schema 包含 `sessions` 和 `session_messages`，支持 session 创建、读取、recent messages 和消息追加。
- `SESSION_PROVIDER=sqlite` 已接入 session store factory。
- `.gitignore` 新增 `.data/`，避免默认 SQLite 数据库文件误提交。
- `.env.example` 补充 SQLite session persistence 示例。
- HTTP runtime 可通过同一个 SQLite 文件跨 runtime 实例读取已有 session 历史。

### 验证

- `uv run python -m unittest tests.test_sqlite_session_store tests.test_session_store_factory tests.test_http_runtime_adapter tests.test_continuous_session_v1` 通过。

### 下一步

- 继续实现 `08.03.03 PostgreSQL Session Store`，为云端部署提供 session 持久化 adapter。

## 2026-07-05：PostgreSQL Session Store

### 完成

- 新增 `PostgresSessionStore`，通过可选 `psycopg` v3 支持云端 session 持久化。
- `SESSION_PROVIDER=postgres` 已接入 session store factory。
- PostgreSQL schema 包含 session 表、message 表和基础索引，支持自动建表和已有 schema 校验。
- 缺少 `DATABASE_URL` 会返回稳定配置错误；provider 异常会转换为 `SESSION_PROVIDER_ERROR`。
- `.env.example`、架构文档、接口文档和后端调度文档补充 PostgreSQL 配置说明。
- 明确 `DATABASE_URL` 不进入 runtime config public snapshot，也不能通过前端 PATCH 写入。

### 验证

- `uv run python -m unittest tests.test_postgres_session_store tests.test_session_store_factory` 通过。

### 下一步

- 继续验证完整测试集，并在后续卡片中考虑真实 PostgreSQL smoke 或连接池能力。

## 2026-07-05：全量 `.env` 编辑器规划

### 完成

- 新增 `09.02.env-config-editor.md` 实现卡片。
- 更新 `docs/usage/config-panel.md`，把配置面板重新定位为全量 `.env` 编辑器。
- 明确需要独立 Env Config Editor API，不能复用 runtime config PATCH 写全量 `.env`。
- 补充字段 check、整体验证、secret redaction、restart-required 提示和草稿 diff 规则。
- 更新 roadmap、前端接入、接口参考、后端调度和设计规范。

### 验证

- 使用 `rg` 检查 `env-config`、`.env 编辑器`、`字段 check`、`09.02` 文档位置。

### 下一步

- 后续实现时先完成普通聊天 demo，再按 `09.02` 单独实现全量 `.env` 编辑器。

## 2026-07-06：Frontend Demo

### 完成

- 新增 `frontend-demo/` 零构建静态页面，提供角色/preset 选择、消息发送、stream delta、source 和 debug 展示。
- HTTP runtime 新增 `/demo` 静态路由，方便通过同一个本地服务打开 demo。
- Demo 支持创建 session、切换 stream/RAG/memory/debug 能力，并提供最小 RAG 文档导入入口。
- Debug 面板默认折叠，普通聊天视图不直接展示调试 JSON。
- 普通聊天 demo 不包含 `.env` 编辑器，继续由 `09.02` 单独规划。

### 验证

- `uv run python -m unittest tests.test_http_runtime_adapter` 通过。
- `uv run python -m unittest discover -s tests` 通过。
- `$env:PYTHONPYCACHEPREFIX='.uv-cache\compile-pycache'; uv run python -m compileall -q src tests` 通过。
- `git diff --check` 通过，仅有 Windows CRLF 转换提示。
- HTTP smoke 通过：`/demo`、`/v1/personas`、`/v1/chat/stream` 均返回 200。
- 浏览器 smoke 通过：demo 读取角色、发送 stream 消息、导入 RAG 文档并展示 source。

### 下一步

- 继续按 `09.02` 实现受信任的全量 `.env` 配置编辑器。

## 2026-07-06：Env Config Editor

### 完成

- 新增 `EnvConfigEditor`，提供 `.env` 字段 schema、redacted snapshot、单字段 check、整份候选配置 check 和写回能力。
- 新增 `GET /v1/env-config/schema`、`GET /v1/env-config`、`POST /v1/env-config/check`、`PATCH /v1/env-config`。
- 新增 `/config` 零构建受信任配置页面，按 HTTP、Model、RAG、Embedding、Agent、Backend Context、Session、Secrets 等分组渲染字段。
- 支持 secret write-only 输入；响应和 UI 只显示 `set`、`empty`、`missing`，不回显原文。
- `.env` 写回会保留注释和未知 key；已知字段可新增、修改、清空或移除。
- 保存后返回 hot reload 结果和 restart-required 提示；有状态 session store 配置仍需要重启后完整生效。

### 验证

- `uv run python -m unittest tests.test_env_config_editor` 通过。
- `uv run python -m unittest tests.test_http_runtime_adapter` 通过。
- `uv run python -m unittest discover -s tests` 通过。
- `$env:PYTHONPYCACHEPREFIX='.uv-cache\compile-pycache'; uv run python -m compileall -q src tests` 通过。
- `git diff --check` 通过，仅有 Windows CRLF 转换提示。
- HTTP smoke 通过：`/config`、`/v1/env-config/schema`、`/v1/env-config`、`/v1/env-config/check`、`PATCH /v1/env-config` 均按预期返回。
- 重启 smoke 通过：通过 Env Config API 写入临时 `.env` 后重启服务，新 model alias 仍可用于 chat。
- 浏览器只读 smoke 通过：`/config` 页面 title、Admin Key 输入框、Connect 按钮和配置容器存在。
- 浏览器交互 smoke 未完成：当前 in-app browser 虚拟剪贴板不可用，`fill()` / `type()` 无法向输入框写入。

### 下一步

- 后续可补浏览器环境可写输入后的完整 UI 交互 smoke。

## 2026-07-06：Backend Config Simplification Docs

### 完成

- 新增 `docs/usage/backend-config.md`，作为后端配置第一入口。
- 补充 fake local、Ollama local、云模型等最小配置示例。
- 说明 `.env`、runtime config API、Env Config Editor API 的职责边界。
- 分析当前配置复杂度来源，并提出 Simple/Advanced UI、字段收敛和 schema 拆分的化简路线。
- 在 `docs/README.md` 和后端调度长文档中加入入口链接。

### 验证

- 使用 `rg` 检查 `backend-config`、fake local、Ollama local 等文档入口和关键词。

### 下一步

- 若进入实现阶段，优先做 `/config` 的 Simple / Advanced 视图，再引入酒馆式 provider 字段映射。

## 2026-07-06：Frontend Calling And Backend Config Usage Docs

### 完成

- 新增 `docs/usage/frontend-api-calling.md`，集中说明前端调用 chat、stream、RAG、memory、demo 和 config 页面的方式。
- 补充 `docs/usage/backend-config.md` 的使用流程和当前已实现后端能力表。
- 更新 `docs/README.md` 推荐阅读顺序，把前端调用完整文档作为前端接入第一入口。
- 在 `docs/usage/frontend-integration.md` 增加入口提示，区分“调用手册”和“架构边界说明”。

### 验证

- 使用 `rg` 检查 `frontend-api-calling`、`POST /v1/chat/stream`、`使用方式总览`、`当前已实现后端能力` 等文档关键词。

### 下一步

- 后续如果继续化简配置，优先把 `/config` 做成 Simple / Advanced 两种视图，再实现酒馆式 provider 字段映射。

## 2026-07-06：HTTP Port Restart Config

### 完成

- 将 `ROLEPLAY_HOST` 和 `ROLEPLAY_PORT` 纳入 runtime config 的 `restart_required_keys`。
- 明确端口是启动级配置：可通过 `.env` / `/config` 修改，但需要重启服务后重新绑定 HTTP socket。
- 补充测试验证 `HttpRuntimeSettings` 会从环境变量和 `.env` 读取 host / port。
- 更新后端配置、配置面板、接口参考和后端调度文档中的 restart-required 说明。

### 验证

- `uv run python -m unittest tests.test_http_runtime_adapter tests.test_env_config_editor` 通过。

### 下一步

- 后续可在 `/config` UI 中把 restart-required 字段做成更明显的重启提示。

## 2026-07-06：Backend Config Field Dictionary

### 完成

- 扩充 `docs/usage/backend-config.md`，新增后端字段字典。
- 按 HTTP、Model、Model Registry、RAG、Embedding、Agent、Backend Context、Session、Secrets、Advanced 分块说明字段含义。
- 为每个配置块补充使用场景和 `.env` 示例。
- 标注 hot reload、restart required、secret、reserved 等状态，避免把预留字段误认为已完整可用。

### 验证

- 使用 `rg` 检查主要配置字段和分组标题均已写入 `docs/usage/backend-config.md`。

### 下一步

- 后续可把 `/config` UI 的字段说明直接对齐这份字段字典，减少配置页面和文档之间的理解偏差。

## 2026-07-07：Docker Compose And Tavern-Style Config Planning

### 完成

- 删除上一版过重的云端部署规划文档。
- 新增 `docs/usage/docker-compose.md`，只说明 Compose 使用方式。
- 新增 `docs/agent-dev/cards/10.01.docker-compose-wrapper.md`。
- 新增 `docs/agent-dev/cards/10.02.tavern-style-provider-config.md`。
- 新增 `docs/agent-dev/cards/10.03.compose-usage-docs.md`。
- 明确“预设”只表示 API type / provider 选择器，不表示一整套部署方案。
- 将配置收束为 LLM、Embedding、RAG 各自的 API type / provider、base URL、model 或 index、token。
- 在 `docs/README.md`、`docs/roadmap.md` 和 `docs/usage/backend-config.md` 更新入口。

### 验证

- 本次只修改文档，使用 `rg` 检查旧部署规划关键词和新 Compose / provider 配置入口。

### 下一步

- 进入实现时先做 `10.01` Docker Compose 封装，再做 `10.02` 酒馆式 provider 配置外观；不要同时改 provider adapter 和 Orchestrator。

## 2026-07-07：Tavern-Style Provider Config

### 完成

- 新增 provider config facade，将 `LLM_*`、`EMBEDDING_*`、`RAG_*` 映射到现有 provider 配置。
- `LLM_*` 可生成内部 `MODEL_PROVIDER_REGISTRY`，并覆盖 legacy 单 provider 默认值。
- 显式 `MODEL_PROVIDER_REGISTRY` 仍然优先，用于高级多模型路由。
- `EMBEDDING_*` 可映射到现有 embedding provider。
- `RAG_*` 可映射到 Qdrant / Chroma 等现有 RAG 字段。
- simple provider 字段存在且未显式设置 session 时，默认使用 SQLite session。
- `/config` schema 和 check 支持 simple 字段、secret redaction 和依赖校验。
- `.env.example` 和后端配置文档补充 simple provider 示例。

### 验证

- `uv run python -m unittest tests.test_provider_config_facade` 通过。
- `uv run python -m unittest tests.test_env_config_editor tests.test_provider_config_facade` 通过。
- `uv run python -m unittest tests.test_model_provider_registry tests.test_cloud_model_providers tests.test_embedding_providers tests.test_qdrant_rag_provider tests.test_local_vector_rag_provider tests.test_session_store_factory` 通过。
- `uv run python -m unittest tests.test_http_runtime_adapter` 通过。

### 下一步

- 继续实现 `10.01` Docker Compose 封装，复用本次已经跑通的 simple provider 字段。

## 2026-07-07：SQLite Memory Store

### 完成

- 新增 `SQLiteMemoryStore`，使用标准库 `sqlite3` 保存长期 memory。
- 新增 `MemoryStoreSettings` 和 `build_memory_store_from_env`。
- HTTP runtime 改为通过 memory store factory 装配，不再固定使用 `InMemoryMemoryStore`。
- `.env.example`、`.env.compose.example`、runtime config、env config schema 和使用文档补充 `MEMORY_PROVIDER=sqlite`。

### 验证

- `uv run python -m unittest tests.test_sqlite_memory_store tests.test_memory_store_factory tests.test_memory_crud tests.test_memory_read_policy tests.test_memory_write_policy tests.test_http_runtime_adapter` 通过。

### 下一步

- 继续实现 `11.04`，用 session 切片补 memory candidate 来源；不要把 session summary 混进 `MemoryStore`。

## 2026-07-13：Access Token Management And Quota Accounting

### 完成

- 新增 SQLite 服务令牌账本，令牌明文只在创建时返回，数据库只保存 SHA-256 哈希和安全前缀。
- 新增令牌创建、列表、详情、额度调整、吊销和逐令牌日志管理 API。
- 保留 `ROLEPLAY_API_KEY` 作为 bootstrap 管理密钥，服务令牌只能访问业务 API。
- 校验服务令牌状态和过期时间，并对已吊销或无效令牌返回统一鉴权错误。
- 逐令牌记录请求 ID、方法、路径、状态、耗时和错误码，不保存请求正文或密钥。
- 从普通聊天和 SSE usage 事件核算 prompt、completion、total tokens，并原子累计到账本。
- 额度耗尽时拒绝后续聊天，管理员可调整额度或设为不限额。
- 增加 `.env`、Compose、配置面板 schema、接口参考和接入文档。

### 验证

- `PYTHONPATH=src python -m unittest discover -s tests` 通过。
- 覆盖令牌明文不落库、过期、吊销、管理权限隔离、请求日志、普通/SSE 用量核算和额度恢复。

### 下一步

- 如果需要严格的并发硬上限，可在模型调用前增加额度预留和请求结束后的差额结算；当前按 Provider 返回的实际 usage 完成后结算。

## 2026-07-13：Access Token App Scope

### 完成

- 为 `AccessToken`、store port、创建用例和管理 API 增加单一 `app_id` scope。
- 新建令牌必须绑定非空 `app_id`，创建、列表、详情、额度调整和吊销响应均返回 scope。
- SQLite 新库持久化 `app_id`；旧库启动时原地增加 nullable 列，不重建 token 或日志表。
- 迁移前旧令牌以 `app_id=null` 表示 legacy unscoped，本阶段保持原鉴权行为。

### 验证

- Access Token store/admin API 共 19 项定向测试通过。
- 完整测试集共 229 项通过。
- 覆盖新库 scope 持久化、缺失 scope 校验、secret 不落库和旧库用量/日志无损迁移。

### 下一步

- 实现 12.03，在业务 HTTP 请求中比较服务令牌 scope 与请求 `app_id`；上线前替换并吊销 legacy unscoped token。

## 2026-07-13：Enforce Request App Scope

### 完成

- HTTP runtime 对 session、chat、RAG body 和 memory query 使用同一 Access Token app scope 规则。
- scope 校验早于聊天额度预检、业务 handler、provider 和 SSE 模型调用。
- 跨 app 和 legacy unscoped token 统一返回 `AUTH_PERMISSION_DENIED`。
- 管理密钥可跨 app；无 app 的 health/persona route 保持可调用。
- scope 拒绝沿用现有令牌审计日志，不保存 body、query 或用户内容。

### 验证

- Access Token admin/runtime 定向测试 15 项通过。
- 完整测试集 234 项通过。
- 覆盖 body/query route、普通/SSE 拒绝、legacy token、管理员跨 app 和拒绝审计。

### 下一步

- 实现 12.04，把 `app_id` 写入 RAG chunk metadata 并在所有 RAG backend 强制过滤。

## 2026-07-13：RAG App Isolation

### 完成

- 顶层 RAG `app_id` 写入每个 chunk metadata，并由 ingest domain 校验 scope 一致性。
- local、内存向量和 Faiss 通过统一 metadata filter 拒绝跨 app chunk。
- Chroma 和 Qdrant 的 payload、查询 filter 和内部 ID 都包含 app scope。
- 缺少 `app_id` 的旧持久化记录不会自动归属或参与检索；使用文档补充 collection 重建说明。
- 保留现有 character、persona、timeline、spoiler、language 和 source type 过滤语义。

### 验证

- RAG metadata/local/vector/Qdrant/embedding 定向测试 38 项通过。
- 完整测试集 240 项通过。
- 覆盖同 document ID 跨 app 隔离、Chroma payload/query filter、Qdrant point ID/filter，以及 legacy 无 scope 记录拒绝。

### 下一步

- 实现 12.05，为 HTTP body、chat message、RAG 文档、`top_k` 和 `max_tokens` 增加资源上限。

## 2026-07-13：Request Resource Limits

### 完成

- 集中定义 HTTP body、ID、chat message、RAG 文档/query 和生成参数的保守默认上限。
- 标准库 HTTP server 在读取前拒绝超过 1 MiB 的 `Content-Length`，runtime direct call 执行同一检查。
- 新增 `REQUEST_BODY_TOO_LARGE`，body 超限返回 413；DTO 字段超限继续返回 400 `VALIDATION_ERROR`。
- Chat/RAG DTO 严格校验 boolean、`top_k` 和 `max_tokens`，不再把字符串 `"false"` 当作 true。
- 超限请求在模型或 RAG provider 调用前失败，不增加依赖、环境变量或分布式限流系统。

### 验证

- Chat/RAG/HTTP/error 定向测试 65 项通过。
- 完整测试集 248 项通过。
- 覆盖 HTTP 预读拒绝、message/content/ID、`top_k`、`max_tokens`、boolean 类型和 provider 未调用。

### 下一步

- 实现 12.06，收束普通用户看到的 LLM、Embedding 和 RAG 配置面。

## 2026-07-13：Simple Config Surface

### 完成

- `/config` 默认只显示 HTTP、Storage、Simple LLM、Simple RAG 和 Simple Embedding，Advanced 默认折叠。
- schema 增加字段级 `advanced` 标记和 provider 字段矩阵，不新增配置 profile 系统。
- 单模型配置使用 `LLM_MODEL` 即可生成内部 route alias，registry 和高级 provider 配置继续保留并具有更高优先级。
- Simple provider 配置默认补齐 SQLite session/memory 与可见数据路径；显式 storage 配置仍优先。
- `.env.example` 收束为 fake model、hash embedding、local RAG 和 SQLite storage 的最小本地配置。

### 验证

- Simple facade、env editor、memory/session factory 和 HTTP adapter 定向测试 63 项通过。
- 完整测试集 250 项通过。
- `/config` 浏览器 smoke 通过：默认不显示高级字段，API type 字段矩阵、Advanced 展开和 SQLite Storage 路径符合预期。

### 下一步

- 实现 12.07 配置写入事务性。

## 2026-07-13：Minimal Frontend Chat Contract

### 完成

- `/v1/chat` 和 `/v1/chat/stream` 允许省略 `capabilities` 与 `generation`。
- 缺省能力关闭 RAG、memory、连续会话和 debug；流式路由仍强制 stream。
- 缺省 model 时使用 router default alias，普通前端不再绑定 fake、Ollama 或云模型名称。
- demo 使用共享 request builder，只发送启用的能力；model alias 移入默认折叠的 Advanced。

### 验证

- Chat DTO、Chat API、Stream Chat 和 HTTP runtime 定向测试 49 项通过。
- 完整测试集 252 项通过。
- 浏览器 smoke 通过：Advanced 默认折叠，model alias 留空时使用服务端 default alias，SSE `done` 后 Send 恢复可用。

### 下一步

- 实现 12.10 Access Token 计量正确性。

## 2026-07-13：Access Token Accounting Correctness

### 完成

- SSE 审计从 `data.error.code` 读取 provider 错误码，并兼容原顶层 `code`。
- OpenAI-compatible 响应缺少 usage 时同时估算 prompt 和 completion。
- provider usage 的负数或不可解析字段按单字段归零，已返回的有效真实值仍优先。

### 验证

- 云/本地模型 provider、Access Token 管理和 HTTP runtime 定向测试 70 项通过。
- 完整测试集 255 项通过。

### 下一步

- 实现 12.17 Production HTTP Gate；12.11 至 12.16 扩展能力继续延期。

## 2026-07-14：Production HTTP Gate

### 完成

- 非 loopback 监听要求至少 32 字符且不是示例占位值的管理密钥。
- CORS 改为同源自动允许、跨域精确白名单，不再返回 `*`。
- SSE 客户端断开时关闭事件迭代器，避免无意义 traceback 并保留审计清理。
- Compose 端口默认只映射宿主机 loopback，TLS 和公网限流交由反向代理。

### 验证

- HTTP runtime、server、配置 schema、SSE 和 Access Token 定向测试 80 项通过。
- 完整测试集 267 项通过。
- `docker compose config --quiet` 通过。

### 下一步

- 保持当前生产边界稳定；12.11 至 12.16 仅在明确要求扩大项目时恢复。

## 2026-07-14：Beginner Delivery Guide

### 完成

- 新增从 `.env`、启动、健康检查、服务令牌到最小 chat 和业务后端转发的单一快速开始路径。
- 重排根 README 和文档入口，区分第一次使用与开发扩展阅读顺序。
- 修正 Compose 强管理密钥、标准云 Provider 可选 base URL、可选依赖和本地 RAG 非持久化说明。
- 修正后端接入中的鉴权主体、app scope、额度和 Provider 限流错误处理说明。
- 将架构文档中尚不存在的独立 `ContextExecutor` 调整为当前实际由 `RoleplayOrchestrator` 执行。

### 验证

- 对照 Provider factory、配置 facade、HTTP runtime、Access Token API 和前端 demo 核对命令与字段。
- `README.md` 和 `docs/` 下 104 个 Markdown 文件的本地链接检查通过。
- `uv run python -m unittest discover -s tests`：267 项测试通过。
- `docker compose config --quiet`：通过。

### 下一步

- 先在受控测试环境按快速开始完成真实云 Provider smoke；只有出现明确业务需求时再恢复延期功能卡。

## 2026-07-14：Multi-period Access Token Quotas

### 完成

- 服务令牌新增可独立组合的生命周期、UTC 每日和 UTC ISO 周 Token 额度。
- 每日用量从 00:00 UTC 开始聚合，每周用量从周一 00:00 UTC 开始聚合；窗口切换保留历史日志和生命周期累计。
- 任一已配置尺度耗尽都会拒绝后续模型请求，响应同时返回各尺度用量、剩余量、重置时间和耗尽尺度。
- PATCH 支持只修改给定尺度，显式 `null` 清除限制；旧 SQLite 账本自动补充 nullable 日、周额度列。
- 后台服务令牌工作台支持创建、查看和编辑三种额度，并在列表中区分总、日、周剩余额度。

### 验证

- Access Token 存储和管理接口定向测试 36 项通过。
- 后台认证与令牌管理接口测试 30 项通过，后台脚本语法和 CSP 静态约束检查通过。
- 完整测试集 309 项通过，1 项跳过。

### 下一步

- 如需严格并发硬上限，在模型调用前增加额度预留，并在请求结束后按实际 usage 差额结算。

## 2026-07-14：Admin Console Review Hardening

### 完成

- Access Token 部分额度 PATCH 改为单条 SQL 原子更新，避免并发修改不同尺度时丢失更新。
- Qdrant 管理列表完整消费 scroll 分页，FAISS upsert 按 chunk ID 替换已有记录。
- PostgreSQL 后台关闭会话在同一事务中锁定、读取并更新目标行，同时校验受影响行数。
- 非 loopback 配置检查把缺失的安全 Cookie 设置视为 `false`，不再绕过生产门禁。
- Memory provider 使用实现自身声明的稳定标识，不再依赖类名匹配。
- 明确反向代理部署时应用只看到 TCP 对端地址，真实客户端 IP 登录限流必须由可信代理执行。

### 验证

- 存储一致性相关定向测试 63 项通过。
- 后台配置、记忆和认证定向测试 22 项通过。
- 完整测试集 313 项通过，1 项跳过；Python compileall 和后台脚本语法检查通过。

### 下一步

- 保持转发客户端 IP 默认不可信；只有引入显式可信代理名单后，才在应用内消费转发头。
