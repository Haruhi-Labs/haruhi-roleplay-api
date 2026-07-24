# Haruhi Roleplay API 文档入口

## 文档定位

本目录同时面向生产 API 接入方、部署管理员和项目开发者。生产接入以
`usage/production-api.md` 为首要入口；其余文档按“可人工审核、可本地验证、可逐步扩展”
的方式组织。

## 第一次使用

接入已经部署的生产服务时：

1. `usage/production-api.md`
   查看生产地址、服务令牌、完整 Chat 参数、当前角色目录、SSE、RAG、Memory 与错误处理。

2. `usage/interface-reference.md` 和 `api-contract.md`
   分别查看全部接口字段与稳定协议语义。

自行部署或本地开发时，按下面顺序阅读：

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

6. `usage/admin-console.md`
   使用安全后台管理令牌、角色、模型、用量、会话、RAG、记忆、审计和系统配置。

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

5. `persona-design.md`
   查看 SOS 团五名角色的篇章划分、视角边界、关系规则和失真检查方法。

6. `api-contract.md`、`usage/production-api.md` 和 `usage/interface-reference.md`
   查看正式 API 契约、生产接入方式和全部接口字段。

7. `usage/backend-dispatch-and-configuration.md`
   查看 registry、多 Provider、Agent、Session、Memory 和 RAG 的完整装配关系。

8. `usage/config-panel.md`
   查看受信任 `.env` 编辑器的边界和字段检查规则。

9. `devlog.md`
   查看开发记录和实际验证历史。

## 目录说明

| 目录     | 用途                 | 是否直接作为实现任务  |
| -------- | -------------------- | --------------------- |
| `guide/` | 长期设计规范         | 否，作为 review 标准  |
| `usage/` | 前后端接入和接口说明 | 否，作为 API 使用参考 |
