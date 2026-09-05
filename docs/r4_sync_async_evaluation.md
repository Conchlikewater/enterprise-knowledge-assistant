# R4 同步 / 异步摄取实测与工程决策

> 状态：2026-09-05 工程实现与实测完成；⑤拥有权验证尚未完成，R5 尚未开始。

## 1. 结论

在本次固定的本机、单 Worker、8 KiB 合成 TXT 和 200 ms 确定性 Embedding
工作负载下，V2 异步摄取适合作为“长耗时摄取”的作品集演示首选路径，同时必须
保留 V1 同步兼容接口。

这个结论的理由不是“异步端到端更快”：本次异步端到端反而更慢。它的价值是把
请求接收与耗时处理解耦，连续提交时更快返回 `job_id`，并能查询状态和恢复一个
明确的 Worker 崩溃点。该结论只适用于本次作品集实验，不是生产替换、容量或 SLA
结论。

## 2. 证据与环境

- 冻结协议：[`docs/r4_evaluation_protocol.md`](r4_evaluation_protocol.md)；
- 机器报告：[`evaluation/ingestion_benchmark_report.json`](../evaluation/ingestion_benchmark_report.json)；
- 基准源码提交：`c5faa054b93e8053a1f0f3c62347dd95da7af8a3`；
- 质量门禁：GitHub Actions `33946956840`，191 tests + 34 subtests，branch-aware
  coverage 87.59%；
- 结果提交前本机完整门禁：193 tests + 34 subtests，branch-aware coverage
  87.59%，lint、format、依赖、字节码和离线评测全部通过；
- 本机：AMD Ryzen 9 7945HX，16 核 / 32 逻辑处理器，15.2 GiB RAM；
- 软件：Windows 11 专业版、Python 3.12.10、Qdrant Server 1.19.0、Docker
  Engine 29.7.2；
- HTTP 边界：`httpx.ASGITransport` 的 FastAPI 应用层请求，不含 Uvicorn、网络
  传输和反向代理；
- Provider：固定等待 200 ms 的 3 维确定性 Fake Embedding，无网络、无 API Key、
  无费用。

正式运行使用隔离的临时 SQLite、上传目录和 Qdrant collection。运行完成后临时
collection 已清理，只剩原有 `knowledge_chunks`；没有写入生产 collection。

## 3. 七维度结果

| 维度 | 同步 V1 | 异步 V2 | 准确解释 |
| --- | ---: | ---: | --- |
| 单次 API 接收 P95 | 340.65 ms | 49.32 ms | 异步低 85.52%，约 6.91 倍响应优势；只指接收响应 |
| 单次端到端 P95 | 340.65 ms | 775.81 ms | 异步为同步的 2.28 倍；Job、轮询和进程边界有成本 |
| 处理期间 `/health` P95 | 23.08 ms，5/5 为 200 | 23.43 ms，5/5 为 200 | 两者本次近似；V1 已把同步处理放入线程池，本实验未证明吞吐优势 |
| 连续 5 份全部响应 P95 | 1559.06 ms | 121.00 ms | 异步低 92.24%，客户端可更快拿到 5 个 Job |
| 连续 5 份全部 ready P95 | 1559.06 ms | 3192.49 ms | 异步为同步的 2.05 倍；单 Worker 队列积压可见 |
| Worker 崩溃恢复 | 不支持 / 不适用 | 通过，2645.38 ms | 同一 Job 恢复；attempt=2；11 个可见 Chunk 且无重复 |
| 100 ms 请求预算 | P95 超出 | P95 未超出 | 仅是本实验边界，不是生产 SLA 或真实代理超时 |

单次样本每种模式各 20 个；连续上传为 3 轮、每轮 5 份。JSON 保留所有原始样本、
mean、P50、P95、min 和 max。样本量较小，尤其连续上传只有 3 轮，不能把毫秒差值
推广为稳定容量数字。

## 4. 复杂度代价

| 责任 | 同步 V1 | 异步 V2 |
| --- | --- | --- |
| 运行服务 | API + Qdrant | API + Worker + Qdrant |
| 生命周期对象 | Document | Document + IngestionJob |
| 客户端完成交互 | POST 一类 | POST + Job GET 两类 |
| 失败处理 | 请求内补偿 | 原子领取、启动恢复、重放清理、状态轮询 |

V2 新增了 API/Worker 竞争 SQLite、Worker 需要守护、Qdrant 与 SQLite 不能组成单个
事务、客户端必须轮询等故障面。它不是免费获得的“性能优化”。

## 5. 决策

预注册的五项判断全部满足：

1. 异步接收 P95 低于同步；
2. 异步在 100 ms 内、同步超过 100 ms；
3. 连续上传时异步更快返回全部响应；
4. 固定崩溃点恢复通过且无重复可见 Chunk；
5. 完整质量门禁和 Qdrant Server 集成测试通过。

因此，演示时优先展示 V2 的 `202 + job_id → 状态查询 → ready`，并展示崩溃恢复；
V1 `201` 保留用于兼容和讲解简单路径。不得说“异步摄取整体快 6.91 倍”，只能说
“在本次受控实验中，异步 API 接收 P95 约快 6.91 倍，但单次端到端 P95 约慢
2.28 倍”。

## 6. 真实排障记录

第一次正式运行无效：长驻 Worker 的 stdout 接入 `subprocess.PIPE`，父进程直到最后
才读取。Windows 管道缓冲写满后，Worker 卡在日志写入，Job 未在 60 秒内 ready。
该运行未生成正式报告。

修复没有放宽超时，而是把长驻 Worker 日志写入临时文件，进程结束后才读取失败
尾部；单次 crash/recover 进程仍使用有界输出捕获。回归测试验证长驻进程不再使用
PIPE，完整本机门禁和 CI 随后通过。修复提交为 `c5faa05`。

## 7. 复现

先保证本机 Qdrant Server 在 `127.0.0.1:6333` 可用，然后运行：

```powershell
.\.venv\Scripts\python.exe scripts\run_ingestion_benchmark.py `
  --quality-gate-evidence "github-actions:33946956840" `
  --source-commit "c5faa054b93e8053a1f0f3c62347dd95da7af8a3"
```

该命令不使用真实 Provider。重跑会产生新的时间样本和生成时间；如要更新正式证据，
必须重新核对、测试并独立提交，不能只挑一次更好看的结果。

## 8. 限制

- 合成 8 KiB TXT 和固定延迟不能代表 PDF、大文件或真实 OpenAI 延迟；
- ASGI 应用层测试不包含公网、Uvicorn、反向代理或客户端网络；
- 顺序上传不是并发压测，未测吞吐上限和背压；
- 只测试一台机器、一个 Worker 和一个固定崩溃点；
- 未测试多 Worker、Lease/Fencing、网络分区或旧 Worker 晚到竞争；
- 100 ms 是预注册实验边界，不是服务等级承诺。
