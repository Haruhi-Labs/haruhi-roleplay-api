# Haruhi Roleplay API 文档入口

## 文档定位

本目录用于指导一个个人开发者逐步实现 Roleplay API 中转服务。文档不是一次性大设计，而是按“可人工审核、可本地验证、可逐步扩展”的方式组织。

## 推荐阅读顺序

1. `roadmap.md`
   先确认项目路线和 MVP 边界。

2. `architecture.md`
   查看整体架构和模块边界。

3. `layered-architecture.md`
   查看 `domain`、`application`、`ports`、`adapters`、`api` 等分层含义和开发加入方式。

4. `character-schema.md`
   查看角色、preset、`ToneConfig`、知识边界和可见性字段说明。

5. `api-contract.md`
   查看对外 API 契约。

6. `usage/frontend-api-calling.md`
   前端调用完整手册从这里开始，包含 chat、stream、RAG、memory 和本地 demo 调用方式。

7. `usage/frontend-integration.md`
   查看前端、业务后端和本项目中转服务的职责边界。

8. `usage/backend-config.md`
   后端配置从这里开始，包含最小 `.env`、配置分组、热更新边界和化简分析。

9. `usage/docker-compose.md`
   查看 Docker Compose 使用方式，以及酒馆式 provider、base URL、model/index、token 配置入口。

10. `usage/config-panel.md`
   查看受信任全量 `.env` 编辑器的使用边界和设计规则。

11. `usage/access-token-management.md`
    查看服务令牌签发、鉴权、额度核算、吊销和逐令牌日志。

12. `usage/interface-reference.md`
   查看更完整的接口字段说明。

13. `devlog.md`
   查看开发记录。

## 目录说明

| 目录     | 用途                 | 是否直接作为实现任务  |
| -------- | -------------------- | --------------------- |
| `guide/` | 长期设计规范         | 否，作为 review 标准  |
| `usage/` | 前后端接入和接口说明 | 否，作为 API 使用参考 |
