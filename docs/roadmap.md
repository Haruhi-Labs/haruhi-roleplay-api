# Roadmap

## 项目目标

本项目要实现一个 Roleplay API 中转服务，用统一接口封装角色 preset、连续会话、RAG、记忆和模型 provider 调度。第一阶段优先保证本地可运行、接口稳定、前端可接入。

## MVP 范围

第一版只保留最小闭环：

- 角色和 preset catalog。
- 非流式 `POST /v1/chat`。
- `GET /v1/personas`。
- PromptBuilder v1。
- FakeModelProvider。
- 统一响应和错误格式。

第一版先不做：

- Admin 后台。
- 云端数据库和向量库。
- 多 provider 全量接入。
- 复杂 RAG rerank。
- 自动 memory consolidation。
- 完整评测平台。

## 开发阶段

| 阶段    | 目标              | 验收                                             |
| ------- | ----------------- | ------------------------------------------------ |
| Phase A | 契约和骨架        | DTO、错误格式、persona schema 清楚               |
| Phase B | 最小 Chat 闭环    | `GET /v1/personas` 和 `POST /v1/chat` 可本地调用 |
| Phase C | 本地可用性        | 本地模型、连续会话、debug trace 可用             |
| Phase D | RAG 最小闭环      | 本地文档可导入、检索、返回 source                |
| Phase E | Memory 最小闭环   | memory 可查询、读取、写入、删除                  |
| Phase F | Stream 和云端替换 | 流式输出和 cloud provider 按需替换               |

## 当前优先级

1. Chat DTO 契约。
2. 统一响应和错误格式。
3. Persona catalog schema。
4. `GET /v1/personas`。
5. PromptBuilder v1。
6. FakeModelProvider。
7. `POST /v1/chat` v1。

完成以上 7 步后，项目进入“最小可运行 Roleplay API”状态。

## 交付原则

- 每次只做一个小功能。
- 每步都能人工 review。
- 每步都有本地验证方式。
- 不一次性实现多个 provider。
- 不在第一版同时推进 RAG、memory、stream 和 cloud。
