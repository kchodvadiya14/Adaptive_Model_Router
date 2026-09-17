"""Tests for the unified, SQLite-backed JobManager (Phase 1 Step 4).

All tests point DATABASE_URL at a throwaway per-test SQLite file so job rows never
leak into the shared dev database, and so "restart" can be simulated by simply
constructing a new JobManager against the same file.
"""

from __future__ import annotations

import asyncio
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.registry import ModelRegistry
from app.services.jobs import BenchmarkJobManager, JobManager

client = TestClient(app)


# --- Shared fixtures ----------------------------------------------------------------


@pytest.fixture
def temp_jobs_db(tmp_path, monkeypatch):
    """Point the app at a throwaway SQLite file and initialize its schema."""
    db_path = tmp_path / "jobs_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    from app.config.settings import get_settings

    get_settings.cache_clear()
    from app.db import database

    database.init_db()
    yield db_path
    get_settings.cache_clear()


def _read_row(db_path, job_id: str) -> sqlite3.Row | None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    conn.close()
    return row


@pytest.fixture
def temp_registry(tmp_path, monkeypatch):
    registry = ModelRegistry(registry_path=tmp_path / "model_registry.json")
    monkeypatch.setattr("app.models.registry._registry", registry)
    monkeypatch.setattr("app.datasets.generator.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.evaluation.benchmark.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.router.rule_based.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.router.policy.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.services.chat.get_model_registry", lambda: registry)
    return registry


@pytest.fixture
def temp_storage(tmp_path, monkeypatch):
    datasets_dir = tmp_path / "datasets"
    datasets_dir.mkdir()
    monkeypatch.setattr("app.datasets.storage.DATASETS_DIR", datasets_dir)
    monkeypatch.setattr("app.datasets.storage.INDEX_PATH", datasets_dir / "index.json")
    monkeypatch.setattr(
        "app.datasets.storage.dataset_path",
        lambda dataset_id: datasets_dir / f"{dataset_id}.jsonl",
    )
    return datasets_dir


@pytest.fixture
def sample_source(tmp_path):
    path = tmp_path / "source.json"
    path.write_text(
        '[{"id":"p1","prompt":"Explain Python lists.","category":"general_qa"},'
        '{"id":"p2","prompt":"Debug this code snippet.","category":"debugging"}]',
        encoding="utf-8",
    )
    return str(path)


def _reset_job_singletons(monkeypatch):
    """The compat wrappers cache a module-level singleton; force a fresh one per test
    so each test's temp_jobs_db is what actually gets used."""
    import app.services.jobs as jobs_module
    import app.services.dataset_jobs as dataset_jobs_module
    import app.services.training_jobs as training_jobs_module
    import app.services.experiment_jobs as experiment_jobs_module

    monkeypatch.setattr(jobs_module, "_job_manager", None)
    monkeypatch.setattr(dataset_jobs_module, "_manager", None)
    monkeypatch.setattr(training_jobs_module, "_manager", None)
    monkeypatch.setattr(experiment_jobs_module, "_manager", None)


# --- 1. Create job -> exists in SQLite -----------------------------------------------


def test_create_job_persists_to_sqlite(temp_jobs_db):
    manager = JobManager(job_type="unit_test")
    job_id = manager.create_job()

    row = _read_row(temp_jobs_db, job_id)
    assert row is not None
    assert row["job_type"] == "unit_test"
    assert row["status"] == "queued"
    assert row["progress"] == 0.0
    assert row["created_at"]
    assert row["started_at"] is None
    assert row["completed_at"] is None


# --- 2. Start job -> status changes correctly ----------------------------------------


@pytest.mark.asyncio
async def test_start_job_marks_running_synchronously(temp_jobs_db):
    manager = JobManager(job_type="unit_test")
    job_id = manager.create_job()

    async def work():
        return {"ok": True}

    manager.start_job(job_id, work)
    # mark_running happens synchronously inside start_job, before the scheduled
    # coroutine gets a chance to run.
    record = manager.get_job(job_id)
    assert record.status == "running"
    assert record.started_at is not None

    await asyncio.sleep(0.05)  # let the background task finish so it doesn't leak


# --- 3. Update progress -> progress persists -----------------------------------------


def test_update_progress_persists(temp_jobs_db):
    manager = JobManager(job_type="unit_test")
    job_id = manager.create_job()
    manager.mark_running(job_id)

    manager.update_progress(job_id, 0.42)

    record = manager.get_job(job_id)
    assert record.progress == 0.42
    assert record.status == "running"  # progress update alone doesn't change status


# --- 4. Complete job -> completed status + timestamp + result persist ----------------


@pytest.mark.asyncio
async def test_start_job_completes_and_persists_result(temp_jobs_db):
    manager = JobManager(job_type="unit_test")
    job_id = manager.create_job()

    async def work():
        return {"answer": 42}

    manager.start_job(job_id, work)
    await asyncio.sleep(0.05)

    record = manager.get_job(job_id)
    assert record.status == "completed"
    assert record.progress == 1.0
    assert record.result == {"answer": 42}
    assert record.error is None

    row = _read_row(temp_jobs_db, job_id)
    assert row["completed_at"] is not None
    assert row["result_json"] is not None


# --- 5. Fail job -> error information persists ----------------------------------------


@pytest.mark.asyncio
async def test_start_job_records_failure(temp_jobs_db):
    manager = JobManager(job_type="unit_test")
    job_id = manager.create_job()

    async def work():
        raise RuntimeError("boom")

    manager.start_job(job_id, work)
    await asyncio.sleep(0.05)

    record = manager.get_job(job_id)
    assert record.status == "failed"
    assert record.error == "boom"
    assert record.result is None

    row = _read_row(temp_jobs_db, job_id)
    assert row["completed_at"] is not None


# --- 6. Get job from a NEW JobManager instance ----------------------------------------


def test_new_manager_instance_sees_existing_job(temp_jobs_db):
    manager_a = JobManager(job_type="unit_test")
    job_id = manager_a.create_job()
    manager_a.mark_completed(job_id, {"value": 1})

    manager_b = JobManager(job_type="unit_test")  # fresh instance, same DB file
    record = manager_b.get_job(job_id)

    assert record is not None
    assert record.status == "completed"
    assert record.result == {"value": 1}


# --- 7. Simulated restart: running/queued jobs survive, but are never falsely --------
#        reported as completed ---------------------------------------------------------


def test_restart_marks_stale_running_job_failed_not_completed(temp_jobs_db):
    manager_a = JobManager(job_type="unit_test")
    running_job_id = manager_a.create_job()
    manager_a.mark_running(running_job_id)  # simulate: process died mid-job

    finished_job_id = manager_a.create_job()
    manager_a.mark_completed(finished_job_id, {"done": True})

    # Simulate a backend restart: a brand new JobManager for the same job_type/DB.
    manager_b = JobManager(job_type="unit_test")

    record = manager_b.get_job(running_job_id)
    assert record.status == "failed"
    assert record.status != "completed"
    assert "restart" in record.error.lower()

    # A job that genuinely finished before the "restart" must be untouched.
    finished = manager_b.get_job(finished_job_id)
    assert finished.status == "completed"
    assert finished.result == {"done": True}


def test_restart_marks_stale_queued_job_failed(temp_jobs_db):
    manager_a = JobManager(job_type="unit_test")
    job_id = manager_a.create_job()  # never started

    manager_b = JobManager(job_type="unit_test")

    record = manager_b.get_job(job_id)
    assert record.status == "failed"
    assert record.result is None


def test_restart_sweep_is_scoped_to_job_type(temp_jobs_db):
    """Restarting the manager for one job_type must not touch stale jobs of another."""
    manager_a = JobManager(job_type="type_a")
    job_id = manager_a.create_job()
    manager_a.mark_running(job_id)

    # "Restart" only type_b's manager; type_a's job must be untouched by it.
    JobManager(job_type="type_b")

    assert manager_a.get_job(job_id).status == "running"

    # Now actually restart type_a's manager: only then is the stale job swept.
    manager_a_restarted = JobManager(job_type="type_a")
    assert manager_a_restarted.get_job(job_id).status == "failed"


# --- 11. Unknown job ID: existing expected behavior preserved ------------------------


def test_unknown_job_id_get_returns_none(temp_jobs_db):
    manager = JobManager(job_type="unit_test")
    assert manager.get_job("does-not-exist") is None


def test_unknown_job_id_raises_keyerror_on_start(temp_jobs_db):
    manager = JobManager(job_type="unit_test")

    async def work():
        return {}

    with pytest.raises(KeyError):
        manager.start_job("does-not-exist", work)


def test_unknown_job_id_raises_keyerror_on_mark_methods(temp_jobs_db):
    manager = JobManager(job_type="unit_test")
    with pytest.raises(KeyError):
        manager.mark_running("does-not-exist")
    with pytest.raises(KeyError):
        manager.mark_completed("does-not-exist", {})
    with pytest.raises(KeyError):
        manager.mark_failed("does-not-exist", "error")


# --- 12. Existing *JobStatus response schemas remain compatible ----------------------


def test_benchmark_job_manager_returns_benchmark_job_status(temp_jobs_db):
    from app.schemas.evaluation import BenchmarkJobStatus

    manager = BenchmarkJobManager()
    job_id = manager.create_job()
    status = manager.get_job(job_id)

    assert isinstance(status, BenchmarkJobStatus)
    assert status.job_id == job_id
    assert status.status == "queued"
    assert status.progress == 0.0
    assert status.report is None


def test_dataset_job_manager_returns_dataset_job_status(temp_jobs_db):
    from app.schemas.dataset import DatasetGenerateJobStatus
    from app.services.dataset_jobs import DatasetJobManager

    manager = DatasetJobManager()
    job_id = manager.create_job()
    status = manager.get_job(job_id)

    assert isinstance(status, DatasetGenerateJobStatus)
    assert status.manifest is None


def test_training_job_manager_returns_training_job_status(temp_jobs_db):
    from app.schemas.training import TrainingJobStatus
    from app.services.training_jobs import TrainingJobManager

    manager = TrainingJobManager()
    job_id = manager.create_job()
    status = manager.get_job(job_id)

    assert isinstance(status, TrainingJobStatus)
    assert status.result is None


def test_experiment_job_manager_returns_experiment_job_status(temp_jobs_db):
    from app.schemas.experiments import ExperimentJobStatus
    from app.services.experiment_jobs import ExperimentJobManager

    manager = ExperimentJobManager()
    job_id = manager.create_job()
    status = manager.get_job(job_id)

    assert isinstance(status, ExperimentJobStatus)
    assert status.report is None

    manager.mark_running(job_id)
    assert manager.get_job(job_id).status == "running"


# --- 8/9/10. Dataset / training / benchmark / experiment jobs still work through -----
#             their existing HTTP APIs, and persist to SQLite -------------------------


def test_dataset_job_works_through_existing_api_and_persists(
    temp_registry, temp_storage, sample_source, temp_jobs_db, monkeypatch
):
    _reset_job_singletons(monkeypatch)

    # A bare `TestClient(app)` opens a fresh event loop per call, which orphans the
    # asyncio.create_task() the job runs on before it can finish — a pre-existing
    # property of this fire-and-forget execution model, not something Step 4 changes
    # (see module docstring: state persistence only, execution model unchanged). Using
    # the client as a context manager keeps one persistent loop across calls so the
    # background task actually gets to run, exactly like a real running server.
    with TestClient(app) as live_client:
        response = live_client.post(
            "/api/dataset/generate",
            json={"source_path": sample_source, "name": "job_test", "quality_floor": 0.85, "max_prompts": 2},
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        for _ in range(50):
            status_response = live_client.get(f"/api/dataset/generate/status/{job_id}")
            assert status_response.status_code == 200
            data = status_response.json()
            if data["status"] == "completed":
                assert data["manifest"] is not None
                break
            if data["status"] == "failed":
                pytest.fail(data.get("error"))
            time.sleep(0.05)
        else:
            pytest.fail("Dataset job did not complete in time")

    row = _read_row(temp_jobs_db, job_id)
    assert row["status"] == "completed"
    assert row["job_type"] == "dataset_generate"
    assert row["result_json"] is not None


def test_benchmark_job_works_through_existing_api_and_persists(
    temp_registry, sample_source, temp_jobs_db, tmp_path, monkeypatch
):
    _reset_job_singletons(monkeypatch)
    monkeypatch.setattr("app.evaluation.reports.REPORTS_DIR", tmp_path / "benchmark_reports")

    with TestClient(app) as live_client:
        response = live_client.post(
            "/api/benchmark",
            json={
                "dataset_path": sample_source,
                "strategies": ["always_cheap"],
                "quality_floor": 0.85,
                "max_prompts": 2,
            },
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        for _ in range(50):
            status_response = live_client.get(f"/api/benchmark/status/{job_id}")
            assert status_response.status_code == 200
            data = status_response.json()
            if data["status"] == "completed":
                assert data["report"] is not None
                break
            if data["status"] == "failed":
                pytest.fail(data.get("error"))
            time.sleep(0.05)
        else:
            pytest.fail("Benchmark job did not complete in time")

    row = _read_row(temp_jobs_db, job_id)
    assert row["status"] == "completed"
    assert row["job_type"] == "benchmark"


def test_training_job_works_through_existing_api_and_persists(
    temp_registry, temp_storage, temp_jobs_db, tmp_path, monkeypatch
):
    _reset_job_singletons(monkeypatch)

    models_dir = tmp_path / "models"
    models_dir.mkdir()
    monkeypatch.setattr("app.training.registry.MODELS_DIR", models_dir)
    monkeypatch.setattr("app.training.registry.REGISTRY_PATH", models_dir / "registry.json")
    monkeypatch.setattr(
        "app.training.registry.artifact_path",
        lambda model_id, router_type: models_dir / f"{router_type.value}_{model_id}.joblib",
    )

    from datetime import UTC, datetime
    import uuid

    from app.datasets.storage import add_manifest, save_records
    from app.schemas.dataset import DatasetManifest, PreferenceRecord

    dataset_id = str(uuid.uuid4())
    records = []
    for i in range(8):
        strong_wins = i % 2 == 0
        records.append(
            PreferenceRecord(
                id=f"r{i}",
                prompt=f"Explain concept {i} with examples and reasoning.",
                task_type="general_qa",
                difficulty=0.4 if not strong_wins else 0.8,
                small_model_id="mock-echo",
                medium_model_id="mock-echo-medium",
                strong_model_id="mock-echo-strong",
                small_response="short",
                medium_response="medium",
                strong_response="long detailed",
                small_score=0.72,
                medium_score=0.84,
                strong_score=0.94 if strong_wins else 0.78,
                preferred_model="strong" if strong_wins else "small",
                small_sufficient=not strong_wins,
                medium_sufficient=True,
                strong_sufficient=True,
                quality_floor=0.85,
            )
        )
    save_records(dataset_id, records)
    add_manifest(
        DatasetManifest(
            id=dataset_id,
            name="job_manager_training_test",
            created_at=datetime.now(UTC).isoformat(),
            source_path="test",
            output_path=str(dataset_id),
            quality_floor=0.85,
            record_count=len(records),
            judge_provider="mock",
        )
    )

    with TestClient(app) as live_client:
        response = live_client.post(
            "/api/training/start",
            json={"dataset_id": dataset_id, "router_type": "tfidf", "routing_threshold": 0.6},
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        for _ in range(100):
            status_response = live_client.get(f"/api/training/status/{job_id}")
            assert status_response.status_code == 200
            data = status_response.json()
            if data["status"] == "completed":
                assert data["result"] is not None
                break
            if data["status"] == "failed":
                pytest.fail(data.get("error"))
            time.sleep(0.1)
        else:
            pytest.fail("Training job did not complete in time")

    row = _read_row(temp_jobs_db, job_id)
    assert row["status"] == "completed"
    assert row["job_type"] == "training"
    assert row["result_json"] is not None


def test_experiment_job_works_through_existing_api_and_persists(
    temp_registry, sample_source, temp_jobs_db, tmp_path, monkeypatch
):
    _reset_job_singletons(monkeypatch)

    reports_dir = tmp_path / "reports"
    monkeypatch.setattr("app.evaluation.experiment_reports.REPORTS_DIR", reports_dir)
    monkeypatch.setattr("app.evaluation.experiment_reports.INDEX_PATH", reports_dir / "index.json")

    response = client.post(
        "/api/experiments/run",
        json={
            "experiment_type": "strategy_comparison",
            "dataset_path": sample_source,
            "max_prompts": 2,
            "strategies": ["always_cheap", "adaptive_router"],
        },
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    for _ in range(50):
        status_response = client.get(f"/api/experiments/status/{job_id}")
        assert status_response.status_code == 200
        data = status_response.json()
        if data["status"] == "completed":
            assert data["report"] is not None
            break
        if data["status"] == "failed":
            pytest.fail(data.get("error"))
        time.sleep(0.1)
    else:
        pytest.fail("Experiment job did not complete in time")

    row = _read_row(temp_jobs_db, job_id)
    assert row["status"] == "completed"
    assert row["job_type"] == "experiment"


# --- Restart survival through the HTTP-facing wrapper, not just the raw JobManager ----


def test_dataset_job_status_survives_manager_recreation_after_completion(
    temp_registry, temp_storage, sample_source, temp_jobs_db, monkeypatch
):
    """POST /api/dataset/generate, let it finish, then rebuild the wrapper (simulating
    a restart) and confirm GET .../status/{job_id} still returns it correctly."""
    _reset_job_singletons(monkeypatch)

    with TestClient(app) as live_client:
        response = live_client.post(
            "/api/dataset/generate",
            json={"source_path": sample_source, "name": "restart_test", "quality_floor": 0.85, "max_prompts": 2},
        )
        job_id = response.json()["job_id"]

        for _ in range(50):
            data = live_client.get(f"/api/dataset/generate/status/{job_id}").json()
            if data["status"] in ("completed", "failed"):
                break
            time.sleep(0.05)
        assert data["status"] == "completed"

    # Simulate restart: drop the cached singleton so the next call builds a new manager.
    _reset_job_singletons(monkeypatch)

    data_after_restart = client.get(f"/api/dataset/generate/status/{job_id}").json()
    assert data_after_restart["status"] == "completed"
    assert data_after_restart["manifest"] is not None
