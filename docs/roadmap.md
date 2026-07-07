# Roadmap

## 项目目标

本项目要实现一个面向前端和业务后端的凉宫春日 Roleplay API 中转服务。它通过 HTTP/Stream 接口接收角色对话请求，在本项目内部解析、校验、分析请求，再按策略调度模型 provider、RAG、session、memory 和后续业务后端上下文，最后把统一响应返回给调用方。

项目定位合理，但不能把 HTTP 运行层、多模型 provider、云端 RAG、完整 Agent 编排和前端 demo 放在同一个 milestone。作为个人开发者，应按“先可运行、再可替换、再会分析、最后可展示”的顺序推进。

## 需求合理性判断

当前四个方向整体合理：

1. HTTP API 调用封装是必须项，否则前端和业务后端无法真实接入。
2. 可用后端实现是必须项，但要按 provider 一个个接入，不能一次性接完 Ollama、DeepSeek、OpenAI、云端 RAG。
3. 完整 Agent 编排是项目的中长期核心，但第一版必须先做 deterministic planner，再考虑模型辅助 planner。
4. 最简前端 demo 合理，但它应该验证接入体验，不应该变成完整产品后台。
5. 受信任全量 `.env` 编辑器合理，但应放在普通聊天 demo 之后，用于本地开发和受控后台；它可以编辑 secret 和 restart-required 字段，但必须通过字段 schema、check、redaction 和重启提示保证安全。

不合理的部分是交付方式：如果把以上内容作为一个大任务实现，会造成 diff 过大、测试困难、人工 review 负担过高，也会让 provider、Agent、UI 的问题互相干扰。因此必须拆成可独立验证的 cards。

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

当前 MVP 已逐步扩展出 session、debug trace、RAG、memory 和 stream。后续路线要从“功能原型”转向“产品化中转服务”。

## 开发阶段

| 阶段    | 目标                   | 验收                                                                           |
| ------- | ---------------------- | ------------------------------------------------------------------------------ |
| Phase A | 契约和骨架             | DTO、错误格式、persona schema 清楚                                             |
| Phase B | 最小 Chat 闭环         | `GET /v1/personas` 和 `POST /v1/chat` 可本地调用                               |
| Phase C | 本地可用性             | 本地模型、连续会话、debug trace 可用                                           |
| Phase D | RAG 最小闭环           | 本地文档可导入、检索、返回 source                                              |
| Phase E | Memory 最小闭环        | memory 可查询、读取、写入、删除                                                |
| Phase F | Stream 和 HTTP 运行层  | 流式输出和真实 HTTP/SSE adapter 可调用                                         |
| Phase G | Provider Pack 产品化   | Ollama/OpenAI-compatible、DeepSeek、OpenAI、本地/云端 RAG 可替换               |
| Phase H | Agent 编排 v1          | 能根据请求分析上下文需求，调度 session、memory、RAG 和业务后端上下文           |
| Phase I | 前端 Demo              | 最简聊天界面可选择角色、发消息、展示 stream、source 和 memory 状态             |
| Phase J | `.env` 编辑器          | 受信任页面可查看 `.env` 摘要、创建配置草稿、check 字段并保存配置               |
| Phase K | Compose 部署与配置收束 | Docker Compose 单容器、SQLite 默认、酒馆式 LLM/Embedding/RAG provider 配置可用 |

## 当前优先级

1. 补真实 HTTP API 运行封装，让 `GET /v1/personas`、`POST /v1/chat`、`POST /v1/chat/stream` 可通过本地服务调用。
2. 把现有 fake/local provider 装配为明确的 provider pack。
3. 逐个增加常见模型 provider：Ollama local、DeepSeek、OpenAI/OpenAI-compatible。
4. 把 RAG 拆成本地检索和云端检索两类 provider，先稳定 port，再接具体实现。
5. 增加 AgentContextPlanner 和 ContextExecutor，让本项目能分析请求并决定要拉取哪些上下文。
6. 做最简前端 demo，用 catalog 选择角色，用 chat/stream 展示回复和 sources。
7. 做受信任 `.env` 编辑器，用独立 env config API 查看、选择、check 和保存配置草稿。
8. 提供一个 Docker Compose 单容器封装，并把用户配置收束为 API type / provider、base URL、model/index 和 token。

完成以上步骤后，项目进入“可被前端真实接入的 Roleplay API 中转服务”状态。

## 交付原则

- 每次只做一个小功能。
- 每步都能人工 review。
- 每步都有本地验证方式。
- 不一次性实现多个 provider。
- 不把所有 provider 放进一个 PR。
- 不让前端直接选择真实 provider、数据库、向量库或密钥。
- Agent 先做 deterministic planner，再考虑模型辅助 planner。
- 前端 demo 先做最小聊天体验，不先做完整产品后台。
- `.env` 编辑器只面向本地开发或受信任后台，不进入普通聊天 UI。
- Linux 部署只做 Docker Compose 单容器封装，不先引入 Kubernetes、Helm、云数据库或多容器本地模型栈。
- 配置预设只表示 provider/API type 选择器，不表示一整套部署方案。
