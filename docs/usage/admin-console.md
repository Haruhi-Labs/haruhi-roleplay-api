# 后台管理控制室

## 入口与登录

服务启动后访问：

```text
http://127.0.0.1:8000/admin/
```

登录密码就是部署时配置的 `ROLEPLAY_API_KEY`。浏览器登录后只保存服务端签发的 `HttpOnly` 会话 Cookie；密码和 CSRF Token 不写入 `localStorage`、`sessionStorage` 或 URL。

后台包含以下工作台：

| 工作台 | 能力 |
| --- | --- |
| 总览 | 7 天请求、Token、错误率、服务健康、额度、Provider、角色、RAG、记忆和活跃会话 |
| 用量分析 | 7/30/90 天趋势、逐服务与逐路由聚合、全局业务请求日志 |
| 运行会话 | 按应用、用户、角色和状态筛选；查看消息数量；关闭活跃会话 |
| 服务令牌 | 签发绑定 App 的令牌、一次性展示明文、组合设置生命周期/每日/每周额度、吊销、查看逐请求日志 |
| 角色 | 创建和维护角色、Persona 模式、可见性、语气、知识边界、RAG/Memory 策略 |
| 模型 | 配置主模型、Provider、Base URL、密钥状态和多模型 Registry，保存前检查 |
| RAG 知识 | 真实 Provider 文档盘点、导入、检索测试和按 App 隔离删除 |
| 记忆 | 多维筛选、分页、人工写入和精确删除长期记忆 |
| 安全审计 | 查看登录及后台变更结果，按主体和成功/失败筛选 |
| 系统配置 | 原生分组配置、只写密钥、草稿审阅、服务端检查、热更新与重启提示 |

## 安全模型

后台会话具有以下边界：

- 登录失败按客户端地址执行内存速率限制；错误响应不区分密码错误和管理能力未配置。
- Cookie 使用 `HttpOnly`、`SameSite=Strict` 和固定 Path；非 loopback 部署强制 `Secure`。
- `POST`、`PATCH`、`PUT` 和 `DELETE` 管理请求必须同时通过会话认证和 CSRF Token 校验。
- 会话同时受绝对 TTL、空闲超时和服务端容量限制；退出会立即撤销当前会话。
- 页面启用 CSP、`frame-ancestors 'none'`、`X-Frame-Options: DENY`、MIME sniff 防护、严格 Referrer 与 Permissions Policy。
- 密钥字段只显示 `set`、`empty` 或 `missing` 状态，新值只发送到服务端，不会从配置 API 回显。
- 服务令牌不能访问后台管理接口，也不能借助自定义 Header 提升为管理员。
- 管理员审计不保存密码、Cookie、CSRF、请求 Header、配置值、RAG/Memory 正文或对话消息。

默认绝对 TTL 为 8 小时、空闲超时为 30 分钟，可通过以下配置调整：

```env
ROLEPLAY_ADMIN_SESSION_TTL_SECONDS=28800
ROLEPLAY_ADMIN_SESSION_IDLE_SECONDS=1800
ROLEPLAY_ADMIN_COOKIE_SECURE=true
```

当前认证模型是单一部署管理员密码，不包含多用户账号、RBAC、SSO 或 MFA。需要多人运维时，应把后台限制在 VPN/内网或身份感知代理之后，并在入口增加组织级 SSO/MFA；不要把单一管理员密码直接共享给大量开发者。

## 生产部署门禁

监听非 loopback 地址时，服务拒绝以下不安全配置：

- `ROLEPLAY_API_KEY` 少于 32 字符或仍是示例占位值。
- `ROLEPLAY_ADMIN_COOKIE_SECURE=false`。

生产环境还应满足：

1. 只通过 HTTPS 反向代理暴露 `/admin/` 和管理 API。
2. 使用密码管理器保存管理员密码，使用 Secret Manager 保存服务令牌和 Provider 密钥。
3. 精确配置 `ROLEPLAY_CORS_ORIGINS`，不要使用通配 Origin。
4. 限制后台来源网络，并由反向代理按可信链解析的真实客户端 IP，为 `/v1/admin/login` 设置请求体、连接数和速率限制；应用内限流只看到 TCP 对端地址。
5. 定期备份 `.data/access-tokens.sqlite3`、Session/Memory SQLite、Persona 目录和 RAG 持久化目录。
6. 定期查看“安全审计”和“用量分析”，对异常登录、错误率或 Token 激增执行轮换和吊销。

## 数据持久化提示

后台直接管理当前运行时 Provider 的真实数据：

- `ACCESS_TOKEN_SQLITE_PATH` 同时保存服务令牌、用量日志和管理员审计。
- `SESSION_PROVIDER=sqlite|postgres` 时会话可跨进程重启保留；`memory` Provider 重启即清空。
- `MEMORY_PROVIDER=sqlite` 时长期记忆持久化；`memory` Provider 重启即清空。
- RAG 是否持久化取决于当前 Provider。本地纯内存 Provider 重启会丢失文档，FAISS、Chroma、Qdrant 等按各自配置持久化。

执行删除前，后台会显示 App、用户或资源 ID 并进行二次确认。仍建议先确认备份和 Provider 的恢复方式。

## 管理 API 与脚本

浏览器后台使用安全会话；自动化脚本仍可通过 `Authorization: Bearer <ROLEPLAY_API_KEY>` 调用同一管理 API。正式接口清单见 [接口参考](interface-reference.md)。脚本中不要把管理员密钥写入命令历史、仓库、URL 或日志。
