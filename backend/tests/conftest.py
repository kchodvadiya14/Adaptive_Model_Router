"""Shared pytest fixtures.

Test isolation
--------------
The application keeps persistent state in files resolved relative to the working
directory: the SQLite database (routing logs, benchmark reports, jobs, model health),
the model registry JSON, and dataset / report / trained-model directories. None of it
may leak into or out of tests:

- `isolated_state` (autouse, per test) points DATABASE_URL at a fresh temporary SQLite
  file, gives the registry singleton a fresh copy of the default models, redirects the
  file-output directories to a temporary tree, and resets cached job managers. Every
  test starts with no routing logs, jobs, or model-health rows, and needs no cleanup.
  Tests that set up their own temp DB or registry still override this, because their
  fixtures run after the autouse one.
- `guard_persistent_state` (autouse, session) fingerprints the persistent locations the
  app would use outside of tests before the run and fails the session if any of them
  changed afterwards.

Production configuration is untouched: everything here is monkeypatching inside the
test process.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

import pytest


# --- Session guard: tests must never touch persistent developer state ----------------


@dataclass(frozen=True)
class PersistentPaths:
    database: Path
    registry: Path
    output_dirs: tuple[Path, ...]


def _configured_persistent_paths() -> PersistentPaths:
    """What the app would use outside tests — read before any test changes the env."""
    from app.config.settings import Settings
    from app.datasets import storage
    from app.evaluation import experiment_reports, reports
    from app.training import registry as training_registry

    database_url = Settings().database_url
    database = Path(database_url.replace("sqlite:///", "", 1)) if database_url.startswith("sqlite:///") else None
    return PersistentPaths(
        database=database.resolve() if database else Path(os.devnull),
        registry=Path("data/processed/model_registry.json").resolve(),
        output_dirs=tuple(
            path.resolve()
            for path in (
                storage.DATASETS_DIR,
                experiment_reports.REPORTS_DIR,
                reports.REPORTS_DIR,
                training_registry.MODELS_DIR,
            )
        ),
    )


def _file_fingerprint(path: Path) -> tuple | None:
    if not path.is_file():
        return None
    return (path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest())


def _dir_fingerprint(path: Path) -> tuple:
    if not path.is_dir():
        return ()
    return tuple(
        (str(item.relative_to(path)), *_file_fingerprint(item))
        for item in sorted(path.rglob("*"))
        if item.is_file()
    )


def _fingerprint(paths: PersistentPaths) -> dict[str, tuple | None]:
    snapshot: dict[str, tuple | None] = {
        str(paths.database): _file_fingerprint(paths.database),
        str(paths.registry): _file_fingerprint(paths.registry),
    }
    for directory in paths.output_dirs:
        snapshot[str(directory)] = _dir_fingerprint(directory)
    return snapshot


@pytest.fixture(scope="session")
def persistent_paths() -> PersistentPaths:
    return _configured_persistent_paths()


@pytest.fixture(scope="session", autouse=True)
def guard_persistent_state(persistent_paths: PersistentPaths):
    before = _fingerprint(persistent_paths)
    yield
    after = _fingerprint(persistent_paths)
    changed = sorted(location for location in before if before[location] != after.get(location))
    if changed:
        pytest.fail(
            "Tests modified persistent application state they must never touch: "
            + ", ".join(changed),
            pytrace=False,
        )


# --- Per-test isolation --------------------------------------------------------------


def use_isolated_database(directory: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the app at a fresh SQLite file under `directory`. The schema is created
    lazily by the existing init_db()/get_connection() path, exactly as in production."""
    from app.config.settings import get_settings

    db_path = directory / "router.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    get_settings.cache_clear()
    return db_path


@pytest.fixture(autouse=True)
def isolated_state(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch):
    from app.config.settings import get_settings
    from app.datasets import storage
    from app.evaluation import experiment_reports, reports
    from app.models.registry import ModelRegistry
    from app.services import dataset_jobs, experiment_jobs, jobs, training_jobs
    from app.training import registry as training_registry

    root = tmp_path_factory.mktemp("isolated_state")
    get_settings.cache_clear()

    use_isolated_database(root, monkeypatch)

    # Registry: the built-in defaults, never the git-tracked or locally edited JSON file.
    monkeypatch.setattr("app.models.registry._registry", ModelRegistry(registry_path=root / "model_registry.json"))

    # File outputs. The *_PATH constants are derived at import time, so patch them too.
    datasets_dir = root / "datasets"
    monkeypatch.setattr(storage, "DATASETS_DIR", datasets_dir)
    monkeypatch.setattr(storage, "INDEX_PATH", datasets_dir / "index.json")
    experiment_reports_dir = root / "experiment_reports"
    monkeypatch.setattr(experiment_reports, "REPORTS_DIR", experiment_reports_dir)
    monkeypatch.setattr(experiment_reports, "INDEX_PATH", experiment_reports_dir / "index.json")
    monkeypatch.setattr(reports, "REPORTS_DIR", root / "benchmark_reports")
    models_dir = root / "models"
    monkeypatch.setattr(training_registry, "MODELS_DIR", models_dir)
    monkeypatch.setattr(training_registry, "REGISTRY_PATH", models_dir / "registry.json")

    # Cached job managers sweep stale jobs when first built; rebuild them per test so that
    # sweep runs against this test's database rather than whichever one existed first.
    monkeypatch.setattr(jobs, "_job_manager", None)
    monkeypatch.setattr(dataset_jobs, "_manager", None)
    monkeypatch.setattr(training_jobs, "_manager", None)
    monkeypatch.setattr(experiment_jobs, "_manager", None)

    yield root
    get_settings.cache_clear()
