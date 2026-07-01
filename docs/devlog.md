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
