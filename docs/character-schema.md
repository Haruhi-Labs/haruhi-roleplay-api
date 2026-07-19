# Character Schema

## 文档位置

角色字段的公开说明写在本文档中。

- 代码定义：`src/haruhi_roleplay_api/domain/persona.py`
- 本地配置示例：`personas/<character_id>/*.json`
- SOS 团设定规范：`docs/persona-design.md`
- 前端 catalog 接入：`docs/usage/frontend-integration.md`
- 接口字段参考：`docs/usage/interface-reference.md`

## 设计目标

角色配置分为两层：

- `CharacterProfile`：角色 catalog 入口，描述“这个角色是谁、有哪些可选模式”。
- `PersonaPreset`：具体角色扮演模式，描述“这一次要怎样扮演这个角色”。

这样做的目的，是让前端只选择 `characterId` 和 `personaMode`，后端在本项目中读取对应 preset，再把身份、语气、知识边界、RAG 策略、记忆策略统一交给 Orchestrator 和 PromptBuilder。

## CharacterProfile

`CharacterProfile` 对应 `personas/<character_id>/character.json`。

| 字段                    | 类型     | 含义                                                              |
| ----------------------- | -------- | ----------------------------------------------------------------- |
| `characterId`           | string   | 稳定角色 ID。用于 API 参数、RAG metadata、memory scope 和目录名。 |
| `displayName`           | string   | 前端展示名。只用于展示，不用于逻辑判断。                          |
| `description`           | string   | 角色目录摘要，仅供前端和后台展示，不进入模型提示词。              |
| `defaultPersonaMode`    | string   | 默认 preset。前端未指定 `personaMode` 时使用。                    |
| `availablePersonaModes` | string[] | 当前角色可被选择的 preset 列表。`defaultPersonaMode` 必须在其中。 |
| `tags`                  | string[] | 前端筛选和分类标签，例如 `haruhi`、`sos-brigade`、`student`。     |
| `visibility`            | string   | catalog 可见性，取值见 `Visibility`。                             |

## PersonaPreset

`PersonaPreset` 对应 `personas/<character_id>/<persona_mode>.json`。

| 字段                 | 类型     | 含义                                                               |
| -------------------- | -------- | ------------------------------------------------------------------ |
| `characterId`        | string   | 所属角色 ID，必须和角色目录一致。                                  |
| `personaMode`        | string   | preset ID。前端通过它选择角色模式。                                |
| `displayName`        | string   | preset 展示名，例如“中后期的春日”。                                |
| `description`        | string   | preset 简短说明，用于前端展示和后台审核。                          |
| `timeline`           | string   | 当前 preset 所在时间线，用于 RAG filter 和知识边界判断。           |
| `identity`           | object   | 角色身份配置，见 `IdentityConfig`。                                |
| `tone`               | object   | 语气和行为强度配置，见 `ToneConfig`。                              |
| `speechStyle`        | string[] | 表达方式标签，例如“直接”“吐槽”“克制”。不能写成长段原作台词。       |
| `behaviorRules`      | string[] | 允许和鼓励的角色行为规则，会进入 prompt。                          |
| `forbiddenBehaviors` | string[] | 禁止行为，例如泄露系统提示、复刻长段原作文本、越过时间线知识边界。 |
| `knowledgeBoundary`  | object   | 知识范围配置，见 `KnowledgeBoundary`。                             |
| `ragPolicy`          | object   | RAG 默认策略，控制是否默认检索以及允许的资料类型。                 |
| `memoryPolicy`       | object   | 记忆默认策略，控制是否默认使用长期记忆以及允许的记忆类型。         |
| `safetyPolicy`       | object   | 安全策略，例如阻止 prompt 泄露和长段版权文本复刻。                 |
| `visibility`         | string   | preset 可见性，取值见 `Visibility`。                               |

## IdentityConfig

`identity` 描述角色“为什么这样行动”，不是语气强度。

| 字段          | 类型     | 含义                                                                                     |
| ------------- | -------- | ---------------------------------------------------------------------------------------- |
| `role`        | string   | 角色身份，例如 `SOS 团团长`、`SOS 团成员`。                                              |
| `description` | string   | 身份说明，描述角色在对话中的基本立场。                                                   |
| `coreDrives`  | string[] | 核心动机，例如“寻找异常”“维持常识”“保护日常”。PromptBuilder 会用它约束角色长期行为方向。 |

## ToneConfig

`tone` 是一组 0 到 1 的数值，用来描述语气和行为倾向。它不是模型参数，也不等同于 `temperature`。

| 字段            | 范围 | 含义                                                                       |
| --------------- | ---- | -------------------------------------------------------------------------- |
| `energy`        | 0..1 | 表达和行动能量。越高越主动、节奏越快。                                     |
| `assertiveness` | 0..1 | 主导性。越高越容易推动话题、安排行动、做决定。                             |
| `warmth`        | 0..1 | 亲和度。越高越照顾对方情绪，越低越冷静或疏离。                             |
| `directness`    | 0..1 | 表达直接程度。越高越少绕弯，越低越含蓄或迂回。                             |
| `randomness`    | 0..1 | 跳跃感和不可预测性。越高越容易提出突然的想法，但仍要受角色和安全边界约束。 |

示例判断：

- 春日通常 `energy` 和 `assertiveness` 较高。
- 阿虚通常 `randomness` 较低，`directness` 可以较高。
- 朝比奈学姐可以降低 `assertiveness`，提高 `warmth`。

## KnowledgeBoundary

`knowledgeBoundary` 决定这个 preset 可以知道什么。它会影响 RAG filter，也会进入 prompt，避免角色越过当前时间线。

| 字段                 | 类型     | 含义                                                                           |
| -------------------- | -------- | ------------------------------------------------------------------------------ |
| `allowedTimelines`   | string[] | 允许使用的时间线。`timeline` 必须在这个列表里。                                |
| `forbiddenTimelines` | string[] | 明确禁止引用的时间线。用于阻止跨阶段剧透。                                     |
| `spoilerLevel`       | integer  | 当前 preset 可接受的剧透等级。数字越高，允许的信息越敏感。当前要求不能小于 0。 |

内置 SOS 团 preset 使用 `melancholy`、`sigh`、`endless_eight`、`disappearance`、`mid_late` 和 `surprise` 六个时间线。具体篇章含义和视角差异见 [SOS 团角色设定设计说明](persona-design.md)。

## Policy Fields

### ragPolicy

RAG 策略控制“是否默认检索资料”和“能检索哪些资料”。

| 字段               | 类型     | 含义                                                                       |
| ------------------ | -------- | -------------------------------------------------------------------------- |
| `enabledByDefault` | boolean  | 当前 preset 是否默认启用 RAG。前端仍可通过 capabilities 覆盖。             |
| `sourceTypes`      | string[] | 允许检索的资料类型，例如 `character_profile`、`timeline`、`relationship`。 |

### memoryPolicy

记忆策略控制“是否默认使用长期记忆”和“能使用哪些记忆”。

| 字段               | 类型     | 含义                                                                                |
| ------------------ | -------- | ----------------------------------------------------------------------------------- |
| `enabledByDefault` | boolean  | 当前 preset 是否默认启用 memory。前端仍可通过 capabilities 覆盖。                   |
| `allowedTypes`     | string[] | 允许读取或写入的记忆类型，例如 `user_preference`、`relationship`、`roleplay_fact`。 |

### safetyPolicy

安全策略控制角色扮演的硬边界。

| 字段                     | 类型    | 含义                                     |
| ------------------------ | ------- | ---------------------------------------- |
| `blockPromptLeak`        | boolean | 禁止输出系统提示、内部规则和隐藏上下文。 |
| `blockLongCopyrightText` | boolean | 禁止复刻长段受版权保护文本。             |

## Visibility

`visibility` 控制角色或 preset 是否暴露给普通 catalog。

| 值        | 含义                                      |
| --------- | ----------------------------------------- |
| `public`  | 可出现在前端 catalog 中，普通用户可选择。 |
| `private` | 内部可用，不应暴露给普通 catalog。        |
| `draft`   | 草稿或测试状态，不应暴露给普通 catalog。  |

## 新增角色建议

新增角色时，不要复制某个已有角色的 `tone` 作为默认模板。推荐顺序：

1. 先写 `CharacterProfile`，确定 `characterId` 和可用 preset。
2. 再为每个 preset 写 `identity`，明确角色身份和核心动机。
3. 再写 `tone`，把性格差异转换成 0..1 的可审核参数。
4. 再写 `speechStyle`、`behaviorRules` 和 `forbiddenBehaviors`。
5. 最后写 `knowledgeBoundary`、`ragPolicy`、`memoryPolicy` 和 `safetyPolicy`。

同一篇章的不同角色不能机械复制 `allowedTimelines`。例如《消失》中只有阿虚保留原世界记忆，其他四名角色必须限制为改写世界视角。
