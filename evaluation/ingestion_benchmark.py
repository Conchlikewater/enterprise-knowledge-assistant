"""Reproducible R4 comparison of synchronous and asynchronous ingestion."""

from __future__ import annotations

import asyncio
import json
import platform
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Sequence
from contextlib import AsyncExitStack
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Any, TextIO
from urllib.parse import urlsplit
from urllib.request import urlopen
from uuid import UUID, uuid4

import httpx
from qdrant_client import QdrantClient

from app.core.config import Settings
from app.main import create_app
from app.providers.embedding_provider import EmbeddingProvider
from evaluation.latency import percentile
from evaluation.providers import EvaluationLLMProvider


@dataclass(frozen=True, slots=True)
class IngestionBenchmarkConfig:
    """Frozen workload controls; defaults are the formal R4 profile."""

    qdrant_url: str
    quality_gate_evidence: str
    source_commit: str
    document_size_bytes: int = 8192
    embedding_delay_ms: int = 200
    warmup_samples: int = 2
    single_samples: int = 20
    batch_rounds: int = 3
    batch_size: int = 5
    health_probes: int = 5
    poll_interval_ms: int = 10
    request_budget_ms: int = 100
    chunk_size: int = 1000
    chunk_overlap: int = 150
    vector_size: int = 3
    qdrant_timeout_seconds: float = 5.0
    worker_timeout_seconds: float = 60.0

    def __post_init__(self) -> None:
        parsed_url = urlsplit(self.qdrant_url)
        if parsed_url.scheme not in {"http", "https"}:
            raise ValueError("qdrant_url must use http or https")
        if parsed_url.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("R4 only permits a loopback Qdrant Server")
        if not self.quality_gate_evidence.strip():
            raise ValueError("quality_gate_evidence must not be blank")
        if not self.source_commit.strip():
            raise ValueError("source_commit must not be blank")
        positive_integers = {
            "document_size_bytes": self.document_size_bytes,
            "embedding_delay_ms": self.embedding_delay_ms,
            "single_samples": self.single_samples,
            "batch_rounds": self.batch_rounds,
            "batch_size": self.batch_size,
            "health_probes": self.health_probes,
            "poll_interval_ms": self.poll_interval_ms,
            "request_budget_ms": self.request_budget_ms,
            "chunk_size": self.chunk_size,
            "vector_size": self.vector_size,
        }
        for name, value in positive_integers.items():
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        if self.warmup_samples < 0:
            raise ValueError("warmup_samples must not be negative")
        if not 0 <= self.chunk_overlap < self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        if self.qdrant_timeout_seconds <= 0:
            raise ValueError("qdrant_timeout_seconds must be positive")
        if self.worker_timeout_seconds <= 0:
            raise ValueError("worker_timeout_seconds must be positive")

    @property
    def normal_async_job_count(self) -> int:
        return (
            self.warmup_samples
            + self.single_samples
            + (self.batch_rounds * self.batch_size)
            + 1
        )

    @property
    def poll_interval_seconds(self) -> float:
        return self.poll_interval_ms / 1000


@dataclass(frozen=True, slots=True)
class TimingSummary:
    count: int
    mean_ms: float
    p50_ms: float
    p95_ms: float
    minimum_ms: float
    maximum_ms: float


@dataclass(slots=True)
class _ModeSamples:
    acceptance_ms: list[float] = field(default_factory=list)
    end_to_end_ms: list[float] = field(default_factory=list)
    health_ms: list[float] = field(default_factory=list)
    health_status_codes: list[int] = field(default_factory=list)
    batch_acceptance_ms: list[float] = field(default_factory=list)
    batch_response_total_ms: list[float] = field(default_factory=list)
    batch_ready_total_ms: list[float] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _AcceptedJob:
    status_url: str
    document_id: UUID
    acceptance_ms: float
    started_at: float


@dataclass(slots=True)
class _RunningWorker:
    process: subprocess.Popen[str]
    log_path: Path
    log_stream: TextIO


@dataclass(frozen=True, slots=True)
class IngestionBenchmarkReport:
    benchmark: str
    schema_version: int
    generated_at: str
    duration_ms: float
    source_commit: str
    quality_gate_evidence: str
    environment: dict[str, Any]
    configuration: dict[str, Any]
    synchronous: dict[str, Any]
    asynchronous: dict[str, Any]
    crash_recovery: dict[str, Any]
    complexity: dict[str, Any]
    decision: dict[str, Any]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["limitations"] = list(self.limitations)
        return payload


class ControlledDelayEmbeddingProvider(EmbeddingProvider):
    """Deterministic provider with a fixed delay and no external I/O."""

    def __init__(self, dimensions: int, delay_ms: int) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        if delay_ms < 0:
            raise ValueError("delay_ms must not be negative")
        self._dimensions = dimensions
        self._delay_seconds = delay_ms / 1000
        self._started = threading.Event()

    @property
    def name(self) -> str:
        return "r4-controlled-delay"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        self._started.set()
        time.sleep(self._delay_seconds)
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def close(self) -> None:
        pass

    def reset_started(self) -> None:
        self._started.clear()

    def wait_until_started(self, timeout_seconds: float) -> bool:
        return self._started.wait(timeout_seconds)

    def _vector(self, text: str) -> list[float]:
        checksum = sum(text.encode("utf-8"))
        values = [
            1.0,
            float(len(text) % 101) / 100,
            float(checksum % 101) / 100,
        ]
        if self._dimensions <= len(values):
            return values[: self._dimensions]
        return values + ([0.0] * (self._dimensions - len(values)))


def summarize_timings(values: list[float]) -> TimingSummary:
    """Build stable aggregate fields while retaining raw samples separately."""

    if not values:
        raise ValueError("timing values must not be empty")
    return TimingSummary(
        count=len(values),
        mean_ms=round(fmean(values), 4),
        p50_ms=round(percentile(values, 0.50), 4),
        p95_ms=round(percentile(values, 0.95), 4),
        minimum_ms=round(min(values), 4),
        maximum_ms=round(max(values), 4),
    )


def evaluate_demo_decision(
    *,
    sync_acceptance_p95_ms: float,
    async_acceptance_p95_ms: float,
    sync_batch_response_p95_ms: float,
    async_batch_response_p95_ms: float,
    request_budget_ms: float,
    crash_recovery_passed: bool,
    quality_gate_evidence: str,
) -> dict[str, Any]:
    """Apply the pre-registered R4 decision without changing production code."""

    criteria = {
        "async_acceptance_p95_lower_than_sync": (
            async_acceptance_p95_ms < sync_acceptance_p95_ms
        ),
        "async_acceptance_within_request_budget": (
            async_acceptance_p95_ms <= request_budget_ms
        ),
        "sync_acceptance_exceeds_request_budget": (
            sync_acceptance_p95_ms > request_budget_ms
        ),
        "async_batch_response_p95_lower_than_sync": (
            async_batch_response_p95_ms < sync_batch_response_p95_ms
        ),
        "crash_recovery_passed": crash_recovery_passed,
        "quality_gate_evidence_recorded": bool(quality_gate_evidence.strip()),
    }
    eligible = all(criteria.values())
    return {
        "recommendation": (
            "prefer_v2_for_long_running_ingestion_demo_keep_v1_compatible"
            if eligible
            else "retain_both_without_async_demo_preference"
        ),
        "eligible": eligible,
        "criteria": criteria,
        "scope": "portfolio demonstration only; not a production replacement",
    }


def run_ingestion_benchmark(
    project_root: Path,
    config: IngestionBenchmarkConfig,
) -> IngestionBenchmarkReport:
    """Run the complete R4 benchmark against a local Qdrant Server."""

    return asyncio.run(_run_ingestion_benchmark(project_root.resolve(), config))


async def _run_ingestion_benchmark(
    project_root: Path,
    config: IngestionBenchmarkConfig,
) -> IngestionBenchmarkReport:
    benchmark_started = time.perf_counter()
    await asyncio.to_thread(_wait_for_qdrant, config)
    qdrant_version = await asyncio.to_thread(_read_qdrant_version, config)
    suffix = uuid4().hex
    sync_collection = f"r4_sync_{suffix}"
    async_collection = f"r4_async_{suffix}"
    sync_samples = _ModeSamples()
    async_samples = _ModeSamples()
    worker_process: _RunningWorker | None = None
    cleanup_client = QdrantClient(
        url=config.qdrant_url,
        timeout=config.qdrant_timeout_seconds,
    )

    try:
        with (
            tempfile.TemporaryDirectory(prefix="r4-sync-") as sync_directory,
            tempfile.TemporaryDirectory(prefix="r4-async-") as async_directory,
        ):
            sync_root = Path(sync_directory)
            async_root = Path(async_directory)
            sync_provider = ControlledDelayEmbeddingProvider(
                config.vector_size,
                config.embedding_delay_ms,
            )
            async_api_provider = ControlledDelayEmbeddingProvider(
                config.vector_size,
                config.embedding_delay_ms,
            )
            sync_app = create_app(
                _settings(sync_root, sync_collection, config),
                embedding_provider=sync_provider,
                llm_provider=EvaluationLLMProvider(),
            )
            async_app = create_app(
                _settings(async_root, async_collection, config),
                embedding_provider=async_api_provider,
                llm_provider=EvaluationLLMProvider(),
            )

            async with AsyncExitStack() as stack:
                await stack.enter_async_context(
                    sync_app.router.lifespan_context(sync_app)
                )
                await stack.enter_async_context(
                    async_app.router.lifespan_context(async_app)
                )
                sync_client = await stack.enter_async_context(
                    httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=sync_app),
                        base_url="http://sync-benchmark",
                    )
                )
                async_client = await stack.enter_async_context(
                    httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=async_app),
                        base_url="http://async-benchmark",
                    )
                )
                worker_process = _start_worker_process(
                    project_root,
                    mode="serve",
                    root=async_root,
                    collection=async_collection,
                    config=config,
                    max_jobs=config.normal_async_job_count,
                )

                await _warm_up(sync_client, async_client, config)
                await _measure_single_documents(
                    sync_client,
                    async_client,
                    sync_samples,
                    async_samples,
                    config,
                )
                await _measure_batches(
                    sync_client,
                    async_client,
                    sync_samples,
                    async_samples,
                    config,
                )
                await _measure_responsiveness(
                    sync_client,
                    async_client,
                    sync_provider,
                    sync_samples,
                    async_samples,
                    config,
                )
                await asyncio.to_thread(
                    _wait_for_worker,
                    worker_process,
                    config.worker_timeout_seconds,
                )
                worker_process = None
                crash_recovery = await _measure_crash_recovery(
                    project_root,
                    async_root,
                    async_collection,
                    async_client,
                    async_app.state.vector_store,
                    config,
                )

        synchronous = _mode_report(sync_samples, config)
        asynchronous = _mode_report(async_samples, config)
        decision = evaluate_demo_decision(
            sync_acceptance_p95_ms=synchronous["single"]["acceptance_ms"]["p95_ms"],
            async_acceptance_p95_ms=(asynchronous["single"]["acceptance_ms"]["p95_ms"]),
            sync_batch_response_p95_ms=(
                synchronous["sequential_batch"]["all_responses_ms"]["p95_ms"]
            ),
            async_batch_response_p95_ms=(
                asynchronous["sequential_batch"]["all_responses_ms"]["p95_ms"]
            ),
            request_budget_ms=config.request_budget_ms,
            crash_recovery_passed=crash_recovery["passed"],
            quality_gate_evidence=config.quality_gate_evidence,
        )
        return IngestionBenchmarkReport(
            benchmark="r4-sync-async-ingestion",
            schema_version=1,
            generated_at=datetime.now(UTC).isoformat(),
            duration_ms=round((time.perf_counter() - benchmark_started) * 1000, 4),
            source_commit=config.source_commit,
            quality_gate_evidence=config.quality_gate_evidence,
            environment={
                "platform": platform.platform(),
                "python": platform.python_version(),
                "qdrant_server": qdrant_version,
                "qdrant_endpoint": _safe_endpoint(config.qdrant_url),
                "http_transport": "httpx-asgi-application-layer",
                "worker_boundary": "independent-python-subprocess",
                "embedding_provider": "r4-controlled-delay-no-network",
            },
            configuration=_configuration(config),
            synchronous=synchronous,
            asynchronous=asynchronous,
            crash_recovery=crash_recovery,
            complexity=_complexity_report(),
            decision=decision,
            limitations=(
                "Uses a fixed-delay deterministic embedding provider, not OpenAI.",
                "Measures ASGI application latency without Uvicorn or network transit.",
                "Uses synthetic 8 KiB TXT documents on one local machine.",
                "Sequential batches are not concurrent load or capacity tests.",
                "Covers one Worker and one fixed crash point, not distributed failure.",
                "The 100 ms request budget is an experimental boundary, not an SLA.",
            ),
        )
    finally:
        if worker_process is not None:
            _terminate_worker(worker_process)
        for collection_name in (sync_collection, async_collection):
            try:
                if cleanup_client.collection_exists(collection_name):
                    cleanup_client.delete_collection(collection_name=collection_name)
            except Exception:
                pass
        cleanup_client.close()


async def _warm_up(
    sync_client: httpx.AsyncClient,
    async_client: httpx.AsyncClient,
    config: IngestionBenchmarkConfig,
) -> None:
    for index in range(config.warmup_samples):
        label = f"warmup-{index:02d}"
        if index % 2 == 0:
            await _post_sync(sync_client, label, config)
            accepted = await _accept_async(async_client, label, config)
            await _wait_until_ready(async_client, accepted, config)
        else:
            accepted = await _accept_async(async_client, label, config)
            await _wait_until_ready(async_client, accepted, config)
            await _post_sync(sync_client, label, config)


async def _measure_single_documents(
    sync_client: httpx.AsyncClient,
    async_client: httpx.AsyncClient,
    sync_samples: _ModeSamples,
    async_samples: _ModeSamples,
    config: IngestionBenchmarkConfig,
) -> None:
    async def measure_sync(label: str) -> None:
        acceptance_ms, end_to_end_ms = await _post_sync(sync_client, label, config)
        sync_samples.acceptance_ms.append(acceptance_ms)
        sync_samples.end_to_end_ms.append(end_to_end_ms)

    async def measure_async(label: str) -> None:
        accepted = await _accept_async(async_client, label, config)
        end_to_end_ms = await _wait_until_ready(async_client, accepted, config)
        async_samples.acceptance_ms.append(accepted.acceptance_ms)
        async_samples.end_to_end_ms.append(end_to_end_ms)

    for index in range(config.single_samples):
        label = f"single-{index:03d}"
        if index % 2 == 0:
            await measure_sync(label)
            await measure_async(label)
        else:
            await measure_async(label)
            await measure_sync(label)


async def _measure_batches(
    sync_client: httpx.AsyncClient,
    async_client: httpx.AsyncClient,
    sync_samples: _ModeSamples,
    async_samples: _ModeSamples,
    config: IngestionBenchmarkConfig,
) -> None:
    for round_index in range(config.batch_rounds):
        labels = [
            f"batch-{round_index:02d}-{item_index:02d}"
            for item_index in range(config.batch_size)
        ]
        if round_index % 2 == 0:
            await _measure_sync_batch(sync_client, labels, sync_samples, config)
            await _measure_async_batch(async_client, labels, async_samples, config)
        else:
            await _measure_async_batch(async_client, labels, async_samples, config)
            await _measure_sync_batch(sync_client, labels, sync_samples, config)


async def _measure_sync_batch(
    client: httpx.AsyncClient,
    labels: list[str],
    samples: _ModeSamples,
    config: IngestionBenchmarkConfig,
) -> None:
    started_at = time.perf_counter()
    for label in labels:
        acceptance_ms, _ = await _post_sync(client, label, config)
        samples.batch_acceptance_ms.append(acceptance_ms)
    total_ms = (time.perf_counter() - started_at) * 1000
    samples.batch_response_total_ms.append(total_ms)
    samples.batch_ready_total_ms.append(total_ms)


async def _measure_async_batch(
    client: httpx.AsyncClient,
    labels: list[str],
    samples: _ModeSamples,
    config: IngestionBenchmarkConfig,
) -> None:
    started_at = time.perf_counter()
    accepted_jobs: list[_AcceptedJob] = []
    for label in labels:
        accepted = await _accept_async(client, label, config)
        accepted_jobs.append(accepted)
        samples.batch_acceptance_ms.append(accepted.acceptance_ms)
    samples.batch_response_total_ms.append((time.perf_counter() - started_at) * 1000)
    await asyncio.gather(
        *(_wait_until_ready(client, accepted, config) for accepted in accepted_jobs)
    )
    samples.batch_ready_total_ms.append((time.perf_counter() - started_at) * 1000)


async def _measure_responsiveness(
    sync_client: httpx.AsyncClient,
    async_client: httpx.AsyncClient,
    sync_provider: ControlledDelayEmbeddingProvider,
    sync_samples: _ModeSamples,
    async_samples: _ModeSamples,
    config: IngestionBenchmarkConfig,
) -> None:
    sync_provider.reset_started()
    sync_upload = asyncio.create_task(_post_sync(sync_client, "responsiveness", config))
    provider_started = await asyncio.to_thread(
        sync_provider.wait_until_started,
        config.worker_timeout_seconds,
    )
    if not provider_started:
        sync_upload.cancel()
        raise RuntimeError("synchronous provider did not enter processing")
    await _collect_health_probes(sync_client, sync_samples, config)
    await sync_upload

    accepted = await _accept_async(async_client, "responsiveness", config)
    await _wait_for_job_status(async_client, accepted.status_url, "running", config)
    await _collect_health_probes(async_client, async_samples, config)
    await _wait_until_ready(async_client, accepted, config)


async def _collect_health_probes(
    client: httpx.AsyncClient,
    samples: _ModeSamples,
    config: IngestionBenchmarkConfig,
) -> None:
    for _ in range(config.health_probes):
        started_at = time.perf_counter()
        response = await client.get("/health")
        samples.health_ms.append((time.perf_counter() - started_at) * 1000)
        samples.health_status_codes.append(response.status_code)
        if response.status_code != 200:
            raise RuntimeError(f"health probe returned {response.status_code}")


async def _post_sync(
    client: httpx.AsyncClient,
    label: str,
    config: IngestionBenchmarkConfig,
) -> tuple[float, float]:
    started_at = time.perf_counter()
    response = await client.post(
        "/api/v1/documents",
        files={"file": (f"{label}.txt", _document_bytes(label, config), "text/plain")},
    )
    elapsed_ms = (time.perf_counter() - started_at) * 1000
    if response.status_code != 201:
        raise RuntimeError(f"synchronous upload returned {response.status_code}")
    if response.json().get("status") != "ready":
        raise RuntimeError("synchronous upload did not return a ready document")
    return elapsed_ms, elapsed_ms


async def _accept_async(
    client: httpx.AsyncClient,
    label: str,
    config: IngestionBenchmarkConfig,
) -> _AcceptedJob:
    started_at = time.perf_counter()
    response = await client.post(
        "/api/v2/documents",
        files={"file": (f"{label}.txt", _document_bytes(label, config), "text/plain")},
    )
    acceptance_ms = (time.perf_counter() - started_at) * 1000
    if response.status_code != 202:
        raise RuntimeError(f"asynchronous upload returned {response.status_code}")
    body = response.json()
    if body.get("document_status") != "processing":
        raise RuntimeError("asynchronous upload returned an unexpected document state")
    return _AcceptedJob(
        status_url=body["status_url"],
        document_id=UUID(body["document_id"]),
        acceptance_ms=acceptance_ms,
        started_at=started_at,
    )


async def _wait_until_ready(
    client: httpx.AsyncClient,
    accepted: _AcceptedJob,
    config: IngestionBenchmarkConfig,
) -> float:
    await _wait_for_job_status(client, accepted.status_url, "ready", config)
    return (time.perf_counter() - accepted.started_at) * 1000


async def _wait_for_job_status(
    client: httpx.AsyncClient,
    status_url: str,
    expected_status: str,
    config: IngestionBenchmarkConfig,
) -> dict[str, Any]:
    deadline = time.perf_counter() + config.worker_timeout_seconds
    while time.perf_counter() < deadline:
        response = await client.get(status_url)
        if response.status_code != 200:
            raise RuntimeError(f"job query returned {response.status_code}")
        body = response.json()
        status = body.get("status")
        if status == expected_status:
            return body
        if status == "failed":
            raise RuntimeError(f"asynchronous job failed with {body.get('error_code')}")
        if expected_status == "running" and status == "ready":
            raise RuntimeError("job completed before responsiveness probes began")
        await asyncio.sleep(config.poll_interval_seconds)
    raise RuntimeError(f"job did not reach {expected_status} before timeout")


async def _measure_crash_recovery(
    project_root: Path,
    root: Path,
    collection: str,
    client: httpx.AsyncClient,
    vector_store: Any,
    config: IngestionBenchmarkConfig,
) -> dict[str, Any]:
    accepted = await _accept_async(client, "crash-recovery", config)
    crash_result = await asyncio.to_thread(
        _run_worker_once,
        project_root,
        "crash",
        root,
        collection,
        config,
    )
    if crash_result.returncode != 91:
        raise RuntimeError(
            "crash Worker returned an unexpected code: "
            f"{crash_result.returncode} {crash_result.stdout[-500:]}"
        )
    crashed_job = await _wait_for_job_status(
        client,
        accepted.status_url,
        "running",
        config,
    )
    crashed_document_response = await client.get(
        f"/api/v1/documents/{accepted.document_id}"
    )
    if crashed_document_response.status_code != 200:
        raise RuntimeError("document could not be queried after Worker crash")
    crashed_document = crashed_document_response.json()
    recovery_started = time.perf_counter()
    recovery_result = await asyncio.to_thread(
        _run_worker_once,
        project_root,
        "recover",
        root,
        collection,
        config,
    )
    recovery_ms = (time.perf_counter() - recovery_started) * 1000
    if recovery_result.returncode != 0:
        raise RuntimeError(
            "recovery Worker failed: "
            f"{recovery_result.returncode} {recovery_result.stdout[-500:]}"
        )
    ready_job = await _wait_for_job_status(
        client,
        accepted.status_url,
        "ready",
        config,
    )
    document_response = await client.get(f"/api/v1/documents/{accepted.document_id}")
    if document_response.status_code != 200:
        raise RuntimeError("recovered document could not be queried")
    document = document_response.json()
    results = await asyncio.to_thread(
        vector_store.search,
        [1.0, 0.0, 0.0],
        [accepted.document_id],
        100,
    )
    chunk_ids = [str(result.chunk_id) for result in results]
    passed = (
        crashed_job["status"] == "running"
        and crashed_document["status"] == "processing"
        and ready_job["status"] == "ready"
        and ready_job["attempt_count"] == 2
        and document["status"] == "ready"
        and len(results) == document["chunk_count"]
        and len(set(chunk_ids)) == len(chunk_ids)
    )
    return {
        "supported_by_synchronous_v1": False,
        "passed": passed,
        "crash_exit_code": crash_result.returncode,
        "state_after_crash": {
            "job": crashed_job["status"],
            "document": crashed_document["status"],
        },
        "recovery_ms": round(recovery_ms, 4),
        "final_job_status": ready_job["status"],
        "final_document_status": document["status"],
        "attempt_count": ready_job["attempt_count"],
        "visible_chunk_count": len(results),
        "unique_visible_chunk_count": len(set(chunk_ids)),
    }


def _settings(
    root: Path,
    collection: str,
    config: IngestionBenchmarkConfig,
) -> Settings:
    return Settings(
        sqlite_path=root / "app.db",
        upload_dir=root / "uploads",
        qdrant_path=root / "unused-local-qdrant",
        qdrant_url=config.qdrant_url,
        qdrant_collection=collection,
        qdrant_timeout_seconds=config.qdrant_timeout_seconds,
        embedding_dimensions=config.vector_size,
        max_upload_bytes=config.document_size_bytes + 1024,
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
    )


def _document_bytes(label: str, config: IngestionBenchmarkConfig) -> bytes:
    line = (
        f"R4 synthetic policy evidence for {label}. "
        "This text is generated locally and contains no user data.\n"
    ).encode()
    repeats = (config.document_size_bytes // len(line)) + 1
    return (line * repeats)[: config.document_size_bytes]


def _mode_report(
    samples: _ModeSamples,
    config: IngestionBenchmarkConfig,
) -> dict[str, Any]:
    single_acceptance = summarize_timings(samples.acceptance_ms)
    return {
        "single": {
            "acceptance_ms": asdict(single_acceptance),
            "end_to_end_ms": asdict(summarize_timings(samples.end_to_end_ms)),
            "raw_acceptance_ms": _rounded(samples.acceptance_ms),
            "raw_end_to_end_ms": _rounded(samples.end_to_end_ms),
        },
        "responsiveness": {
            "health_ms": asdict(summarize_timings(samples.health_ms)),
            "status_codes": samples.health_status_codes,
            "all_probes_succeeded": all(
                status == 200 for status in samples.health_status_codes
            ),
            "raw_health_ms": _rounded(samples.health_ms),
        },
        "sequential_batch": {
            "rounds": config.batch_rounds,
            "documents_per_round": config.batch_size,
            "per_request_acceptance_ms": asdict(
                summarize_timings(samples.batch_acceptance_ms)
            ),
            "all_responses_ms": asdict(
                summarize_timings(samples.batch_response_total_ms)
            ),
            "all_ready_ms": asdict(summarize_timings(samples.batch_ready_total_ms)),
            "raw_all_responses_ms": _rounded(samples.batch_response_total_ms),
            "raw_all_ready_ms": _rounded(samples.batch_ready_total_ms),
        },
        "request_budget": {
            "budget_ms": config.request_budget_ms,
            "acceptance_p95_exceeds_budget": (
                single_acceptance.p95_ms > config.request_budget_ms
            ),
        },
    }


def _configuration(config: IngestionBenchmarkConfig) -> dict[str, Any]:
    return {
        "document_type": "synthetic-txt",
        "document_size_bytes": config.document_size_bytes,
        "embedding_delay_ms": config.embedding_delay_ms,
        "embedding_dimensions": config.vector_size,
        "chunk_size": config.chunk_size,
        "chunk_overlap": config.chunk_overlap,
        "warmup_samples_per_mode": config.warmup_samples,
        "single_samples_per_mode": config.single_samples,
        "batch_rounds": config.batch_rounds,
        "batch_size": config.batch_size,
        "health_probes_per_mode": config.health_probes,
        "async_poll_interval_ms": config.poll_interval_ms,
        "request_budget_ms": config.request_budget_ms,
    }


def _complexity_report() -> dict[str, Any]:
    return {
        "synchronous_v1": {
            "runtime_services": 2,
            "runtime_service_names": ["api", "qdrant"],
            "persisted_lifecycle_objects": ["Document"],
            "completion_http_interactions": ["POST /api/v1/documents"],
            "recovery_responsibilities": ["in-request compensating rollback"],
        },
        "asynchronous_v2": {
            "runtime_services": 3,
            "runtime_service_names": ["api", "worker", "qdrant"],
            "persisted_lifecycle_objects": ["Document", "IngestionJob"],
            "completion_http_interactions": [
                "POST /api/v2/documents",
                "GET /api/v2/jobs/{job_id}",
            ],
            "recovery_responsibilities": [
                "atomic claim",
                "startup recovery",
                "replay cleanup",
                "status polling",
            ],
        },
        "new_failure_surfaces": [
            "API and Worker contend on SQLite",
            "Worker lifecycle must be supervised",
            "Qdrant success can precede SQLite readiness",
            "clients must poll a second resource",
        ],
    }


def _worker_command(
    project_root: Path,
    mode: str,
    root: Path,
    collection: str,
    config: IngestionBenchmarkConfig,
    max_jobs: int | None = None,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "evaluation.ingestion_benchmark_worker",
        mode,
        "--database",
        str(root / "app.db"),
        "--upload-dir",
        str(root / "uploads"),
        "--qdrant-url",
        config.qdrant_url,
        "--collection",
        collection,
        "--vector-size",
        str(config.vector_size),
        "--chunk-size",
        str(config.chunk_size),
        "--chunk-overlap",
        str(config.chunk_overlap),
        "--embedding-delay-ms",
        str(config.embedding_delay_ms),
        "--poll-interval-ms",
        str(config.poll_interval_ms),
        "--timeout-seconds",
        str(config.worker_timeout_seconds),
    ]
    if max_jobs is not None:
        command.extend(("--max-jobs", str(max_jobs)))
    return command


def _start_worker_process(
    project_root: Path,
    *,
    mode: str,
    root: Path,
    collection: str,
    config: IngestionBenchmarkConfig,
    max_jobs: int,
) -> _RunningWorker:
    log_path = root / "worker-process.log"
    log_stream = log_path.open("w", encoding="utf-8")
    try:
        process = subprocess.Popen(
            _worker_command(
                project_root,
                mode,
                root,
                collection,
                config,
                max_jobs,
            ),
            cwd=project_root,
            stdout=log_stream,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except BaseException:
        log_stream.close()
        raise
    return _RunningWorker(
        process=process,
        log_path=log_path,
        log_stream=log_stream,
    )


def _wait_for_worker(
    worker: _RunningWorker,
    timeout_seconds: float,
) -> None:
    try:
        worker.process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        _terminate_worker(worker)
        raise RuntimeError("benchmark Worker did not finish") from exc
    worker.log_stream.close()
    if worker.process.returncode != 0:
        output = _read_worker_log_tail(worker.log_path)
        raise RuntimeError(
            f"benchmark Worker exited with {worker.process.returncode}: {output}"
        )


def _terminate_worker(worker: _RunningWorker) -> None:
    try:
        if worker.process.poll() is None:
            worker.process.terminate()
            try:
                worker.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker.process.kill()
                worker.process.wait(timeout=5)
    finally:
        if not worker.log_stream.closed:
            worker.log_stream.close()


def _read_worker_log_tail(log_path: Path, limit: int = 1000) -> str:
    try:
        return log_path.read_text(encoding="utf-8", errors="replace")[-limit:]
    except OSError:
        return "<worker log unavailable>"


def _run_worker_once(
    project_root: Path,
    mode: str,
    root: Path,
    collection: str,
    config: IngestionBenchmarkConfig,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        _worker_command(project_root, mode, root, collection, config),
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=config.worker_timeout_seconds,
    )


def _wait_for_qdrant(config: IngestionBenchmarkConfig) -> None:
    deadline = time.monotonic() + min(config.worker_timeout_seconds, 15)
    while time.monotonic() < deadline:
        try:
            with urlopen(
                f"{config.qdrant_url.rstrip('/')}/readyz",
                timeout=1,
            ) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.25)
    raise RuntimeError("local Qdrant Server is not ready")


def _read_qdrant_version(config: IngestionBenchmarkConfig) -> str:
    try:
        with urlopen(config.qdrant_url, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return str(payload.get("version", "unknown"))
    except (OSError, ValueError, json.JSONDecodeError):
        return "unknown"


def _safe_endpoint(url: str) -> str:
    parsed = urlsplit(url)
    host = parsed.hostname or "unknown"
    port = f":{parsed.port}" if parsed.port is not None else ""
    return f"{parsed.scheme}://{host}{port}"


def _rounded(values: list[float]) -> list[float]:
    return [round(value, 4) for value in values]
