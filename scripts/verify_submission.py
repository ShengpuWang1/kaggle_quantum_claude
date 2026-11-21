"""Run unmodified official verifiers, preserving commands and results per run."""

import argparse
import datetime
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS = ("invsqrt", "dqi", "dfthcsos")


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


def build_commands(source, verifiers, task="all", full=False, workers=1, salt=""):
    commands = {}
    for name in TASKS if task == "all" else (task,):
        if name == "invsqrt":
            command = [
                str(verifiers / "invsqrt/verify_submission_invsqrt.py"),
                str(circuit_path(source, name)),
                "--max-workers",
                str(workers),
            ]
            if not full:
                command += ["--max-x", "4096"]
        elif name == "dqi":
            command = [
                str(verifiers / "dqi/verify_submission_dqi.py"),
                str(circuit_path(source, name)),
                "--max-workers",
                str(workers),
            ]
            if not full:
                command += ["--num-shots", "4096"]
        else:
            command = [str(verifiers / "dfthcsos/verify.py"), str(source / "dfthcsos")]
        if salt:
            command += ["--salt", salt]
        commands[name] = command
    return commands


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=ROOT / "data/official/sample_submission"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Full official verification counts; potentially slow",
    )
    parser.add_argument(
        "--task", choices=["all", "invsqrt", "dqi", "dfthcsos"], default="all"
    )
    parser.add_argument(
        "--workers", type=int, default=1, help="DQI needs several GB per worker"
    )
    parser.add_argument("--salt", default="", help="Optional official verifier salt")
    args = parser.parse_args()
    source = args.source.resolve()
    verifiers = ROOT / "data/official/verifiers"
    try:
        commands = build_commands(
            source,
            verifiers,
            task=args.task,
            full=args.full,
            workers=args.workers,
            salt=args.salt,
        )
    except ValueError as exc:
        parser.error(str(exc))
    run = (
        ROOT / "runs" / datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%S%fZ")
    )
    run.mkdir(parents=True)
    results = {
        "mode": "full" if args.full else "smoke (dfthcsos uses full defaults)",
        "tasks": {},
    }
    for task, command in commands.items():
        command = [sys.executable, *command]
        print(f"Running {task}; logs: {run}", flush=True)
        start = time.monotonic()
        with (
            (run / f"{task}.json").open("w") as out,
            (run / f"{task}.stderr").open("w") as err,
        ):
            process = subprocess.run(
                command, cwd=ROOT, stdout=out, stderr=err, check=False
            )
        results["tasks"][task] = {
            "command": command,
            "returncode": process.returncode,
            "seconds": time.monotonic() - start,
        }
        (run / "run.json").write_text(json.dumps(results, indent=2) + "\n")
    return int(any(t["returncode"] for t in results["tasks"].values()))


if __name__ == "__main__":
    sys.exit(main())
