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
