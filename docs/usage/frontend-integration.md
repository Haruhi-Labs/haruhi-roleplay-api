# 前端接入说明

如果你要直接照着写调用代码，先看 [前端调用完整文档](frontend-api-calling.md)。本文主要解释前端、业务后端和本项目中转服务之间的边界。

## 适用场景

Web、移动端、小程序、游戏 UI 可以通过自己的后端调用本服务。前端通常不应该直接持有 Roleplay API 的 API Key。

## 推荐架构

前端 -> 业务后端 -> Roleplay API

原因：

- API Key 不暴露给浏览器。
- 业务后端可以绑定登录用户和 `user_id`。
- 可以统一做风控、限流、日志和付费逻辑。

## 前端需要关心的字段

| 字段         | 来源           | 用途                   |
| ------------ | -------------- | ---------------------- |
| session_id   | 后端创建后返回 | 连续会话               |
| character_id | catalog 接口   | 选择角色               |
| persona_mode | catalog 接口   | 选择角色 preset        |
| message      | 用户输入       | 当前消息               |
| stream       | UI 设置        | 是否流式显示           |
| reply        | API 返回       | 展示回复               |
| sources      | API 返回       | 展示 RAG 来源          |
| debug        | 开发环境返回   | 调试，不给普通用户展示 |

## UI 角色和 Preset 选择

前端不要硬编码三种春日模式。推荐启动时或进入页面时调用 `GET /v1/personas`，拿到可展示的角色和 preset catalog。

内置角色可以先展示为：

| UI 名称      | character_id   | persona_mode         | 说明                           |
| ------------ | -------------- | -------------------- | ------------------------------ |
| 刚入学的春日 | haruhi         | entrance_haruhi      | 更强势、更兴奋、更主动         |
| 中后期的春日 | haruhi         | mid_late_haruhi      | 更熟悉社团关系，互动更稳定     |
| 消失春日     | haruhi         | disappearance_haruhi | 更日常、更克制                 |
| 朝比奈学姐   | asahina_mikuru | default_mikuru       | 更温和、更紧张、更照顾对话氛围 |
| 阿虚         | kyon           | default_kyon         | 更冷静、更吐槽、更像旁观叙述   |

自定义角色只要 `visibility=public`，也应该出现在 catalog 中。

角色和 preset 字段含义见 [Character Schema](../character-schema.md)。

## 非流式前端流程

1. 用户输入消息。
2. 前端把消息发给业务后端。
3. 业务后端调用 `POST /v1/chat`。
4. 前端等待完整回复。
5. 前端展示 `reply`。
6. 如果有 `rag.sources`，展示“参考资料”入口。

适合：

- 简单页面。
- 移动端弱网。
- 不需要打字机效果的场景。

## 流式前端流程

1. 用户输入消息。
2. 前端请求业务后端的 stream endpoint。
3. 业务后端调用 `POST /v1/chat/stream`，并把 Roleplay API 的 stream event 转发给前端。
4. 前端收到 `start` 后创建 assistant 消息占位。
5. 前端收到 `delta` 后追加文本。
6. 前端收到 `source` 后缓存引用来源。
7. 前端收到 `done` 后结束 loading。
8. 前端收到 `error` 后展示失败状态。

当前项目的框架无关 handler 以 `data.events` 数组表达 stream event；业务后端接入真实 HTTP 框架后，应逐条转成 SSE 或等价流式协议。

适合：

- Web 聊天窗口。
- 希望降低等待感的场景。
- 长回复。

## 前端状态建议

| 状态      | 说明           |
| --------- | -------------- |
| idle      | 未发送         |
| sending   | 请求已发出     |
| streaming | 正在接收 delta |
| completed | 回复完成       |
| failed    | 请求失败       |

## 本地 Demo

当前仓库提供零构建静态前端 demo。启动本地 HTTP server 后访问：

```text
http://127.0.0.1:8000/demo
```

Demo 功能：

- 读取 `GET /v1/personas` 并选择角色和 preset。
- 调用 `POST /v1/sessions` 创建连续会话。
- 调用 `POST /v1/chat` 发送非流式消息。
- 调用 `POST /v1/chat/stream` 展示 stream delta。
- 调用 `POST /v1/rag/documents` 导入最小资料片段。
- 展示 RAG source 摘要；debug 摘要默认折叠，仅用于开发排查。

Demo 默认使用同源 API。若本地服务配置了 `ROLEPLAY_API_KEY`，需要在 demo 的 API Key 输入框中临时填写；该值只保存在当前页面内存，不写入 localStorage。

## 前端展示规则

- 普通用户不展示 debug trace。
- RAG source 只展示 title、source type、score 或简短摘要。
- 不展示完整 chunk，除非产品明确需要。
- Safety blocked 时展示温和提示。
- session 过期时提示重新开始对话。

## Memory 管理 UI

当前前端可以通过业务后端展示和删除用户长期记忆。产品允许时，也可以在 chat 请求中开启 `capabilities.memory=true`，由服务端按策略读取有限记忆，并写入通过 policy 的显式候选。

推荐流程：

1. 进入角色设置或隐私管理页时，由业务后端调用 `GET /v1/memory/{user_id}`。
2. 查询参数必须包含 `app_id` 和 `character_id`，如果是 preset 专属记忆，还要传 `persona_mode`。
3. UI 展示 `type`、`content`、`confidence`、`updated_at`。
4. 用户删除时，由业务后端调用 `DELETE /v1/memory/{user_id}/{memory_id}`。

前端不要自己拼接或新增 memory，也不要把 memory 内容直接塞进用户消息。若产品需要写入候选，应由业务后端生成 `metadata.memory_write`，并携带明确 reason 和 confidence。

## 前端不要做什么

- 不要在浏览器保存 API Key。
- 不要在前端硬编码系统 prompt。
- 不要把 debug trace 暴露给普通用户。
- 不要让普通聊天 UI 选择 agent planner；planner 是服务端运行时配置。
- 不要让普通聊天 UI 选择 backend context source；source 是服务端运行时配置。
- 不要允许用户直接修改 `app_id`。
- 不要把 RAG source 当作模型回复的一部分混排到角色台词里。

## 前端与中转服务的边界

前端只表达用户意图和产品能力选择，不直接选择本项目内部的后端实现。

前端可以选择：

- `character_id`
- `persona_mode`
- 是否使用连续会话
- 是否请求流式输出
- 是否在产品允许时开启 RAG 或 memory
- 可被白名单允许的模型别名

前端不能选择：

- 数据库 provider
- 向量库 provider
- embedding provider
- 真实模型厂商和密钥
- RAG 文档物理存储位置
- backend context source

这些调度由本项目根据配置完成，详见 [中转服务后端调度与配置说明](backend-dispatch-and-configuration.md)。

## 管理前端：运行时配置

普通聊天前端不应该直接修改 provider 配置。若需要做本地管理面板或开发调试面板，可以调用：

- `GET /v1/runtime-config`
- `PATCH /v1/runtime-config`

这两个接口必须带 `Authorization: Bearer <ROLEPLAY_API_KEY>` 或 `X-API-Key`。管理前端只能修改服务端白名单允许的非敏感配置，例如 `MODEL_PROVIDER`、`MODEL_NAME`、`MODEL_ALIAS`、`RAG_PROVIDER`、`EMBEDDING_PROVIDER`、`CHROMA_COLLECTION`、`AGENT_CONTEXT_PLANNER`、`BACKEND_CONTEXT_PROVIDER`、`BACKEND_CONTEXT_SOURCES`、`SESSION_RECENT_LIMIT` 等。

示例：

```ts
await fetch(`${baseUrl}/v1/runtime-config`, {
  method: "PATCH",
  headers: {
    "Content-Type": "application/json",
    Authorization: `Bearer ${adminApiKey}`,
  },
  body: JSON.stringify({
    values: {
      MODEL_PROVIDER: "fake",
      MODEL_NAME: "fake-roleplay-model",
      MODEL_ALIAS: "fake-roleplay-model",
      RAG_PROVIDER: "local",
      AGENT_CONTEXT_PLANNER: "deterministic",
      BACKEND_CONTEXT_PROVIDER: "fake",
      BACKEND_CONTEXT_SOURCES: "user_profile,game_state",
      SESSION_RECENT_LIMIT: "12",
    },
  }),
});
```

普通聊天前端和 `PATCH /v1/runtime-config` 不提交密钥类配置，例如 `OPENAI_API_KEY`、`DEEPSEEK_API_KEY`、`GEMINI_API_KEY`。如果需要可视化维护这些值，只能使用受信任 `.env` 编辑器的 write-only secret 输入；保存后 UI 只能显示 set/empty/missing 状态，不能回显原文。

管理前端可以展示 `GET /v1/runtime-config` 返回的 `restart_required_keys`，但不要把这些 key 做成“立即生效”的开关。比如 `SESSION_PROVIDER`、`SESSION_SQLITE_PATH` 需要服务重启后重新装配 session store，不能在普通聊天过程中热切换。

`AGENT_CONTEXT_PLANNER=model` 当前只是后续模型辅助规划的预留入口。管理前端可以展示这个状态，但不应把它作为可用选项开放给普通用户。

`BACKEND_CONTEXT_PROVIDER=fake` 当前只用于本地调试。真实业务后端 adapter 接入前，管理前端可以展示 backend context 是否启用、读取了哪些 source，但不要把 source 选择暴露给普通聊天用户。

更完整的 `.env` 编辑器设计见 [全量 .env 编辑器使用与设计说明](config-panel.md)。

`.env` 编辑器建议拆成独立受信任页面，而不是放进普通聊天界面。它可以做：

- 通过 `/config` 打开本地受信任配置页面。
- 读取当前 `.env` 的 redacted 摘要。
- 按 HTTP、Model、RAG、Embedding、Agent、Backend Context、Session、Secrets 分组展示字段。
- 创建配置草稿、字段 check 和 diff preview。
- 修改普通字段、restart-required 字段和 secret 字段。
- 保存 `.env` 后提示哪些字段已热更新、哪些字段需要重启。

`.env` 编辑器不应该做：

- 让普通用户访问。
- 回显真实 API key、token、secret 或 `DATABASE_URL`。
- 把 `.env` 原文完整返回给浏览器。
- 让浏览器直接读写 `.env` 文件。
- 承诺所有字段保存后都立即生效。
- 绕过 Env Config Editor API 直接写 `.env`。

当前 `/config` 页面不会在普通聊天 demo 中出现入口。接入后台时，也应把它放在受信任管理区，而不是普通用户聊天页。
