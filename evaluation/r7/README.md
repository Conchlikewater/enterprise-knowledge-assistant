# R7 school Graph Retrieval experiment

This directory is isolated from the production `app/` package. The user withdrew
the 50-question preregistration before any formal experiment result and requested
a fresh 100-question design. The proposed distribution is awaiting review;
no 100-question file or hash has been frozen. See `revision_review.json` and
`docs/r7_100_question_distribution_proposal.md`. Graph retrieval and automatic
graph extraction are not implemented.

## Historical assets retained for traceability

- `corpus_sources.json`: canonical facts, official source URLs, license data,
  and 60 manually curated graph assertions;
- `corpus_manifest.json`: SHA256 and page count for 12 deterministic PDFs;
- `documents/`: 12 two-page historical syllabus fixtures;
- `questions.json`: superseded 50-question set, retained unchanged, not executable;
- `development_questions.json`: 10 separate threshold-development questions,
  excluded from all final metrics;
- `protocol.json`: three-arm comparison, fusion, metrics, and promotion gates.

The superseded set contains 15 ordinary facts, 17 one-hop relationship questions,
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

The USD 0.01 development-only calibration was authorized and ran against the
existing 12-document corpus and 10 development questions. Three embedding
requests used 3,869 reported tokens (estimated USD 0.00007738). The registered
threshold rule found **no eligible threshold**: two required evidence chunks
ranked 22 and 10, outside Top-5. No final questions were loaded.

The original report is `calibration/20260908_12docs.json`. It is a development
diagnostic, not a graph comparison or a threshold for expanded data. The
100-question distribution and corpus expansion require review; the calibration
blocker must be resolved before a replacement preregistration and graph code.
The three arms, metrics, and promotion thresholds remain unchanged.

The default calibration command is a no-network dry run:

```powershell
.\.venv\Scripts\python.exe scripts\run_r7_calibration.py
```

Real runs require explicit `--allow-paid`, new output/cache paths, and user
authorization. Existing reports cannot be overwritten. Final three-arm
evaluation and LLM graph extraction do not have paid-call authorization.

An offline hashing run may later verify mechanics, but it cannot decide whether
Graph Retrieval should enter the application. Even a positive formal result
requires a separate integration decision.
