"""Per-task champion state and deterministic promotion."""

from __future__ import annotations

import fcntl
import json
import math
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .artifacts import (
    atomic_json,
    candidate_files,
    copy_task,
    manifest,
    sha256,
    tree_manifest,
    verify_manifest,
)
from .config import ROOT, TASKS


class ChampionError(RuntimeError):
    """Raised when champion initialization or promotion is unsafe."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class ChampionStore:
    def __init__(self, root: Path = ROOT):
        self.root = root
        self.directory = root / "autoresearch" / "champions"
        self.reference_path = root / "autoresearch" / "reference_costs.json"
        self.lock_path = self.directory / ".lock"

    @contextmanager
    def lock(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+b") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def references(self) -> dict:
        return json.loads(self.reference_path.read_text(encoding="utf-8"))["tasks"]

    def current(self, task: str) -> dict:
        if task not in TASKS:
            raise ChampionError(f"Unknown task: {task}")
        path = self.directory / task / "current.json"
        if not path.is_file():
            raise ChampionError(f"No {task} champion; run scripts/orchestrate.py init")
        return json.loads(path.read_text(encoding="utf-8"))

    def generation_dir(self, champion: dict) -> Path:
        task = champion["task"]
        generation = champion["champion_id"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", generation):
            raise ChampionError("Invalid champion identifier")
        return self.directory / task / "generations" / generation

    def artifact_dir(self, task: str) -> Path:
        return self.generation_dir(self.current(task)) / "artifacts"

    def source_dir(self, task: str) -> Path:
        return self.generation_dir(self.current(task)) / "source"

    def costs(self) -> dict[str, float]:
        return {task: float(self.current(task)["cost"]) for task in TASKS}

    def initialize(self) -> list[dict]:
        created = []
        with self.lock():
            for task in TASKS:
                current_path = self.directory / task / "current.json"
                if current_path.exists():
                    continue
                created.append(self._initialize_task(task))
        return created

    def _initialize_task(self, task: str) -> dict:
        reference = self.references()[task]
        result_path = self.root / reference["result"]
        result = json.loads(result_path.read_text(encoding="utf-8"))
        cost = float(reference["cost"])
        if result.get("status") != "PASS" or not math.isfinite(cost) or cost <= 0:
            raise ChampionError(f"Invalid full reference record for {task}: {result_path}")
        if not math.isclose(float(result["score"]), cost, rel_tol=1e-12):
            raise ChampionError(f"Reference cost mismatch for {task}")
        official = self.root / "data" / "official" / "sample_submission"
        if task in {"invsqrt", "dqi"}:
            circuit = next(official.glob(f"{task}.km*"))
            actual_hash = sha256(circuit)
            if actual_hash != reference["artifact_sha256"]:
                raise ChampionError(f"Official {task} artifact hash does not match its reference")
            if result.get("circuit_sha256") != actual_hash:
                raise ChampionError(f"Reference result is not bound to official {task}")
        elif result.get("submission_sha256") != reference["submission_sha256"]:
            raise ChampionError("Chemistry reference result hash mismatch")
        self._validate_official_provenance(task, official)

        generation = self.directory / task / "generations" / "baseline"
        artifacts = generation / "artifacts"
        if generation.exists():
            raise ChampionError(f"Partial champion generation already exists: {generation}")
        copy_task(official, task, artifacts)
        source = generation / "source"
        source.mkdir(parents=True)
        (source / "STARTING_POINT.md").write_text(
            "# Official baseline\n\n"
            "The reference generator is in `data/official/verifiers/`. "
            "Create the configured build entrypoint in this source directory.\n",
            encoding="utf-8",
        )
        candidate_manifest = manifest(artifacts, task)
        champion = {
            "schema_version": 1,
            "champion_id": "baseline",
            "task": task,
            "parent_id": None,
            "created_at": utc_now(),
            "cost": cost,
            "reference_cost": cost,
            "artifacts": candidate_manifest,
            "source": tree_manifest(source),
            "verification": {
                "mode": "full",
                "result": str(result_path.relative_to(self.root)),
                "result_sha256": sha256(result_path),
            },
            "provenance": "Official sample submission and pinned local full-verifier record",
        }
        atomic_json(self.directory / task / "current.json", champion)
        return champion

    def _validate_official_provenance(self, task: str, official: Path) -> None:
        provenance_path = self.root / "docs" / "competition" / "provenance.json"
        records = json.loads(provenance_path.read_text(encoding="utf-8"))["files"]
        for path in candidate_files(official, task):
            relative = path.relative_to(self.root).as_posix()
            expected = records.get(relative)
            if not expected or sha256(path) != expected["sha256"]:
                raise ChampionError(f"Official artifact failed provenance validation: {relative}")

    def promote(
        self,
        *,
        task: str,
        experiment_id: str,
        parent_id: str,
        candidate_dir: Path,
        source_dir: Path,
        candidate_manifest: dict,
        metrics: dict,
        result_path: Path,
    ) -> dict:
        if metrics.get("status") != "PASS":
            raise ChampionError("Only PASS verification results can be promoted")
        cost = float(metrics.get("score", math.nan))
        if not math.isfinite(cost) or cost <= 0:
            raise ChampionError("Candidate has no finite positive cost")
        with self.lock():
            current = self.current(task)
            if current["champion_id"] != parent_id:
                raise ChampionError(
                    f"Stale parent: experiment has {parent_id}, current is {current['champion_id']}"
                )
            if candidate_manifest["digest"] == current["artifacts"]["digest"]:
                raise ChampionError("Candidate bytes are unchanged from the champion")
            if cost >= float(current["cost"]):
                raise ChampionError(
                    f"Candidate cost {cost} is not below champion cost {current['cost']}"
                )
            verify_manifest(candidate_dir, candidate_manifest)
            generation_id = experiment_id
            generation = self.directory / task / "generations" / generation_id
            if generation.exists():
                raise ChampionError(f"Champion generation already exists: {generation}")
            artifacts = generation / "artifacts"
            copy_task(candidate_dir, task, artifacts)
            copied_manifest = manifest(artifacts, task)
            if copied_manifest["digest"] != candidate_manifest["digest"]:
                raise ChampionError("Promoted artifact copy failed its hash check")
            target_source = generation / "source"
            if source_dir.exists():
                shutil.copytree(source_dir, target_source)
            else:
                target_source.mkdir(parents=True)
            champion = {
                "schema_version": 1,
                "champion_id": generation_id,
                "task": task,
                "parent_id": parent_id,
                "created_at": utc_now(),
                "cost": cost,
                "reference_cost": current["reference_cost"],
                "artifacts": copied_manifest,
                "source": tree_manifest(target_source),
                "verification": {
                    "mode": "full",
                    "result": str(result_path.relative_to(self.root)),
                    "result_sha256": sha256(result_path),
                },
                "provenance": f"Promoted from {experiment_id}",
            }
            atomic_json(self.directory / task / "current.json", champion)
            return champion

    def package_portfolio(self, output: Path) -> dict:
        from scripts.package_submission import package

        output = output.resolve()
        output.relative_to(self.root)
        with tempfile.TemporaryDirectory(
            prefix="portfolio-", dir=self.root / ".cache"
        ) as temporary:
            portfolio = Path(temporary)
            provenance = {}
            for task in TASKS:
                champion = self.current(task)
                source = self.generation_dir(champion) / "artifacts"
                for path in candidate_files(source, task):
                    relative = path.relative_to(source)
                    target = portfolio / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.symlink(path, target)
                provenance[task] = {
                    "champion_id": champion["champion_id"],
                    "cost": champion["cost"],
                    "artifact_digest": champion["artifacts"]["digest"],
                }
            package(portfolio, output)
        atomic_json(output.with_suffix(".research.json"), {"champions": provenance})
        return provenance
