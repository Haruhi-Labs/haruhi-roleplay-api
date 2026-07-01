# Layered Architecture

## 文档位置

本项目的分层说明以本文档为主。

- 总体架构入口：`docs/architecture.md`
- 长期设计规范：`docs/guide/design-spec.md`
- 后端调度说明：`docs/usage/backend-dispatch-and-configuration.md`
- 当前源码路径：`src/haruhi_roleplay_api/`

## 为什么要分层

这个项目是 Roleplay API 中转服务，不是单个聊天脚本。它后续会同时接入角色 preset、PromptBuilder、FakeModel、本地模型、RAG、memory、session 和云端 provider。

分层的意义是把变化速度不同的东西分开：

- 角色、请求、prompt 这些业务概念要稳定。
- HTTP 框架、数据库、模型厂商、向量库这些实现可以替换。
- 测试时可以用 fake adapter，不调用真实模型或云服务。
- 前端和业务后端看到的是统一 API，不知道内部 provider 如何调度。

简单说：分层不是为了显得“架构味很浓”，而是为了让个人开发时每一步都小、可测、可替换。

## 依赖方向

推荐依赖方向：

```text
api -> application -> domain
api -> application -> ports
adapters -> ports
adapters -> domain
infrastructure -> api / application / adapters
```

禁止依赖方向：

```text
domain -> api
domain -> adapters
application -> adapters
application -> provider SDK
ports -> adapters
PromptBuilder -> PersonaRepository
ModelProvider -> RAG / memory / session 业务规则
```

## 各层含义

| 层 | 路径 | 表示什么 | 可以做什么 | 不应该做什么 |
| --- | --- | --- | --- | --- |
| `domain` | `src/haruhi_roleplay_api/domain/` | 项目的业务名词、DTO、值对象和纯规则 | 定义 `ChatInput`、`PersonaPreset`、`PromptBuildInput` 等稳定结构；做基础字段校验 | 读取文件、访问数据库、调用模型 SDK、知道 HTTP 框架 |
| `application` | `src/haruhi_roleplay_api/application/` | use case、orchestrator 和业务编排 | 调用 ports；决定流程顺序；组合 domain 对象；转换业务错误 | 直接读写文件、直接连接数据库、直接调用 OpenAI/Ollama/Qdrant SDK |
| `ports` | `src/haruhi_roleplay_api/ports/` | 外部能力接口，也就是 application 眼里的“插座” | 定义 `PersonaRepository`、`PromptBuilder`、未来的 `ChatModelProvider`、`SessionStore` | 放具体实现、读取环境变量、依赖 adapter |
| `adapters` | `src/haruhi_roleplay_api/adapters/` | ports 的具体实现 | 本地读 JSON、调用 fake model、连接数据库、接模型 SDK | 写业务编排规则；反向要求 domain/application 知道具体 provider |
| `api` | `src/haruhi_roleplay_api/api/` | 对外接口入口和响应映射 | 做 handler、request/response envelope、HTTP 字段和内部字段转换 | 直接访问数据库或文件；把复杂业务逻辑写在 controller 里 |
| `infrastructure` | `src/haruhi_roleplay_api/infrastructure/` | 启动、配置、依赖注入和 provider pack | 根据环境选择 adapter；组装 application use case；校验配置 | 写角色业务规则；泄露 secret 到日志或响应 |

## 当前项目中的例子

### domain

- `domain/chat.py`：聊天输入输出契约。
- `domain/persona.py`：角色和 preset schema。
- `domain/prompt.py`：PromptBuilder 的输入、输出和 message 结构。

这些对象应该尽量稳定。比如 `PromptBuildInput` 只描述 PromptBuilder 需要什么，不关心这些数据来自文件、数据库还是测试 fake。

### application

- `application/personas.py`：列出公开角色 catalog 的 use case。
- `application/prompts.py`：默认 `PersonaPromptBuilder`，把角色配置组装成模型 messages。
- `application/errors.py`：统一业务错误。

application 层可以表达业务流程，但只能通过 ports 接触外部能力。

### ports

- `ports/personas.py`：`PersonaRepository` 接口。
- `ports/prompts.py`：`PromptBuilder` 接口。

ports 是可替换能力的边界。以后从本地 JSON 换成 PostgreSQL，application 仍然只认识 `PersonaRepository`。

### adapters

- `adapters/personas.py`：`LocalPersonaRepository`，从本地 `personas/` 目录读 JSON。

adapter 可以知道文件路径、SDK、数据库连接，但要把结果转换成 domain 对象再交给 application。

### api

- `api/responses.py`：统一成功/失败响应 envelope。
- `api/personas.py`：`get_personas` handler。

api 层负责把外部调用映射到 application use case。当前还没有接 FastAPI/Flask，所以 handler 是框架无关函数。

## 如何加入开发

新增功能时，按这个顺序走，人工 review 会轻很多：

1. 先读对应卡片。
   - 位置：`docs/agent-dev/cards/`
   - 明确本步做什么、不做什么、测试什么。

2. 先判断是否需要新增 domain 对象。
   - 请求、响应、角色、prompt、memory item 这类稳定名词放 `domain`。
   - 不要把 HTTP `snake_case` 或数据库 row 直接放进 domain。

3. 再判断是否需要 port。
   - 只要能力未来可能换实现，就先定义 port。
   - 例如模型、RAG、memory、session、persona repository 都应该是 port。

4. 在 application 写 use case 或 orchestrator。
   - 这里决定业务顺序。
   - 这里只依赖 domain 和 ports。
   - 不直接 `Path(...)` 读文件，也不直接 new 具体 adapter。

5. 在 adapters 写具体实现。
   - 本地开发先写 local 或 fake adapter。
   - adapter 负责处理 SDK、文件、数据库、网络错误，并转成统一错误或 domain 对象。

6. 在 api 写入口。
   - 做字段映射、响应 envelope、错误映射。
   - 不把业务流程写在 handler 里。

7. 写最小测试。
   - domain：测字段校验和边界。
   - application：测流程、过滤、能力开关。
   - adapter：测本地读取、缺失配置、错误转换。
   - api：测响应 envelope 和对外字段。

8. 更新文档和 devlog。
   - 如果新增对外字段，更新 `docs/api-contract.md` 或 `docs/usage/interface-reference.md`。
   - 如果新增架构边界，更新本文档或 `docs/architecture.md`。
   - 如果完成一张卡片，更新 `docs/devlog.md` 和对应 card。

## 判断代码应该放哪一层

| 问题 | 放置位置 |
| --- | --- |
| “这个字段是业务概念吗？” | `domain` |
| “这是一个用户动作或业务流程吗？” | `application` |
| “这是可替换外部能力的接口吗？” | `ports` |
| “这是某个接口的具体实现吗？” | `adapters` |
| “这是 HTTP/SSE/WebSocket 入口或响应格式吗？” | `api` |
| “这是启动配置、provider pack 或依赖注入吗？” | `infrastructure` |

## 当前阶段的开发建议

当前项目还在 MVP 早期，推荐继续保持这种节奏：

1. 每张卡片只新增一个小能力。
2. 优先 fake/local provider，不急着接云服务。
3. application 层不要依赖具体 adapter。
4. PromptBuilder 不查数据，只组织上下文。
5. ModelProvider 不理解 persona、RAG、memory 的业务规则。
6. 新增能力时先保证 `unittest` 可以本地跑通。

