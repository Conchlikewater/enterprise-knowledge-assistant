# OpenAI vs DeepSeek RAG Generation Comparison

Questions: 50; documents: 10; pricing snapshot: 2026-08-11.

| Metric | openai | deepseek |
|---|---:|---:|
| Model | gpt-5.6-sol | deepseek-v4-flash |
| Reference-answer token F1 | 75.15% | 72.58% |
| Answer/refusal behavior accuracy | 100.00% | 91.67% |
| Citation marker validity | 100.00% | 100.00% |
| Application citation integrity | 100.00% | 100.00% |
| Average LLM latency (ms) | 1771.45 | 912.84 |
| P50 LLM latency (ms) | 1558.19 | 932.42 |
| P95 LLM latency (ms) | 3430.64 | 1143.56 |
| Input tokens | 14546 | 14372 |
| Output tokens | 1118 | 905 |
| Estimated API cost (USD) | 0.106270 | 0.002195 |

## Limitations

- The corpus and questions are synthetic and do not establish production accuracy.
- Reference-answer token F1 is a deterministic proxy and may penalize valid paraphrases.
- Only answer/refuse behavior is scored; the current production prompt has no clarification response.
- Application citations are constructed from retrieved chunks; citation-marker validity separately checks the model text.
- Latency measures sequential provider calls on this machine and is not a concurrency benchmark.
