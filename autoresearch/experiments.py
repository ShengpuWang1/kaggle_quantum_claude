"""Persistent experiment records and resumable lifecycle checkpoints."""

from __future__ import annotations

import json
import os
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .artifacts import atomic_json
from .config import ROOT, redact


class ExperimentError(RuntimeError):
    """Raised for an invalid experiment state or resume request."""


TERMINAL_STATES = {"promoted", "rejected", "failed"}
TRANSITIONS = {
    "new": {"planned", "failed"},
    "planned": {"implementing", "failed"},
    "implementing": {"checks", "failed"},
    "checks": {"smoke", "implementing", "rejected", "failed"},
    "smoke": {"reviewing", "implementing", "rejected", "failed"},
    "reviewing": {"implementing", "full", "rejected", "failed"},
    "full": {"promoted", "rejected", "failed"},
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def new_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"EXP-{timestamp}-{secrets.token_hex(3)}"


class Experiment:
    def __init__(self, directory: Path, workspace: Path):
        self.directory = directory
        self.workspace = workspace
        self.metadata_path = directory / "metadata.json"
        self.events_path = directory / "events.jsonl"

    @classmethod
    def create(cls, root: Path, public_config: dict) -> Experiment:
        experiment_id = new_id()
        directory = root / "autoresearch" / "experiments" / experiment_id
        workspace = root / "autoresearch" / "workspaces" / experiment_id
        directory.mkdir(parents=True, exist_ok=False)
        workspace.mkdir(parents=True, exist_ok=False)
        experiment = cls(directory, workspace)
        experiment.save(
            {
                "schema_version": 1,
                "experiment_id": experiment_id,
                "created_at": utc_now(),
                "status": "new",
                "task": None,
                "parent_id": None,
                "config": public_config,
                "cycles": [],
            }
        )
        experiment.event("created")
        return experiment

    @classmethod
    def load(cls, root: Path, experiment_id: str) -> Experiment:
        if not re.fullmatch(r"EXP-[A-Za-z0-9-]+", experiment_id):
            raise ExperimentError("Invalid experiment identifier")
        directory = root / "autoresearch" / "experiments" / experiment_id
        workspace = root / "autoresearch" / "workspaces" / experiment_id
        experiment = cls(directory, workspace)
        metadata = experiment.metadata
        if metadata.get("schema_version") != 1:
            raise ExperimentError("Unsupported experiment metadata version")
        return experiment

    @property
    def experiment_id(self) -> str:
        return self.directory.name

    @property
    def metadata(self) -> dict[str, Any]:
        try:
            return json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ExperimentError(f"Cannot read {self.metadata_path}: {exc}") from exc

    def save(self, metadata: dict[str, Any]) -> None:
        metadata = dict(metadata)
        metadata["updated_at"] = utc_now()
        atomic_json(self.metadata_path, metadata)

    def update(self, **values: Any) -> dict[str, Any]:
        metadata = self.metadata
        metadata.update(values)
        self.save(metadata)
        return metadata

    def transition(self, target: str) -> None:
        metadata = self.metadata
        current = metadata["status"]
        if target not in TRANSITIONS.get(current, set()):
            raise ExperimentError(f"Invalid state transition: {current} -> {target}")
        self.update(status=target)
        self.event("state", previous=current, state=target)

    def event(self, kind: str, **values: Any) -> None:
        record = {"time": utc_now(), "kind": kind, **redact(values)}
        line = json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n"
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())

    def write_json(self, name: str, value: Any) -> None:
        atomic_json(self.directory / name, redact(value))

    def append_cycle(self, cycle: dict[str, Any]) -> None:
        metadata = self.metadata
        metadata.setdefault("cycles", []).append(cycle)
        self.save(metadata)

    def replace_last_cycle(self, cycle: dict[str, Any]) -> None:
        metadata = self.metadata
        if not metadata.get("cycles"):
            raise ExperimentError("No implementation cycle to update")
        metadata["cycles"][-1] = cycle
        self.save(metadata)

    def require_resumable(self) -> dict[str, Any]:
        metadata = self.metadata
        if metadata["status"] in TERMINAL_STATES:
            raise ExperimentError(
                f"{self.experiment_id} is terminal ({metadata['status']}) and cannot be resumed"
            )
        if metadata["status"] == "full":
            raise ExperimentError(
                "Resume after full verification is intentionally disabled; inspect the experiment"
            )
        return metadata


def list_experiments(root: Path = ROOT) -> list[dict[str, Any]]:
    directory = root / "autoresearch" / "experiments"
    records = []
    if not directory.exists():
        return records
    for path in sorted(directory.iterdir(), reverse=True):
        metadata = path / "metadata.json"
        if not metadata.is_file():
            continue
        try:
            records.append(json.loads(metadata.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            records.append({"experiment_id": path.name, "status": "unreadable"})
    return records
