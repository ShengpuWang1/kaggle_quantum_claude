"""Run unmodified official verifiers, preserving commands and results per run."""

import argparse
import datetime
import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def circuit_path(source, task):
    matches = [
        source / f"{task}.{extension}"
        for extension in ("kmb", "kmx")
        if (source / f"{task}.{extension}").is_file()
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one {task} .kmb or .kmx circuit in {source}; "
            f"found {len(matches)}"
        )
    return matches[0]


def build_commands(source, *, full, workers, salt=None, task="all"):
    source = source.resolve()
    verifiers = ROOT / "data/official/verifiers"
    commands = {}
    if task in ("all", "invsqrt"):
        commands["invsqrt"] = [
            str(verifiers / "invsqrt/verify_submission_invsqrt.py"),
            str(circuit_path(source, "invsqrt")),
            "--max-workers",
            str(workers),
        ]
    if task in ("all", "dqi"):
        commands["dqi"] = [
            str(verifiers / "dqi/verify_submission_dqi.py"),
            str(circuit_path(source, "dqi")),
            "--max-workers",
            str(workers),
        ]
    if task in ("all", "dfthcsos"):
        commands["dfthcsos"] = [
            str(verifiers / "dfthcsos/verify.py"), str(source / "dfthcsos")
        ]
    if not full:
        if "invsqrt" in commands:
            commands["invsqrt"] += ["--max-x", "4096"]
        if "dqi" in commands:
            commands["dqi"] += ["--num-shots", "4096"]
    if salt is not None:
        for command in commands.values():
            command += ["--salt", salt]
    return commands


def public_command(command):
    result = list(command)
    for index, value in enumerate(result[:-1]):
        if value in {"--salt", "--seed", "--api-key", "--token", "--password", "--secret"}:
            result[index + 1] = "<redacted>"
    return result


def _terminate(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _sanitized_environment(salt_env=None):
    environment = os.environ.copy()
    for key in list(environment):
        upper = key.upper()
        sensitive = any(
            part in upper for part in ("API_KEY", "AUTH_TOKEN", "SECRET", "PASSWORD", "_SALT")
        ) or upper.endswith("_TOKEN")
        if sensitive and key != salt_env:
            environment.pop(key, None)
    return environment


def run_verification(
    *,
    source,
    full=False,
    task="all",
    workers=1,
    run_dir=None,
    salt_env=None,
    timeout_seconds=None,
    fail_fast=False,
):
    source = Path(source).resolve()
    run = (
        Path(run_dir).resolve()
        if run_dir
        else ROOT
        / "runs"
        / datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%S%fZ")
    )
    if run.exists() and any(run.iterdir()):
        raise FileExistsError(f"Run directory is not empty: {run}")
    run.mkdir(parents=True, exist_ok=True)
    salt = None
    if salt_env:
        salt = os.environ.get(salt_env)
        if not salt:
            raise ValueError(f"Salt environment variable is not set: {salt_env}")
    commands = build_commands(source, full=full, workers=workers, salt=salt, task=task)
    results = {
        "schema_version": 2,
        "mode": "full" if full else "smoke (dfthcsos uses full defaults)",
        "source": str(source),
        "tasks": {},
    }
    if salt is not None:
        results["salt_sha256"] = hashlib.sha256(salt.encode()).hexdigest()
        results["salt_env"] = salt_env

    for name, command in commands.items():
        if task not in ("all", name):
            continue
        invocation = [sys.executable, *command]
        print(f"Running {name}; logs: {run}", flush=True)
        start = time.monotonic()
        timed_out = False
        with (
            (run / f"{name}.json").open("w") as out,
            (run / f"{name}.stderr").open("w") as err,
        ):
            process = subprocess.Popen(
                invocation,
                cwd=ROOT,
                stdout=out,
                stderr=err,
                env=_sanitized_environment(salt_env),
                start_new_session=True,
            )
            try:
                returncode = process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                _terminate(process)
                returncode = process.wait()
        seconds = time.monotonic() - start
        if salt is not None:
            for suffix in ("json", "stderr"):
                path = run / f"{name}.{suffix}"
                text = path.read_text(encoding="utf-8", errors="replace")
                if salt in text:
                    path.write_text(text.replace(salt, "<redacted>"), encoding="utf-8")
        record = {
            "command": public_command(invocation),
            "returncode": returncode,
            "seconds": seconds,
            "timed_out": timed_out,
        }
        try:
            task_result = json.loads((run / f"{name}.json").read_text(encoding="utf-8"))
            score = float(task_result["score"])
            if (
                returncode == 0
                and task_result.get("status") == "PASS"
                and math.isfinite(score)
                and score > 0
            ):
                record["status"] = "PASS"
                record["score"] = score
            else:
                record["status"] = "FAIL"
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            record["status"] = "FAIL"
            record["result_error"] = str(exc)
        results["tasks"][name] = record
        (run / "run.json").write_text(json.dumps(results, indent=2) + "\n")
        if fail_fast and (returncode != 0 or record["status"] != "PASS"):
            break
    return run, results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=ROOT / "data/official/sample_submission"
    )
    parser.add_argument(
        "--full", action="store_true", help="Full official verification counts; potentially slow"
    )
    parser.add_argument(
        "--task", choices=["all", "invsqrt", "dqi", "dfthcsos"], default="all"
    )
    parser.add_argument(
        "--workers", type=int, default=1, help="DQI needs several GB per worker"
    )
    parser.add_argument("--run-dir", type=Path, help="Explicit empty output directory")
    parser.add_argument(
        "--salt-env", help="Read the validation salt from this environment variable"
    )
    parser.add_argument("--timeout-seconds", type=float)
    parser.add_argument("--fail-fast", action="store_true")
    args = parser.parse_args()
    run, results = run_verification(
        source=args.source,
        full=args.full,
        task=args.task,
        workers=args.workers,
        run_dir=args.run_dir,
        salt_env=args.salt_env,
        timeout_seconds=args.timeout_seconds,
        fail_fast=args.fail_fast,
    )
    print(run)
    return int(
        any(task["returncode"] or task["status"] != "PASS" for task in results["tasks"].values())
    )


if __name__ == "__main__":
    sys.exit(main())
