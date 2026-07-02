# 前端接入说明

## 适用场景

Web、移动端、小程序、游戏 UI 可以通过自己的后端调用本服务。前端通常不应该直接持有 Roleplay API 的 API Key。

## 推荐架构

前端 -> 业务后端 -> Roleplay API

原因：

- API Key 不暴露给浏览器。
- 业务后端可以绑定登录用户和 `user_id`。
- 可以统一做风控、限流、日志和付费逻辑。

## 前端需要关心的字段

| 字段 | 来源 | 用途 |
| --- | --- | --- |
| session_id | 后端创建后返回 | 连续会话 |
| character_id | catalog 接口 | 选择角色 |
| persona_mode | catalog 接口 | 选择角色 preset |
| message | 用户输入 | 当前消息 |
| stream | UI 设置 | 是否流式显示 |
| reply | API 返回 | 展示回复 |
| sources | API 返回 | 展示 RAG 来源 |
| debug | 开发环境返回 | 调试，不给普通用户展示 |

## UI 角色和 Preset 选择

前端不要硬编码三种春日模式。推荐启动时或进入页面时调用 `GET /v1/personas`，拿到可展示的角色和 preset catalog。

内置角色可以先展示为：

| UI 名称 | character_id | persona_mode | 说明 |
| --- | --- | --- | --- |
| 刚入学的春日 | haruhi | entrance_haruhi | 更强势、更兴奋、更主动 |
| 中后期的春日 | haruhi | mid_late_haruhi | 更熟悉社团关系，互动更稳定 |
| 消失春日 | haruhi | disappearance_haruhi | 更日常、更克制 |
| 朝比奈学姐 | asahina_mikuru | default_mikuru | 更温和、更紧张、更照顾对话氛围 |
| 阿虚 | kyon | default_kyon | 更冷静、更吐槽、更像旁观叙述 |

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
3. 业务后端转发 Roleplay API 的 stream event。
4. 前端收到 `start` 后创建 assistant 消息占位。
5. 前端收到 `delta` 后追加文本。
6. 前端收到 `source` 后缓存引用来源。
7. 前端收到 `done` 后结束 loading。
8. 前端收到 `error` 后展示失败状态。

适合：

- Web 聊天窗口。
- 希望降低等待感的场景。
- 长回复。

## 前端状态建议

| 状态 | 说明 |
| --- | --- |
| idle | 未发送 |
| sending | 请求已发出 |
| streaming | 正在接收 delta |
| completed | 回复完成 |
| failed | 请求失败 |

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

这些调度由本项目根据配置完成，详见 [中转服务后端调度与配置说明](backend-dispatch-and-configuration.md)。
