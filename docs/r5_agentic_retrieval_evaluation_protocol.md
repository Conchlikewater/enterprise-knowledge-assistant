# R5 受限 Agentic Retrieval 评测协议

> 状态：**2026-09-05 预注册完成，仅协议设计，未实现、未运行 Agent，也没有实验结果。**
> 上位规则：`docs/r_protocol.md` 与《2026 年 9 月 双项目升级执行协议 v6》。

## 1. 本阶段到底交付什么

R5 只回答一个实验设计问题：未来若实现两轮 Agentic Retrieval，怎样公平判断它的收益来自“第二轮检索策略”，而不是单纯多取了证据？

本阶段交付：

- Dense Top-5、Dense Top-10、Agentic 5×2 三组对照协议；
- 可回放的 step-level trajectory 字段和排序、去重、预算规则；
- Agent failure taxonomy 与四类 adversarial case；
- 指标、归因方法、运行有效性和报告边界；
- 机器可校验的协议清单 `evaluation/agentic_retrieval_protocol.json`。

本阶段**不交付**：

- Agent、规划器、第二轮查询生成器或工具调用实现；
- `app/` 内的 Agent API、Investigation、LangGraph、Draft、Approval 或 HITL；
- Agent 专用标注题集、固定轨迹 fixture、在线 Provider 运行或实验结果；
- R6/R7 的实现与对照实验。

所以 R5 完成后唯一安全表述是：

> 设计并冻结了受限 Agentic Retrieval 的三组公平对照、轨迹记录、失败分类和对抗测试协议。

不能表述为“实现了 Agent”“跑完了 Agent 评测”或“Agent 优于 Dense”。

## 2. 与当前系统的关系

当前生产回答链路仍是 Dense Retrieval，Agent 没有进入 `app/` 或任何生产 API。未来实验代码若获批，只能放在 `evaluation/` 或 `experiments/`，并继续调用现有检索边界，而不是复制或替换生产检索服务。

当前 `evaluation/questions.json` 有 50 道题，`evaluation/corpus_sources.json` 有 10 份合成文档。这些数据已经支持证据召回、MRR、回答/拒答等 RAG 评测，但尚未标注：

- 是否应进入第二轮；
- 期望停止原因；
- 可接受的第二轮查询意图；
- step-level failure；
- adversarial case 的安全行为。

因此它们只是未来 Agent 实验题集的**候选来源**，不能在 R5 被称为已经冻结的 Agent 题集。R6/R7 若在十月获批，必须先生成独立、版本化的 Agent 标注清单，并在任何真实运行前冻结。

## 3. 三组对照

| 对照臂 | 逻辑检索轮次 | 每轮返回上限 | 总返回预算 | 作用 |
| --- | ---: | ---: | ---: | --- |
| Dense Top-5 | 1 | 5 | 5 | 当前生产检索预算基线 |
| Dense Top-10 | 1 | 10 | 10 | 控制“只是多取 5 条证据”的混杂因素 |
| Agentic 5×2 | 最多 2 | 5 | 10 | 测试第二轮决策、查询改写和停止行为 |

必须同时保留三组。只比较 Dense Top-5 与 Agentic 5×2，会把“预算从 5 增到 10”和“Agent 策略”混在一起；只有 Agentic 相对预算匹配的 Dense Top-10 仍有可解释差异时，才可能讨论策略价值。

Agentic 5×2 的预算约束是全局约束：

- 一轮只允许一次知识库检索调用；
- 整个问题最多两次检索调用，不是每个子问题各两次；
- 每次最多返回 5 条，第二轮重复项仍占该次返回名额，不补查第三次；
- 两轮合并后按 `chunk_id` 去重，最终唯一候选最多 10 条；
- 超过两轮、第三次检索或通过拆分工具绕过预算，都记为 `LOOP_LIMIT_BREACH`。

## 4. 公平性与允许差异

三个对照臂必须固定相同的：

1. 文档版本与允许的 `document_ids`；
2. 题目 ID、题面和人工 gold evidence；
3. Embedding Provider、模型、维度和配置；
4. 最终回答生成 Provider 与模型；
5. 温度及其他采样参数；
6. 最终回答 Prompt 的版本与哈希；
7. Evidence/Citation 输入格式。

允许不同的只有：

- 检索策略和候选预算；
- Agentic 臂独有的规划/第二轮决策 Prompt；
- 因第二轮产生的额外模型调用、token、成本和延迟。

规划 Prompt 不强求与 Dense 相同，因为 Dense 不需要规划。它必须单独版本化并记录哈希；其所有成本只能计入 Agentic 臂，不能从报告中隐藏。

三个对照臂必须在同一冻结题集上运行。不得为某一臂删除坏例、替换文档或单独调整最终回答 Prompt。

## 5. 候选排序、合并与去重

为了让 Recall 和 MRR 可重复计算，排序规则固定为：

1. 每次检索先按向量分数降序；分数相同用 `chunk_id` 升序打破平局；
2. Dense Top-5/Top-10 直接使用该单轮顺序；
3. Agentic 先保留第一轮顺序，再追加第二轮中首次出现的 Chunk；
4. 跨轮重复的 `chunk_id` 不再次进入最终列表，但保留在原始 trajectory 中；
5. MRR 使用上述最终首次出现顺序，不能按事后 gold 相关性重排。

该规则不是生产 Agent 算法，只是未来对照实验的统一计分顺序。

## 6. Step-level trajectory 契约

未来每个“题目 × 对照臂 × 重复轮次”产生一条只追加的运行记录。至少包含：

### 6.1 运行身份与冻结配置

- `run_id`、`protocol_version`、`execution_mode`；
- `question_id`、`arm_id`、`allowed_document_ids`；
- dataset/corpus/config 版本与哈希；
- Embedding、规划 Prompt、最终回答 Prompt、生成模型和 Evidence 格式版本；
- 起止时间、总延迟、token、估算成本与错误码。

### 6.2 每轮检索

- `round_index`；
- 实际 query；
- 请求的 `document_ids`；
- 每个返回项的 `rank / chunk_id / document_id / score`；
- 原始返回数、去重后新增数、gold evidence 命中；
- 检索延迟与工具结果状态；
- 是否请求第二轮、决定理由与停止原因。

### 6.3 最终结果

- 最终首次出现顺序的唯一 Evidence；
- `answer / refuse / error` 行为；
- Citation 与 claim-evidence 映射；
- primary failure 和 secondary failures；
- adversarial case（若有）及预期是否满足。

trajectory 不保存 API Key、完整私密文档、无必要的完整 Prompt 或生产用户数据。Prompt 正文由版本化文件管理，轨迹只保存版本和哈希。

## 7. 停止原因

停止原因与 failure 是两个维度：安全停止可以不是失败；例如工具超时后有界终止，是依赖故障但不是无限循环。

| 代码 | 适用场景 |
| --- | --- |
| `BASELINE_SINGLE_ROUND` | Dense 基线完成固定的一轮检索 |
| `SUFFICIENT_EVIDENCE` | Agentic 在预算内判断证据充分 |
| `NO_NEW_EVIDENCE` | 第二轮没有新增唯一证据 |
| `MAX_ROUNDS_REACHED` | 已使用两轮，不能继续检索 |
| `RETRIEVAL_EMPTY` | 没有证据且没有安全、不同的第二轮查询可用 |
| `EVIDENCE_CONFLICT` | 冲突证据无法在现有材料中安全消解 |
| `TOOL_TIMEOUT` | 检索工具超时并按有界策略终止 |
| `TOOL_OUTPUT_INVALID` | 工具输出无法通过严格 Schema 校验 |
| `SCOPE_VIOLATION` | 请求或结果越出顶层文档范围 |
| `PLANNER_OUTPUT_INVALID` | 规划输出在至多一次受控修复后仍无效 |

每条 Agentic 轨迹必须有且只有一个最终停止原因。Dense 基线固定为 `BASELINE_SINGLE_ROUND`。

## 8. Agent failure taxonomy

一次运行可以有一个 primary failure 和多个 secondary failure，但同一事实不能重复计数。至少冻结以下分类：

| 失败代码 | 可观察判定 | 面试中对应的问题 |
| --- | --- | --- |
| `WRONG_TOOL_SELECTION` | 调用了知识库检索以外的工具，或调用不存在/未授权工具 | 工具白名单和最小权限 |
| `PARAMETER_EXTRACTION_ERROR` | query 为空、字段无效，或传入的范围无法解析 | 结构化输出与参数校验 |
| `SCOPE_VIOLATION` | 请求或返回包含允许范围外的文档 | RAG 文档范围隔离 |
| `LOOP_LIMIT_BREACH` | 超过两次检索、出现第三轮，或未在预算内终止 | 有界 Agent 与成本控制 |
| `PREMATURE_TERMINATION` | gold 标注要求第二轮且第一轮证据不足，却提前给出终态 | 停止策略是否过早 |
| `UNSUPPORTED_SUMMARY` | 没有充分 Evidence 仍回答，或 claim 没有支持它的 Citation | 幻觉与证据约束 |
| `CONFLICT_SUPPRESSION` | 检索到相互冲突证据却静默丢弃一方并给出确定结论 | 冲突证据处理 |
| `UNHANDLED_TOOL_ERROR` | 空结果、超时或非法格式导致崩溃、无限重试或无安全终态 | 工具失败的降级路径 |

“模型回答不好”不是足够精确的失败分类。每个失败必须能由 trajectory 字段和人工 gold 共同复核。

## 9. Adversarial cases

未来冻结题集必须至少包含以下四类。这里冻结行为约束，不宣称测试已经运行。

| 场景 | 必须观察 | 安全期望 |
| --- | --- | --- |
| 工具返回空 | 轮次、第二轮决策、最终行为 | 若有不同且受控的查询可做第二轮；仍为空则拒答，不编造总结 |
| Evidence 相互矛盾 | 两方 Evidence 是否都保留、最终 claim | 明确冲突或拒答，不静默选择有利一方 |
| 工具超时 | 超时码、尝试数、停止原因 | 有界终止，不无限重试，不伪造工具结果 |
| 工具返回非法格式 | Schema 错误、修复次数、停止原因 | 最多一次受控格式修复；仍失败则安全终止 |

所有场景仍受两次检索上限约束。格式修复是结构化输出修复，不额外增加检索预算，但其模型调用、token、成本和延迟必须记录。

## 10. 指标与归因

### 10.1 检索质量

对三个对照臂使用同一 gold evidence：

```text
Evidence Recall@K = 最终唯一候选命中的 gold Evidence 数 / gold Evidence 总数
RR = 1 / 第一个 gold Evidence 的最终排名；无命中时为 0
MRR = 所有可评分题 RR 的平均值
```

同时报告题目总数、可评分分母、按题型结果、最终唯一候选数和实际检索调用次数。

### 10.2 第二轮归因

令 `A` 为第一轮 `chunk_id` 集合，`B` 为第二轮 `chunk_id` 集合：

```text
Jaccard(A, B) = |A ∩ B| / |A ∪ B|；A、B 都为空时定义为 1
replacement_ratio = |B - A| / max(1, |B|)
new_gold_evidence = |(B - A) ∩ Gold|
```

- Jaccard 高、替换率低：第二轮大多重复第一轮；
- 替换率高但 `new_gold_evidence=0`：第二轮改变了结果，却未找到更多有效证据；
- Agentic 相对 Top-5 提升、但不优于 Top-10：主要证据是预算收益，不能归因为 Agent 策略；
- Agentic 相对 Top-10 仍提升，且出现新增 gold Evidence：才有讨论策略收益的依据，但仍须结合成本、延迟和失败率。

### 10.3 行为、安全与成本

至少报告：

- 第二轮触发准确率和混淆矩阵（仅对有该 gold 标注的题）；
- 停止原因准确率；
- failure taxonomy 各类计数、发生率和题目 ID；
- 文档范围越界次数和发生越界的任务数；
- answer/refuse/error 混淆矩阵；
- Citation identity、source/page、semantic support 与 claim completeness；
- 每臂检索次数、token、估算成本、平均延迟、P50/P95。

小样本必须展示分母和原始题目 ID，不能只给百分比。

## 11. 数据冻结与防止调参污染

R6/R7 若获批，必须在实现/运行前完成：

1. 从当前 50 题选择或新增适合多步检索的候选题；
2. 为每题标注允许文档、gold evidence、预期行为、是否应进入第二轮、期望停止原因和 adversarial 标签；
3. 把开发 fixtures 与最终评测题分开；
4. 只用开发 fixtures 调整 Prompt、Schema 和停止规则；
5. 冻结最终题集版本与哈希后，三个对照臂一次性使用同一版本；
6. 如因标注错误必须改题，增加数据集版本并让三个对照臂全部重跑。

R5 不预设题数，也不沿用归档旧 V3 的“24 题”作为既成事实。题数应由实际标注质量决定，并在未来预注册提交中写清分母。

## 12. CI、真实 Provider 与 Git 时序

R5 的 CI 只校验：

- 机器协议能被标准 JSON 解析；
- 三组预算、公平性字段、停止原因、失败分类和 adversarial case 不漂移；
- 协议明确 `agent_implemented=false`、`experiment_executed=false`；
- 当前 10 文档/50 题事实与清单一致。

R5 不新增 Agent 运行代码和固定轨迹，也不调用真实 Provider。

未来时序必须拆分：

1. R5 协议/Schema 预注册提交；
2. R6 实现与测试提交（十月、另行批准）；
3. R7 实验结果提交（十月、运行前再次批准真实 Provider 和预算）。

离线回放必须标记 `execution_mode=offline_replay`；真实模型运行必须标记 `execution_mode=real_provider`。任何在线命令都不得进入默认测试或 CI。

## 13. 未来实验的有效性与报告边界

以下任一情况发生，运行无效并应停止分析，不得补数据掩盖：

- 三组使用了不同题目、文档、Embedding 或最终回答配置；
- Agentic 超过两次检索或总返回预算 10；
- 运行中修改 Prompt、阈值或 gold 标注却不升版本；
- trajectory 缺失到无法复核第二轮决策或失败分类；
- 真实 Provider 运行没有用户预算授权；
- 只展示有利指标或隐藏 Top-10 对照。

未来结果必须注明：数据来自当前小规模合成企业文档及之后冻结的有限题集，只能说明该配置下的实验行为，不代表真实企业语料、生产安全或通用 Agent 能力。即使结果为正，也不能自动进入 `app/`；生产化需要新的范围、威胁模型、测试和用户批准。

## 14. R5 验收清单

- [x] 三组对照及预算冻结；
- [x] 七项跨臂固定条件与允许差异冻结；
- [x] 排序、合并、去重和两轮上限冻结；
- [x] step-level trajectory 字段冻结；
- [x] 停止原因、failure taxonomy 和 adversarial cases 冻结；
- [x] Evidence、MRR、Jaccard、替换率、成本和安全指标冻结；
- [x] 当前 50 题与未来 Agent 标注题集的边界写清；
- [x] CI/真实 Provider 和提交时序写清；
- [x] 无 Agent 实现、无在线运行、无结果结论。
