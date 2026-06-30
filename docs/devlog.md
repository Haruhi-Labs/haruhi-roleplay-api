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
