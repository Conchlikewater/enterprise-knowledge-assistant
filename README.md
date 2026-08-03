# Enterprise Knowledge Assistant（RAG V1）

这是一个面向学习和本地演示的企业知识助手后端。V1 将通过 FastAPI 提供 TXT/PDF 同步摄取、限定文档范围的向量检索，以及由检索结果生成的结构化引用。

## 当前阶段：Day 10 回答与结构化引用闭环

目前已建立模块边界、类型化配置、统一错误格式、完整应用生命周期、核心领域模型、SQLite 文档仓库、安全的 TXT/PDF 文档处理层、本地持久化 Qdrant、OpenAI embedding/LLM providers、带补偿回滚的同步摄取、文档范围检索，以及基于检索证据的回答和结构化引用 API。

```text
app/api              HTTP 路由与应用入口
app/core             配置、异常和全局错误处理
app/domain           与框架无关的核心数据模型
app/providers        OpenAI embedding 与 LLM 实现
app/storage          SQLite 文档仓库与本地 Qdrant 向量存储
app/services         同步摄取与后续业务流程编排
app/document_processing  文件校验、哈希、TXT/PDF 解析与切块
tests                单元、集成和评估测试
data                 本地运行数据（不提交数据库内容）
```

## 当前 API

- `GET /health`：检查应用、SQLite、Qdrant 和 embedding provider 是否可用。
- `POST /api/v1/documents`：上传一个 UTF-8 TXT 或文本型 PDF，并同步完成摄取。
- `GET /api/v1/documents`：列出文档元数据，不暴露本地文件路径。
- `GET /api/v1/documents/{document_id}`：读取单个文档元数据。
- `DELETE /api/v1/documents/{document_id}`：删除文件、向量和文档记录。
- `POST /api/v1/search`：仅在请求指定且状态为 `ready` 的文档中执行语义检索。
- `POST /api/v1/answers`：基于指定文档的检索证据生成回答和结构化引用。

启动服务后可在 `http://127.0.0.1:8000/docs` 查看并直接操作交互式 API 文档。上传需要先在 `.env` 中配置 `OPENAI_API_KEY`；未配置时应用仍可启动，但健康检查和上传会返回稳定的 503 错误。

所有应用错误使用以下稳定结构：

```json
{
  "error": {
    "code": "DOCUMENT_NOT_FOUND",
    "message": "The requested document was not found.",
    "request_id": "..."
  }
}
```

## 环境说明

- 当前 Python：3.12，项目专用环境为 `.venv`
- 不复用 `02_foundations` 的虚拟环境
- 已安装轻量 Web、multipart 上传解析、测试、文本型 PDF、Qdrant 和 OpenAI 官方 SDK
- embedding 和回答使用云端 API；本机不需要安装模型
- 尚未安装 OCR 或大型 RAG 框架
- `.env.example` 只包含非敏感默认值；真实 `.env` 不提交 Git
- API Key 只从环境或 `.env` 读取，不进入日志、响应或 Settings 的字符串表示
- 摄取失败会删除该次写入的向量和上传文件，并保留状态为 `failed` 的文档记录用于排查
- 删除接口会验证数据库中的保存路径确实属于配置的上传目录，拒绝危险路径
- 检索前后都会验证文档范围；查询正文不会写入应用日志或响应元数据
- LLM 请求使用 `store=False`；模型只生成答案正文，引用元数据由应用从真实检索结果构造
- 没有检索证据时直接返回稳定的无证据响应，不调用 LLM

依赖清单写在 `requirements.txt` 和 `requirements-dev.txt`，新增依赖前必须先说明用途和范围。

## 架构约束

- 路由只负责 HTTP；业务流程进入 services。
- domain 不依赖 FastAPI、Qdrant 或模型 SDK。
- providers/storage 通过小接口隔离具体实现。
- 不向响应或日志泄露文档内容、问题、提示词、密钥或本地路径。
- V1 不包含 Docker、任务队列、认证、多租户、OCR、Agent、MCP 或前端。

## 设计文档

- `docs/architecture_log.md`：V1 架构决策、API 契约和质量边界。
- `docs/open_source_research.md`：开源项目调研证据。
- `docs/provider_decisions.md`：OpenAI embedding/LLM 选择和隐私配置。
