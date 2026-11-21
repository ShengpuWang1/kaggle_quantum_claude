"""Deterministic build/test execution and official-verifier integration."""

from __future__ import annotations

import os
import secrets
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from scripts.autoresearch_verifier import public_command, run_verification

from .artifacts import atomic_json, sha256
from .config import ROOT, Settings, TaskRecipe


class VerificationError(RuntimeError):
    """Raised when verification cannot produce a trustworthy result."""


def _public_environment() -> dict[str, str]:
    environment = os.environ.copy()
    sensitive = ("API_KEY", "AUTH_TOKEN", "SECRET", "PASSWORD", "_SALT")
    for key in list(environment):
        if any(part in key.upper() for part in sensitive):
            environment.pop(key, None)
    return environment


def _kill_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def run_recipe(
    recipe: TaskRecipe,
    *,
    workspace: Path,
    log_directory: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Run configured argument arrays without a shell, stopping at the first failure."""
    log_directory.mkdir(parents=True, exist_ok=False)
    commands = [("build", recipe.build)] if recipe.build else []
    commands += [("test", command) for command in recipe.tests]
    records = []
    for index, (kind, configured) in enumerate(commands):
        command = [
            part.replace("{python}", sys.executable).replace(
                "{workspace}", str(workspace)
            )
            for part in configured
        ]
        stem = f"{index:02d}-{kind}"
        stdout_path = log_directory / f"{stem}.log"
        start = time.monotonic()
        timed_out = False
        with stdout_path.open("wb") as output:
            process = subprocess.Popen(
                command,
                cwd=workspace,
                env=_public_environment(),
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                returncode = process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_group(process)
                returncode = process.wait()
        records.append(
            {
                "kind": kind,
                "command": public_command(command),
                "returncode": returncode,
                "seconds": time.monotonic() - start,
                "timed_out": timed_out,
                "log": stdout_path.name,
            }
        )
        if returncode != 0:
            break
    result = {"ok": bool(records) and all(r["returncode"] == 0 for r in records)}
    if not commands:
        result = {"ok": True, "note": "No build or test commands configured"}
    result["commands"] = records
    result["log_directory"] = str(log_directory)
    atomic_json(log_directory / "commands.json", result)
    return result


class VerificationRunner:
    def __init__(self, root: Path = ROOT, settings: Settings | None = None):
        self.root = root
        self.settings = settings or Settings()

    def _full_salt(self, experiment_id: str) -> str:
        path = (
            self.root
            / ".secrets"
            / "autoresearch"
            / "salts"
            / f"{experiment_id}.txt"
        )
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        path.parent.mkdir(parents=True, exist_ok=True)
        value = secrets.token_urlsafe(32)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(value)
        return value

    def verify(
        self,
        *,
        workspace: Path,
        task: str,
        full: bool,
        run_directory: Path,
        experiment_id: str,
    ) -> dict[str, Any]:
        variable = "AUTORESEARCH_VALIDATION_SALT"
        previous = os.environ.get(variable)
        salt = self._full_salt(experiment_id) if full else None
        if salt is not None:
            os.environ[variable] = salt
        try:
            _, results = run_verification(
                source=workspace,
                full=full,
                task=task,
                workers=self.settings.workers,
                run_dir=run_directory,
                salt_env=variable if full else None,
                timeout_seconds=(
                    self.settings.full_timeout_seconds
                    if full
                    else self.settings.smoke_timeout_seconds
                ),
                fail_fast=True,
            )
        finally:
            if salt is not None:
                if previous is None:
                    os.environ.pop(variable, None)
                else:
                    os.environ[variable] = previous
        record = results["tasks"].get(task)
        if not record:
            raise VerificationError(f"Official verifier returned no {task} record")
        result_path = run_directory / f"{task}.json"
        metrics = {
            "mode": "full" if full else "smoke",
            "status": record["status"],
            "returncode": record["returncode"],
            "timed_out": record["timed_out"],
            "seconds": record["seconds"],
            "run_directory": str(run_directory.relative_to(self.root)),
            "result": str(result_path.relative_to(self.root)),
            "result_sha256": sha256(result_path),
        }
        if record["status"] == "PASS":
            metrics["score"] = record["score"]
        return metrics
