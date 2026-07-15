# 凉宫小说角色扮演 RAG 语料

本项目不把整卷小说直接塞入向量库。离线流水线会把 13 卷中文文本清洗成短记录，再按时间线、角色视角、资料类型和标注来源写入 JSONL；运行时仍复用现有的 `app_id`、`character_id`、`timeline`、`spoiler_level` 和 `source_type` 过滤。

## 设计依据

[ChatHaruhi](https://github.com/LC1332/Chat-Haruhi-Suzumiya) 已验证“带标题的经典短场景 + 角色台词脚本”比整部脚本直接入库更适合角色扮演；其论文也报告了角色记忆检索对演绎效果的提升（[论文](https://arxiv.org/abs/2308.09597)）。本流水线沿用短场景思想，但补上了原项目欠缺的时间线和角色视角边界。

[REVERIEMEM](https://arxiv.org/abs/2606.25632) 把长篇小说角色记忆区分为情节、可见事实和情境化人格材料，并强调角色不能读取其视角之外的事实。本项目因此只把完整第一人称场景分配给叙述者阿虚；其他角色主要读取经明确归因的本人台词和外部行为观察。行为观察会在 prompt 中明确标成“演绎参考，而非角色亲历事实”。

向量文本会连同作品名、篇章名、记录类型和视角一起嵌入，这对应 [Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval) 的上下文化分块思路。Qdrant 查询会先按角色、时间线、剧透等级和资料类型做 payload 过滤；这些字段也是 [Qdrant 官方过滤文档](https://qdrant.tech/documentation/search/filtering/) 建议用于无法由向量表达的业务约束。当前实现还支持 [Qdrant 混合检索](https://qdrant.tech/documentation/search/text-search/hybrid-search/) 和本地轻量 rerank。

## 产物结构

仓库直接追踪已经审计的正式发布包：

- `data/rag-corpus/haruhi/records.jsonl.gz`：17,041 条可直接装载的 gzip JSONL；
- `data/rag-corpus/haruhi/manifest.json`：语料版本、来源散列、数量和压缩产物散列；
- `data/rag-corpus/haruhi/production-audit.json`：最终生产审计结果。

Loader 会直接读取 `.jsonl.gz`，发布前不需要手工解压。原始小说、逐条审阅批次、候选文件、质量抽样和金标模板仍只留在被忽略的 `.data` 工作目录，不进入仓库。

导入器会给离线记录附加 `atomic_record=true`，Local、Chroma/Faiss 和 Qdrant provider 都会保持“一条 JSONL 记录对应一个检索 chunk”，不会再按通用文档的 `RAG_CHUNK_SIZE` 二次切开结构化台词或目标回答。通过管理 API 上传的普通长文档仍按原有规则分块。

正式记录遵循 [`schemas/haruhi-rag-record-v2.schema.json`](../schemas/haruhi-rag-record-v2.schema.json)。`record_kind`、`perspective`、`retrieval_channel`、`knowledge_owner`、`subject_character_id`、`usage` 和 `corpus_version` 同时位于 JSONL 顶层和 metadata；加载时两处不一致会直接失败。这样既保留现有 `RagDocumentMetadata.extra` 兼容性，也能在 Qdrant/Chroma payload 中扁平索引和过滤。

其中 `behavior_observation` 的 `knowledge_owner=kyon`、`subject_character_id=<被观察角色>`、`usage=style_only`，明确表示资料来自阿虚视角，只能校准目标角色的外显演绎；`dialogue_example` 使用 `retrieval_channel=dialogue_style`，不作为当前事件事实；`scene_memory` 才属于 `usage=knowledge`。每次确定性构建都会根据全部记录正文和元数据生成 `haruhi-rag-<digest>` 形式的 `corpus_version`，并写入 manifest 和每条记录。

| 记录类型 | 检索角色 | 用途 | 视角约束 |
|---|---|---|---|
| `scene_memory` | 阿虚 | 约 300～400 字的连续场景 | 阿虚第一人称经历 |
| `inner_monologue` | 阿虚 | 心理活动、判断和叙述语气 | 只属于阿虚 |
| `dialogue_example` | 被明确归因的说话人 | 台词、应对和相邻对话 | 只作说话/行为范例 |
| `behavior_observation` | 被观察角色 | 动作、表情、关系反应 | 外部观察，不等于角色知道观察者内心 |

自动说话人标注只接受以下证据：同段明确署名、以冒号引出下一句的明确主语，或台词后一段的明确“某人回答/说道”。不会凭口癖硬猜，也不会用长对话轮次强行交替；无法确认的台词保留在阿虚场景中，但不建立角色台词记录。所有记录都有 `confidence` 和原始行号，说话人归因记录还会保存 `attribution_reason`，便于人工抽查或覆盖。这一保守基线只归因了 13,703 个段首直接引语中的 1,534 个目标角色台词（11.19%），适合无模型构建，不代表完整台本覆盖。

## Agent 逐条台词审阅

完整台本模式会扫描正文中所有 `「」`、`『』`、`“”`、`‘’`，包括段中引语、同段多引语和嵌套引语。当前源文本共导出 14,641 个审阅单元、15,596 个引语 span；每个 span 都有稳定 ID、精确字符范围、父子嵌套关系、前后文、源文件 SHA-256 和旧规则结果。

审阅分两层：

1. `gpt-5.6-luna` 低推理完成全部 span 首审，分类为现场台词、心理话、文字、术语、标题、拟声、转述、表演或回放，并分别标注实际发声者与措辞所有者。
2. `gpt-5.6-sol` 只复核未确定项、目标角色 `probable` 台词、旧规则冲突、嵌套/配对异常，以及从其余常规项中按固定种子抽取的 5% 质量样本。

模型只看到批内短 ID，最终结果再由本地映射回稳定 span ID，以减少重复 token。每批结果都经过跨字段语义校验并原子写入，支持并发、失败重试和断点续跑。只允许自动修正可唯一确定的格式问题，例如把心理主体从 `speaker` 移到 `word_owner`，或把仅凭风格的 `certain` 降为 `probable`；人物身份冲突不会被本地代码擅自改写。

导出候选：

```bash
python scripts/export_haruhi_dialogue_review.py
```

Luna 全量首审：

```bash
python scripts/run_haruhi_dialogue_review.py \
  --model gpt-5.6-luna \
  --effort low \
  --batch-spans 80 \
  --workers 3
```

选择疑难项与确定性随机样本：

```bash
python scripts/select_haruhi_dialogue_adjudication.py
```

Sol 盲审复核（不向 Sol 提供 Luna 答案，降低一致性偏差）：

```bash
python scripts/run_haruhi_dialogue_review.py \
  --model gpt-5.6-sol \
  --effort medium \
  --prompt prompts/corpus/dialogue-adjudication-v1.md \
  --prompt-version dialogue-adjudication-prompt.v1 \
  --batch-prefix sol-v1 \
  --span-selection .data/rag-corpus/haruhi-review/adjudication_selection.txt \
  --output .data/rag-corpus/haruhi-review/reviews/sol \
  --batch-spans 60 \
  --workers 2
```

生成质量报告并构建最终 RAG 语料：

```bash
python scripts/report_haruhi_dialogue_review.py
uv run --with opencc-python-reimplemented python scripts/build_haruhi_corpus.py \
  --use-agent-review
```

最终构建会整体移除旧的自动 `dialogue_example`，以 Agent 审阅台词替换，不会新旧并存。只有 `current_scene`、目标五角色、`certain/probable` 且引号闭合的真实发言进入角色台本；心理话、术语、NPC 台词、转述和表演台词仍保留审阅结果，但不会污染目标角色话风。嵌套引用他人原话时，外层台词中的引用内容会被省略。

最终化阶段还会按“角色 + 记录类型 + 完整正文”确定性去重；同一检索文本若在原文不同位置重复出现，只保留置信度最高并优先经过 Sol 复核的一条，源 span 的审阅覆盖统计仍单独保留。

`dialogue_example` 使用 `roleplay-dialogue-example.v2` 结构：每条记录明确保存 `dialogue_scene_id`、`stimulus_turns` 和 `response_turn`。场景按篇章内相邻发言的正文段落距离确定；相邻发言超过 5 个段落时开始新的对话场景。生成用正文只包含同一场景中目标发言之前最近两轮已确认说话人的台词，不再加入未来台词；未知说话人不会进入刺激上下文。目标角色回答单独标记并优先占用长度预算，构建器只会整轮舍弃过长的前置上下文，绝不会静默截断目标台词。

`quality_report.json` 会报告 Luna 覆盖率、Luna/Sol 一致率、随机样本中的目标说话人精确率和召回率代理值，以及 Wilson 95% 区间。Sol 盲审复核是成本可控的模型质量代理，不等同于人工金标准确率；绝对准确率仍需要人类标注测试集。这里的“逐条”指全部引语 span，叙述性心理和行为段落仍由原有保守规则提取。

每次在 `.data` 重建后，先显式审计新的工作区产物：

```bash
python scripts/audit_haruhi_corpus.py \
  --corpus .data/rag-corpus/haruhi/records.jsonl \
  --manifest .data/rag-corpus/haruhi/manifest.json
```

审计会全量检查版本一致性、ID/正文去重、路由字段与知识归属、非台本说明头、760 字上限，以及结构化台词的目标回答完整性、最多两轮历史、无未来台词、无未知说话人和相邻发言不超过 5 个正文段落。省略参数时，脚本会复核仓库内置的压缩正式语料；Qdrant 发布也会在创建集合前强制执行同一审计。

## 当前生成快照

本次对 13 卷、87 个篇章中的全部 15,596 个引语 span 完成了 Luna 首审；4,750 个风险/抽样 span 被选入 Sol，因同一正文行的关联 span 一并复核，Sol 实际覆盖 5,143 个。审阅得到 10,588 条目标角色台词候选，其中 `certain` 10,258 条、`probable` 330 条；最终化去除 2 条完全重复记录后，正式索引包含 10,586 条 `dialogue_example`。全部正式记录共 17,041 条。

在 585 条常规确定性随机样本上，以不读取 Luna 答案的 Sol 盲审作为代理参照，目标说话人精确率代理为 94.84%（Wilson 95%：92.30%–96.57%），召回率代理为 94.61%（Wilson 95%：92.05%–96.38%）。该数字衡量的是双模型复核一致性代理，不应表述成人工金标准确率。整个 Sol 复核集的精确字段一致率为 59.81%，反映疑难项确实发生了较多改判；最终语料对这些 span 使用 Sol 结果。

时间线映射与 persona 一致：

| 小说范围 | timeline | spoiler level |
|---|---|---:|
| 《忧郁》 | `melancholy` | 1 |
| 《叹息》《烦闷》及《动摇》前两篇 | `sigh` | 2 |
| 《暴走·漫无止境的八月》 | `endless_eight` | 3 |
| 《消失》 | `disappearance` | 4 |
| 《暴走》其余篇、《动摇》后篇、《阴谋》《愤慨》 | `mid_late` | 5 |
| 《分裂》《惊愕》《直觉》《剧场》 | `surprise` | 6 |

《分裂／惊愕》的 α、β 分支会额外写入 `metadata.branch`。同一时间线内仍保留卷号、篇章和原始行号。

《消失》还会写入 `metadata.allowed_persona_modes`：第一至第三章中改写世界的普通人格资料只允许 `disappearance_*` persona；改写前、时间修复及恢复后的原世界资料只允许中后期/《惊愕》persona。这个二级过滤同时在本地、Chroma 和 Qdrant 路径生效，避免仅靠同一个 `disappearance` timeline 把原世界身份泄漏给普通人格。

## 构建

源文件默认从维护者本机的下列目录读取，不会复制进 Git：

```text
~/Downloads/【小説】涼宮春日系列/txt
```

执行：

```bash
uv run --with opencc-python-reimplemented python scripts/build_haruhi_corpus.py
```

也可显式指定路径：

```bash
uv run --with opencc-python-reimplemented python scripts/build_haruhi_corpus.py \
  --source "/path/to/novels/txt" \
  --output .data/rag-corpus/haruhi
```

本机构建工作区输出包括：

- `.data/rag-corpus/haruhi/records.jsonl`：可装载记录；
- `.data/rag-corpus/haruhi/manifest.json`：源文件 SHA-256、各角色/类型/时间线数量、台词归因率与质量告警。

流水线会统一 UTF-8/UTF-16、繁转简、换行和空白，删除录入站点信息、插图占位、`chapter/chp/pic` 控制词、后记及参考文献。质量门会检查 13 卷覆盖、ID 唯一性、角色覆盖、记录长度和站点污染；失败时不会留下一个表面成功的产物。

内部仓库只发布上述三个最终产物。原始文本、模型审阅输入输出、抽样集和构建缓存继续放在 `.data`，不得提交。更新正式语料时必须重新构建、全量审计并以确定性 gzip 生成新的版本化发布包。

## 接入运行时

纯内存或本地向量 provider 仅用于开发；需要时可直接装载仓库内置压缩语料：

```dotenv
RAG_API_TYPE=local
RAG_CHUNK_SIZE=700
RAG_MIN_RELEVANCE_SCORE=0.2
RAG_BOOTSTRAP_CORPUS_PATH=data/rag-corpus/haruhi/records.jsonl.gz
RAG_BOOTSTRAP_APP_ID=web-demo
```

`RAG_BOOTSTRAP_APP_ID` 必须与业务请求及服务令牌绑定的 `app_id` 一致，避免跨应用泄漏。当前 `frontend-demo` 默认使用 `web-demo`。

生产默认使用 Qdrant 和真实中文/多语 embedding。配置 provider 后直接运行发布命令；脚本默认读取仓库内置的 `records.jsonl.gz`：

```bash
python scripts/publish_haruhi_qdrant.py publish --app-id web-demo
```

生产 Qdrant 不应设置 `RAG_BOOTSTRAP_CORPUS_PATH`，避免每次启动重复计算 embedding。发布脚本会硬性拒绝内置 hash embedding；必须配置真实中文/多语 embedding、模型和正确维度。

生产 Qdrant 不要把运行时直接绑定到某个物理集合。配置稳定 alias（例如 `RAG_INDEX=haruhi_rag_live`），发布脚本会创建同时包含 `corpus_version` 和 embedding 配置指纹的新物理集合。任何已存在的目标集合都会在写入前被拒绝，确保发布过程不会逐点覆盖线上集合；语料审计、point 数和原子性检查全部通过后才切换 alias。

发布默认以 64 条为一批调用 embedding API 并批量 upsert Qdrant，可通过 `QDRANT_INGEST_BATCH_SIZE` 调整。批处理只减少网络往返，不合并语料记录：JSONL 仍严格保持一条记录对应一个 point，也不会调用生成模型。

建议同时开启 `QDRANT_HYBRID_SEARCH=true`。此模式并行取得 dense 向量候选和 `multilingual` 全文候选，用 RRF 合并后再执行本地字符重排、去重和类型配额。它不调用 LLM，不增加生成 Token；主要用于补回七夕、雪山症候群等专名被向量召回漏掉的记录。需要兼容未创建 `content` 全文索引的旧集合时保持关闭，完成版本化发布后再开启。

聊天编排会在模型提示词前应用 `RAG_MIN_RELEVANCE_SCORE`，默认 `0.2`；低于阈值时允许返回空召回，不会为了凑满 Top-K 注入无关桥段。Qdrant 混合检索会用内部保留的 dense 相似度或词面覆盖作为门禁依据，而不是把 RRF 排名分数误当相关度。该默认值是安全起点，生产环境按所选向量模型和真实请求抽样调整。

若同一个模型名背后的实际权重发生变化，显式提供新的发布标识以生成不同物理集合：

```bash
python scripts/publish_haruhi_qdrant.py publish \
  --app-id web-demo \
  --release-id bge-m3-2026-07
```

发布输出会记录“上一个集合”。需要回滚时直接把 alias 切回该集合，不需要重新计算 embedding：

```bash
python scripts/publish_haruhi_qdrant.py activate \
  --collection haruhi_rag_live__haruhi-rag-上一版本__emb-上一指纹
```

旧集合默认保留。确认观察期结束后才能显式删除；脚本拒绝删除仍被任何 alias 引用的集合，并要求重复输入集合名：

```bash
python scripts/publish_haruhi_qdrant.py delete \
  --collection haruhi_rag_live__haruhi-rag-旧版本__emb-旧指纹 \
  --confirm haruhi_rag_live__haruhi-rag-旧版本__emb-旧指纹
```

## 可选离线检索诊断

仓库保留人工样本模板和指标脚本，供以后比较 embedding 模型或做专项回归；它不是当前 Qdrant 发布的前置门槛，也不替代线上真实对话抽样。需要时可生成 300 条分层模板：

```bash
python scripts/build_haruhi_retrieval_gold.py
```

模板位于未跟踪的 `.data/rag-eval/haruhi/gold-template.jsonl`，格式遵循 `schemas/haruhi-rag-eval-v2.schema.json`。正例标注人需要阅读 `annotation.source_preview`，编写 2—4 条自然的 `conversation` 和一条 `current_input`，让对话可能联想到该互动桥段，但不能出现作品名、篇章名或照抄原句；还要补齐所有同样可接受的 `relevant_document_ids`。反例则编写普通寒暄、即时任务或全新话题，并保持 `maximum_retrieved_hits=0`。确认后把 `status` 从 `pending` 改为 `ready`。最终检索 query 由线上同一段确定性代码生成，模型自动生成的问题只能用于 smoke test，不能代替人工金标。

把完成标注的文件保存为 `.data/rag-eval/haruhi/gold.jsonl`，在生产同款 embedding 和 Qdrant alias 上执行：

```bash
python scripts/evaluate_haruhi_rag.py --app-id web-demo
```

该脚本报告 Recall@K、MRR、逐用例命中文档与隔离错误，适合诊断单个检索通道。当前生产验收以正式语料审计、真实 Qdrant 发布校验和上线后的对话抽样为准。

至少覆盖以下查询组，并分别以五名角色和各篇章 persona 验证结果：

- 自然桥段：用户拒绝普通活动、成员失约、临时比赛、误会、别扭关心、面对异常时的反应；
- 角色应对：命令、拒绝、解释、安慰、转移话题和邀请用户参与；
- 空召回：普通寒暄、实时业务问题和语料中没有对应关系模式的全新话题；
- 越界反例：《忧郁》春日不能检索《消失》或《惊愕》，改写世界角色不能读取原世界秘密；
- 视角反例：非阿虚角色不能把 `behavior_observation` 中的阿虚心理当成自己知道的事实。

记录类型、视角、置信度和审阅信息保留在 provider payload 与 API source 中用于路由和追溯，但不会写进模型可见的系统提示词。

聊天检索查询不是只发送最后一句用户输入，而是确定性加入目标角色、persona 模式、当前时间线和最近 6 条会话消息。整个查询受 4,000 字上限约束：优先移除最旧历史，单条超长消息保留首尾并标记中间省略，因此不会额外调用模型或消耗查询改写 Token。

所有 provider 的候选结果会经过统一的轻量重排：`0.80 × 原始相关度 + 0.15 × 中文字符/二元组覆盖 + 0.05 × 审阅质量`。选择阶段先按记录类型做软配额并限制同一 `scene_id` 最多一条；候选不足时再放宽。聊天最终最多注入 3 条目标角色应对素材和 2 条阿虚视角导演桥段；导演通道不足时 actor 素材可以回填。相同文档或规范化正文始终去重。该过程不调用生成模型。

进入生成提示词时，资料按用途分成“相似桥段”“补充背景”“角色应对范例”“动作与语气参考”。角色设定与时间线边界始终优先；导演桥段、`style_only` 资料和阿虚持有的行为观察都不能变成目标角色凭空知道的事实。提示词只保留自然语言正文，不显示文档 ID、评分、模型名或审阅方法。
