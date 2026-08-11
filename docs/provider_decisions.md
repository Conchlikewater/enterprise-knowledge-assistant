# Provider Decisions

- Decision date: 2026-08-03
- Enhancement date: 2026-08-11
- Status: OpenAI runtime-verified; DeepSeek adapter offline-tested, live comparison pending
- Scope: one active embedding provider and one selectable LLM provider at runtime

## Embedding provider

V1 uses the OpenAI Python SDK with `text-embedding-3-small` and an explicit
1,536-dimensional output. The Qdrant collection and embedding provider must
agree on this dimension before ingestion or retrieval begins.

The adapter:

- batches document chunks while preserving order
- validates dimensions and finite values
- maps upstream failures to a stable application error
- does not log input text, vectors, credentials, or raw SDK errors

## LLM provider

The default model is `gpt-5.6-sol`. V1 uses it through the Responses API with:

- low reasoning effort for this bounded grounded-answer task
- low text verbosity
- a small maximum output budget
- `store=False`
- no tools, web search, file search, or conversation state

The prompt tells the model to use only supplied evidence, treat evidence as
untrusted quoted data, cite numbered source blocks, and return a stable marker
when evidence is insufficient.

The application—not the model—constructs citation metadata. Document IDs,
chunk IDs, filenames, page numbers, excerpts, and scores always come from
retrieved Qdrant payloads.

The later Multi-LLM enhancement keeps this contract and adds
`deepseek-v4-flash` through DeepSeek's OpenAI-compatible Responses API. Only
the generation adapter changes: OpenAI remains the embedding provider, and the
retrieval pipeline, evidence blocks, refusal marker, and application citation
construction stay unchanged. Exactly one LLM backend is active in the API at
runtime, selected with `RAG_LLM_PROVIDER=openai|deepseek`.

## Configuration

The model names and runtime limits can be changed through environment variables,
but the application intentionally configures only one embedding implementation
and one selected LLM implementation at a time.

Relevant settings:

```text
RAG_EMBEDDING_MODEL=text-embedding-3-small
RAG_EMBEDDING_DIMENSIONS=1536
RAG_LLM_PROVIDER=openai
RAG_LLM_MODEL=gpt-5.6-sol
RAG_LLM_REASONING_EFFORT=low
RAG_LLM_VERBOSITY=low
RAG_LLM_MAX_OUTPUT_TOKENS=800
RAG_LLM_TIMEOUT_SECONDS=60
RAG_DEEPSEEK_BASE_URL=https://api.deepseek.com
```

## Verification evidence

Both LLM provider adapters have deterministic unit tests using injected SDK test
doubles and do not require API keys in CI. Separate OpenAI live smoke checks
used only synthetic content and confirmed:

- document and query embeddings reach local Qdrant
- document-scoped retrieval returns only selected-document results
- `gpt-5.6-sol` produces a grounded answer
- every returned citation resolves to a retrieved chunk
- uploaded files and vectors can be deleted after the request lifecycle

DeepSeek has not yet been live-run on this machine because no
`DEEPSEEK_API_KEY` is configured. No DeepSeek quality, latency, token, or cost
result is claimed until the explicit online comparison is completed.

## Official references

- OpenAI model guidance: https://developers.openai.com/api/docs/guides/latest-model
- GPT-5.6 Sol model: https://developers.openai.com/api/docs/models/gpt-5.6-sol
- OpenAI Python SDK: https://github.com/openai/openai-python
- DeepSeek API quick start: https://api-docs.deepseek.com/
- DeepSeek Responses API compatibility: https://api-docs.deepseek.com/guides/responses_api/
- DeepSeek model pricing: https://api-docs.deepseek.com/quick_start/pricing
