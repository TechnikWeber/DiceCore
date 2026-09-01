"""
Training as a background job the web UI can watch.

Requirements this shape comes from: training takes minutes, the browser must be able to
close and come back, and a run must be cancellable without killing the service that also
serves the API a game is talking to. So: one thread, an append-only log, and a snapshot
any request can read.

One run at a time, on purpose. Two runs on one machine make both slow and the second one's
model overwrite the first one's for no benefit.
"""

from __future__ import annotations

import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import Settings
from ..dataset.store import DatasetStore

#: Keep the log bounded — a long run must not grow memory on a Pi without limit.
MAX_LOG = 400


class JobState:
    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TrainingJob:
    id: str
    set_id: str
    epochs: int
    state: str = JobState.IDLE
    started: float = field(default_factory=time.time)
    finished: float | None = None
    #: Latest progress dict from the trainer: epoch, loss, accuracy, stage.
    progress: dict[str, Any] = field(default_factory=dict)
    log: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    model_path: str | None = None
    accuracy: float | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id, "set_id": self.set_id, "epochs": self.epochs, "state": self.state,
            "started": self.started, "finished": self.finished, "progress": self.progress,
            "log": self.log, "error": self.error, "model_path": self.model_path,
            "accuracy": self.accuracy,
            "elapsed_s": round((self.finished or time.time()) - self.started, 1),
        }


class TrainingManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = threading.Lock()
        self._job: TrainingJob | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def job(self) -> TrainingJob | None:
        return self._job

    def is_running(self) -> bool:
        return self._job is not None and self._job.state == JobState.RUNNING

    def start(self, set_id: str, epochs: int = 30, name: str = "") -> TrainingJob:
        from .trainer import torch_available

        with self._lock:
            if self.is_running():
                raise RuntimeError("A training run is already going. Stop it first.")
            ok, why = torch_available()
            if not ok:
                raise RuntimeError(why)

            stamp = time.strftime("%Y%m%d-%H%M%S")
            out_dir = self.settings.models_dir / (name or f"{set_id}-{stamp}")
            job = TrainingJob(id=out_dir.name, set_id=set_id, epochs=epochs,
                              state=JobState.RUNNING)
            self._job = job
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run, args=(job, out_dir), name="dicecore-training", daemon=True
            )
            self._thread.start()
            return job

    def stop(self) -> None:
        """Ask the run to finish after the current epoch. The best model so far is kept."""
        self._stop.set()

    def _run(self, job: TrainingJob, out_dir: Path) -> None:
        from .trainer import train_model

        def progress(fields: dict[str, Any]) -> None:
            job.progress = fields
            job.log.append({"at": time.time(), **fields})
            del job.log[:-MAX_LOG]

        try:
            store = DatasetStore(self.settings.dataset_dir)
            meta = train_model(
                store, job.set_id, out_dir, epochs=job.epochs,
                progress=progress, should_stop=self._stop.is_set,
            )
            job.accuracy = meta.accuracy
            job.model_path = str(out_dir)
            job.state = JobState.CANCELLED if self._stop.is_set() else JobState.DONE
        except Exception as exc:
            job.state = JobState.FAILED
            job.error = f"{type(exc).__name__}: {exc}"
            job.log.append({"at": time.time(), "stage": "failed",
                            "message": traceback.format_exc(limit=3)})
        finally:
            job.finished = time.time()
