# V3 P0 Agent 决策契约

> 状态：阶段 0 候选冻结，具体阈值待固定 fixtures 校准；尚未实现。
> 目标：把两轮 Agent 的关键判断定义成确定、可单测、可离线回放的纯函数。

## 1. 设计原则

- Provider 和 Retrieval 负责产生结构化轨迹；
- 决策内核只读取结构化数据，不直接访问网络、数据库、文件或环境变量；
- 相同输入、相同 `DecisionConfig` 必须得到相同输出；
- 所有检索工具由服务端注入顶层 `allowed_document_ids`；
- 整个 Investigation 最多两个逻辑检索轮次；
- 每轮最多接纳 5 个全局去重候选，两轮总候选预算最多 10；
- “每轮 5 个”不是“每个子问题 5 个”。

## 2. 核心结构

### `Subquestion`

```text
subquestion_id
text
required: bool
target_document_ids: list[document_id] | null
```

`target_document_ids` 只能是顶层允许范围的子集。空值表示允许使用整个顶层范围。

### `EvidenceCandidate`

```text
chunk_id
document_id
page_number
filename
score
content_sha256
subquestion_ids
support_label: supports / contradicts / irrelevant / unknown
round_index: 1 / 2
```

### `DecisionConfig`

```text
config_version
per_round_candidate_budget = 5
max_rounds = 2
max_total_candidate_budget = 10
score_threshold
coverage_threshold
min_evidence_per_subquestion
```

阶段 0 冻结候选范围：

- `score_threshold`：`None / 0.20 / 0.25 / 0.30 / 0.35 / 0.40`；
- `coverage_threshold`：`0.60 / 0.75 / 1.00`；
- `min_evidence_per_subquestion`：`1 / 2`。

进入 Agent 实现前，使用固定开发 fixtures 选出一个版本化配置。旧实验中的 `0.37` 不自动进入候选配置。

## 3. 逻辑检索轮次

一个逻辑轮次可以包含多个子问题查询，但必须经过统一预算控制：

1. 为未覆盖子问题分配查询；
2. 调用 RetrievalService，始终携带同一顶层 document IDs；
3. 按 `chunk_id` 在本轮去重；
4. 记录所有物理检索调用次数；
5. 按确定的排序规则合并；
6. 截断为本轮最多 5 个候选；
7. 跨轮再次去重，但第一轮已经消耗的候选预算不会退还。

必须同时记录：物理检索调用次数、每轮返回数、本轮去重数、跨轮新增候选数和最终去重候选数。

## 4. 文档范围越界

纯函数：

```text
detect_scope_violation(allowed_document_ids, requested_document_ids, returned_evidence)
```

出现以下任一情况即越界：

- 工具请求包含不在顶层范围内的 ID；
- 子问题目标范围不是顶层范围子集；
- Retrieval 返回了范围外 document ID；
- 模型生成的新 document ID 被传给工具。

越界不能通过过滤后继续执行来掩盖。Investigation 进入 failed，停止原因为 `SCOPE_VIOLATION`，并记录安全 Trace。

## 5. Evidence 接纳规则

纯函数：

```text
accept_evidence(candidates, allowed_document_ids, config)
```

一个候选成为 accepted Evidence，必须同时满足：

1. document ID 在允许范围；
2. chunk ID、document ID、来源字段和内容哈希完整；
3. 未与已接纳候选重复；
4. 配置了 score threshold 时，`score >= threshold`；
5. 至少关联一个已知子问题；
6. `support_label` 是 supports 或 contradicts。

unknown/irrelevant 可以保留在轨迹中，但不计入 coverage。`contradicts` 是有效证据，用于展示冲突，不代表支持最终正向结论。

运行时 `support_label` 来自通过 Schema 校验的结构化判断；离线评测还要与人工 gold label 比较，不能把模型自评当作 Citation 正确性的最终证据。

## 6. 子问题覆盖率

纯函数：

```text
calculate_coverage(required_subquestions, accepted_evidence, min_evidence_per_subquestion)
```

覆盖定义：一个 required 子问题至少具有 `min_evidence_per_subquestion` 条与它关联的 accepted Evidence，才记为 covered。

公式：

```text
coverage = covered_required_subquestions / total_required_subquestions
```

约束：

- `total_required_subquestions == 0` 是无效计划，不能把 coverage 定义为 1；
- 同一 Chunk 对同一子问题只计一次；
- 一个 Chunk 可以支持多个子问题，但必须在结构化 Evidence 中明确关联；
- 离线评测通过 gold subquestion 对齐计算；无法可靠对齐的题标为歧义，不进入硬门禁。

## 7. 证据充分性

纯函数：

```text
assess_sufficiency(subquestions, accepted_evidence, coverage, config)
```

初始候选规则：

- `coverage >= coverage_threshold`；
- 所有标为 required 且涉及明确文档比较的子问题至少有一条 Evidence；
- 不存在缺少必要上下文且只能由用户补充的子问题；
- 每条准备写入报告的关键 claim 至少能绑定一条 accepted Evidence；
- 冲突证据可以形成“存在冲突”的结论，但不能被静默挑选一方。

具体 coverage threshold 和最低 Evidence 数在 Agent 开发前从候选范围中校准。改变规则必须增加 `config_version`，旧轨迹继续按旧版本回放。

## 8. 第二轮触发

纯函数：

```text
should_run_second_round(rounds_used, sufficiency, unresolved_subquestions,
                        clarification_needed, new_query_available,
                        accepted_candidate_count, config)
```

只有以下条件全部成立才触发第二轮：

1. `rounds_used == 1`；
2. 当前 Evidence 不充分；
3. 不需要先向用户澄清；
4. 至少有一个 required 子问题未覆盖；
5. 可以为未覆盖项生成与第一轮不同的受控查询；
6. 全局候选预算仍有剩余；
7. 未发生范围、Provider 或依赖错误。

只要任一条件不满足，就不进入第二轮。第二轮触发结果和每个布尔输入都必须写入轨迹，以便 CI 回放。

## 9. 停止原因

P0 枚举固定为：

| 停止原因 | Investigation结果 |
| --- | --- |
| `SUFFICIENT_EVIDENCE` | completed + answer |
| `NEEDS_CLARIFICATION` | needs_clarification，无最终结果 |
| `NO_NEW_EVIDENCE` | completed + refusal |
| `MAX_ROUNDS_REACHED` | completed + refusal |
| `SCOPE_VIOLATION` | failed |
| `PROVIDER_OUTPUT_INVALID` | failed |
| `DEPENDENCY_UNAVAILABLE` | failed |

纯函数 `determine_stop_reason(...)` 的优先级固定为：

1. 范围越界；
2. Provider/依赖不可恢复错误；
3. 必须澄清；
4. 证据充分；
5. 第二轮没有新增 accepted Evidence；
6. 已使用两轮；
7. 否则不停止，进入第二轮。

达到两轮后即使覆盖率接近阈值也不能开始第三轮。

## 10. Evidence Table

纯函数：

```text
build_evidence_table(subquestions, accepted_evidence, claims)
```

每行至少包含：

```text
subquestion_id
claim_id
conclusion
support_label
document_id
chunk_id
filename
page_number
round_index
score
content_sha256
```

构造规则：

- 只使用 accepted Evidence；
- 输出顺序固定为 subquestion order、claim ID、document ID、chunk ID；
- 同一 claim/chunk 不重复；
- 缺少来源字段的 Evidence 不得进入表；
- 对没有证据的 required 子问题生成明确的 missing-evidence 行，不伪造 Citation；
- Evidence Table 是 Investigation 结果的一部分，不是审批或正式归档记录。

## 11. 可回放轨迹

固定轨迹 fixture 至少保存：

```text
schema_version
decision_config_version
prompt_versions
allowed_document_ids
question / subquestions
round 1 queries and candidates
round 1 decision inputs/outputs
round 2 queries and candidates（若有）
final accepted evidence
coverage / trigger / stop reason
evidence table / response label / citations
```

轨迹不保存 API Key、完整私密原文或不必要的完整 Prompt。Prompt 正文由版本化文件管理，fixture 只保存版本与哈希。

## 12. 参数冻结门禁

进入 Agent 业务实现前必须产生一份版本化配置记录，说明：

- 使用哪些开发 fixtures；
- score/coverage/min-evidence 各候选的结果；
- 对 Evidence Recall、拒答误差、第二轮触发正确率的影响；
- 最终选择与未选择原因；
- 最终题和第二次盲审结果未参与调参。

没有该记录时，可以实现纯函数和fixtures，但不能宣称 Agent 参数已冻结。
