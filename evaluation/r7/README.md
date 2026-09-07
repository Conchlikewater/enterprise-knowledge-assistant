# R7 school Graph Retrieval experiment

This directory is isolated from the production `app/` package. It freezes the
data and comparison rules for a bounded Graph Retrieval experiment; it does not
claim that GraphRAG is available through a production API.

## Frozen assets

- `corpus_sources.json`: canonical facts, official source URLs, license data,
  and 60 manually curated graph assertions;
- `corpus_manifest.json`: SHA256 and page count for 12 deterministic PDFs;
- `documents/`: 12 two-page historical syllabus fixtures;
- `questions.json`: 50 final questions, frozen before graph implementation;
- `development_questions.json`: 10 separate threshold-development questions,
  excluded from all final metrics;
- `protocol.json`: three-arm comparison, fusion, metrics, and promotion gates.

The final set contains 15 ordinary facts, 17 one-hop relationship questions,
12 multi-hop questions, 3 scope-isolation questions, and 3 unsupported
questions. Relationship and multi-hop questions contain exact Evidence and
graph assertion paths.

## Temporal and license boundary

The sources are historical MIT OpenCourseWare offerings from 2003 through
2020. They cannot establish current MIT course numbers, prerequisites, or
degree requirements. Raw OCW pages and third-party extracts are not committed.
The adapted dataset is separately covered by `LICENSE.md` under CC BY-NC-SA
4.0; the application code remains MIT-licensed.

## Rebuild the fixtures

From the repository root:

```powershell
.\.venv\Scripts\python.exe scripts\build_r7_school_corpus.py
```

The builder writes the 12 PDFs and `corpus_manifest.json`. A second build must
produce identical hashes. It does not access the network.

## Current gate

The formal comparison uses the existing `text-embedding-3-small` adapter, but
no real Provider call is authorized yet. The semantic threshold must first be
selected only on `development_questions.json` using the frozen rule in
`protocol.json`, then recorded in a preregistration-only commit. Graph code may
start only after that value is frozen.

An offline hashing run may later verify mechanics, but it cannot decide whether
Graph Retrieval should enter the application. Even a positive formal result
requires a separate integration decision.
