# Haruhi Roleplay API 文档入口

## 文档定位

本目录用于指导一个个人开发者逐步实现 Roleplay API 中转服务。文档不是一次性大设计，而是按“可人工审核、可本地验证、可逐步扩展”的方式组织。

## 第一次使用

只想配置后端并让前端发出第一条消息时，按下面顺序阅读：

1. `usage/quickstart.md`
   从复制 `.env`、启动服务、签发服务令牌，到调用 chat 和接入业务后端。

2. `usage/backend-config.md`
   切换 fake、Ollama、OpenAI-compatible、DeepSeek、Gemini、Embedding 和 RAG。

3. `usage/frontend-api-calling.md`
   实现非流式 chat、SSE、session、RAG 和 memory 调用。

4. `usage/access-token-management.md`
   为每个 `app_id` 签发和管理独立业务令牌。

5. `usage/docker-compose.md`
   在 Linux 单机上使用 Docker Compose，并理解反向代理和数据持久化边界。

## 开发和扩展

需要修改项目或增加 Provider、角色和能力时，按下面顺序阅读：

1. `roadmap.md`
   确认当前交付边界和延期项。

2. `architecture.md`
   查看整体请求链路、Agent 编排和模块边界。

3. `layered-architecture.md`
   查看 `domain`、`application`、`ports`、`adapters`、`api` 等分层含义和开发加入方式。

4. `character-schema.md`
   查看角色、preset、`ToneConfig`、知识边界和可见性字段说明。

5. `api-contract.md` 和 `usage/interface-reference.md`
   查看正式 API 契约和全部接口字段。

6. `usage/backend-dispatch-and-configuration.md`
   查看 registry、多 Provider、Agent、Session、Memory 和 RAG 的完整装配关系。

7. `usage/config-panel.md`
   查看受信任 `.env` 编辑器的边界和字段检查规则。

8. `devlog.md`
   查看开发记录和实际验证历史。

## 目录说明

| 目录     | 用途                 | 是否直接作为实现任务  |
| -------- | -------------------- | --------------------- |
| `guide/` | 长期设计规范         | 否，作为 review 标准  |
| `usage/` | 前后端接入和接口说明 | 否，作为 API 使用参考 |
