# 凉宫小说角色扮演 RAG 语料

本项目不把整卷小说直接塞入向量库。离线流水线会把 13 卷中文文本清洗成短记录，再按时间线、角色视角、资料类型和标注来源写入 JSONL；运行时仍复用现有的 `app_id`、`character_id`、`timeline`、`spoiler_level` 和 `source_type` 过滤。

## 设计依据

[ChatHaruhi](https://github.com/LC1332/Chat-Haruhi-Suzumiya) 已验证“带标题的经典短场景 + 角色台词脚本”比整部脚本直接入库更适合角色扮演；其论文也报告了角色记忆检索对演绎效果的提升（[论文](https://arxiv.org/abs/2308.09597)）。本流水线沿用短场景思想，但补上了原项目欠缺的时间线和角色视角边界。

[REVERIEMEM](https://arxiv.org/abs/2606.25632) 把长篇小说角色记忆区分为情节、可见事实和情境化人格材料，并强调角色不能读取其视角之外的事实。本项目因此只把完整第一人称场景分配给叙述者阿虚；其他角色主要读取经明确归因的本人台词和外部行为观察。行为观察会在 prompt 中明确标成“演绎参考，而非角色亲历事实”。

向量文本会连同作品名、篇章名、记录类型和视角一起嵌入，这对应 [Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval) 的上下文化分块思路。Qdrant 查询会先按角色、时间线、剧透等级和资料类型做 payload 过滤；这些字段也是 [Qdrant 官方过滤文档](https://qdrant.tech/documentation/search/filtering/) 建议用于无法由向量表达的业务约束。若后续数据量继续增大，可按 [Qdrant 混合检索](https://qdrant.tech/documentation/search/text-search/hybrid-search/) 增加 sparse/BM25 和 rerank。

## 产物结构

每条 `records.jsonl` 记录都可直接转换成项目的 `RagIngestInput`：

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

每次正式构建后运行生产审计：

```bash
python scripts/audit_haruhi_corpus.py
```

审计会全量检查版本一致性、ID/正文去重、路由字段与知识归属、非台本说明头、760 字上限，以及结构化台词的目标回答完整性、最多两轮历史、无未来台词、无未知说话人和相邻发言不超过 5 个正文段落。报告写入未跟踪的 `.data/rag-corpus/haruhi/production-audit.json`；存在任何错误时脚本以非零状态退出，可直接作为发布前门禁。

## 当前生成快照

本次对 13 卷、87 个篇章中的全部 15,596 个引语 span 完成了 Luna 首审；4,750 个风险/抽样 span 被选入 Sol，因同一正文行的关联 span 一并复核，Sol 实际覆盖 5,143 个。最终生成 10,588 条目标角色台词记录，其中 10,258 条为 `certain`、330 条为 `probable`：春日 3,139、阿虚 2,822、朝比奈 1,275、长门 809、古泉 2,543。

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

输出包括：

- `.data/rag-corpus/haruhi/records.jsonl`：可装载记录；
- `.data/rag-corpus/haruhi/manifest.json`：源文件 SHA-256、各角色/类型/时间线数量、台词归因率与质量告警。

流水线会统一 UTF-8/UTF-16、繁转简、换行和空白，删除录入站点信息、插图占位、`chapter/chp/pic` 控制词、后记及参考文献。质量门会检查 13 卷覆盖、ID 唯一性、角色覆盖、记录长度和站点污染；失败时不会留下一个表面成功的产物。

原始文本附带个人学习用途和禁止转载声明，因此生成文件放在已被 `.gitignore` 排除的 `.data` 下。不要把原文或衍生 JSONL 提交到公开仓库；代码、显式篇章映射和质量统计可以版本管理。

## 接入运行时

纯内存 `local` provider 必须随进程启动装载，否则脚本结束后数据就会消失：

```dotenv
RAG_API_TYPE=local
RAG_CHUNK_SIZE=700
RAG_MIN_RELEVANCE_SCORE=0.2
RAG_BOOTSTRAP_CORPUS_PATH=.data/rag-corpus/haruhi/records.jsonl
RAG_BOOTSTRAP_APP_ID=web-demo
```

`RAG_BOOTSTRAP_APP_ID` 必须与业务请求及服务令牌绑定的 `app_id` 一致，避免跨应用泄漏。当前 `frontend-demo` 默认使用 `web-demo`。

对 Chroma 或 Qdrant，可在配置好 provider 与 embedding 后执行一次持久化导入：

```bash
python scripts/ingest_haruhi_corpus.py --app-id web-demo
```

持久化 provider 完成导入后应取消 `RAG_BOOTSTRAP_CORPUS_PATH`，避免每次启动重复计算 embedding。生产 Qdrant 和一次性持久化导入现在会硬性拒绝内置 hash embedding；必须配置真实中文/多语 embedding、模型和正确维度。只有明确的非生产测试才能给旧导入脚本传 `--allow-test-embedding`，或设置 `RAG_ALLOW_TEST_EMBEDDING=true`。该例外不要进入生产配置。

生产 Qdrant 不要把运行时直接绑定到某个物理集合。配置稳定 alias（例如 `RAG_INDEX=haruhi_rag_live`），再通过发布脚本创建带 `corpus_version` 的新集合。脚本会先创建所有过滤字段及中文全文 payload index，导入后核对指定 `app_id` 的精确 point 数，只有计数一致才原子切换 alias：

发布默认以 64 条为一批调用 embedding API 并批量 upsert Qdrant，可通过 `QDRANT_INGEST_BATCH_SIZE` 调整。批处理只减少网络往返，不合并语料记录：JSONL 仍严格保持一条记录对应一个 point，也不会调用生成模型。

建议同时开启 `QDRANT_HYBRID_SEARCH=true`。此模式并行取得 dense 向量候选和 `multilingual` 全文候选，用 RRF 合并后再执行本地字符重排、去重和类型配额。它不调用 LLM，不增加生成 Token；主要用于补回七夕、雪山症候群等专名被向量召回漏掉的记录。需要兼容未创建 `content` 全文索引的旧集合时保持关闭，完成版本化发布后再开启。

聊天编排会在模型提示词前应用 `RAG_MIN_RELEVANCE_SCORE`，默认 `0.2`；低于阈值时允许返回空召回，不会为了凑满 Top-K 注入无关桥段。Qdrant 混合检索会用内部保留的 dense 相似度或词面覆盖作为门禁依据，而不是把 RRF 排名分数误当相关度。该默认值只是安全起点，生产值必须用包含“应召回”和“应不召回”的自然多轮对话金标集校准。

```bash
python scripts/publish_haruhi_qdrant.py publish --app-id web-demo
```

发布输出会记录“上一个集合”。需要回滚时直接把 alias 切回该集合，不需要重新计算 embedding：

```bash
python scripts/publish_haruhi_qdrant.py activate \
  --collection haruhi_rag_live__haruhi-rag-上一版本
```

旧集合默认保留。确认观察期结束后才能显式删除；脚本拒绝删除仍被任何 alias 引用的集合，并要求重复输入集合名：

```bash
python scripts/publish_haruhi_qdrant.py delete \
  --collection haruhi_rag_live__haruhi-rag-旧版本 \
  --confirm haruhi_rag_live__haruhi-rag-旧版本
```

## 验收建议

先生成 300 条按“记录类型 × 角色 × 时间线”分层的人工金标模板：

```bash
python scripts/build_haruhi_retrieval_gold.py
```

模板位于未跟踪的 `.data/rag-eval/haruhi/gold-template.jsonl`，格式遵循 `schemas/haruhi-rag-eval-v1.schema.json`。标注人需要阅读 `annotation.source_preview`，写出不照抄原句、真实用户可能提出的 `query`，确认相关文档后把 `status` 从 `pending` 改为 `ready`。模型自动生成的问题只能用于 smoke test，不能代替人工金标。

把完成标注的文件保存为 `.data/rag-eval/haruhi/gold.jsonl`，在生产同款 embedding 和 Qdrant alias 上执行：

```bash
python scripts/evaluate_haruhi_rag.py --app-id web-demo
```

默认发布门槛为用例通过率不低于 90%、MRR 不低于 0.50，且 `app_id`、角色、时间线、剧透等级和 persona 隔离失败必须为 0。报告同时给出平均 Recall@K、逐用例命中文档与失败原因，写入 `.data/rag-eval/haruhi/report.json`。这一步必须使用生产 embedding；hash embedding 已被 Qdrant 门禁拒绝。

至少覆盖以下查询组，并分别以五名角色和各篇章 persona 验证结果：

- 具体事件：七夕、孤岛、漫无止境的八月、电脑游戏、雪山、入团考试；
- 角色关系：春日如何对阿虚表达在意、长门何时主动选择、实玖瑠的任务边界、古泉如何区分推测与事实；
- 话风：命令、拒绝、解释、安慰、遇到异常时的反应；
- 越界反例：《忧郁》春日不能检索《消失》或《惊愕》，改写世界角色不能读取原世界秘密；
- 视角反例：非阿虚角色不能把 `behavior_observation` 中的阿虚心理当成自己知道的事实。

当前检索会把记录类型、视角和置信度一并写进系统上下文，并明确要求模型在资料与 persona 边界冲突时舍弃资料。

聊天检索查询不是只发送最后一句用户输入，而是确定性加入目标角色、persona 模式、当前时间线和最近 6 条会话消息。整个查询受 4,000 字上限约束：优先移除最旧历史，单条超长消息保留首尾并标记中间省略，因此不会额外调用模型或消耗查询改写 Token。

所有 provider 的候选结果会经过统一的轻量重排：`0.80 × 原始相关度 + 0.15 × 中文字符/二元组覆盖 + 0.05 × 审阅质量`。选择阶段先按 `dialogue_example≤2`、`scene_memory≤2`、`behavior_observation≤1`、`inner_monologue≤1` 的软配额取结果，并限制同一 `scene_id` 最多一条；候选不足时依次放宽类型配额和场景限制。相同文档或规范化正文始终去重。该过程全部在本地完成，不调用生成模型。

进入生成提示词时，检索结果会再次按用途分成“原作事实与角色记忆”“目标角色台词与应对范例”“内心语气与外部行为观察”三段，并明确规定角色设定与时间线边界的权威高于检索事实，检索事实又高于风格范例。`style_only` 资料不能新增角色知识，阿虚持有的行为观察也不能变成被观察角色的内心事实。
