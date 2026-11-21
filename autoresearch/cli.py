"""Command-line interface for deterministic auto-research."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from scripts.autoresearch_verifier import run_verification

from .artifacts import atomic_json
from .champions import ChampionStore
from .config import ROOT, TASKS, ConfigError, load_config
from .experiments import Experiment, list_experiments
from .orchestrator import Orchestrator
from .scoring import leaderboard_estimate


def _print(value) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def _summary(experiment: Experiment) -> dict:
    metadata = experiment.metadata
    result = {
        "experiment_id": experiment.experiment_id,
        "status": metadata["status"],
        "task": metadata.get("task"),
    }
    if metadata.get("comparison"):
        result["comparison"] = metadata["comparison"]
    return result


def cmd_init(args) -> int:
    champions = ChampionStore(ROOT)
    created = champions.initialize()
    current = {task: champions.current(task) for task in TASKS}
    atomic_json(
        ROOT / "autoresearch" / "research" / "STATE.json",
        {"last_experiment": None, "last_status": "initialized", "champions": current},
    )
    _print({"initialized": [record["task"] for record in created]})
    return 0


def cmd_run(args) -> int:
    orchestrator = Orchestrator(load_config(args.config), ROOT)
    experiment = orchestrator.start()
    _print(_summary(experiment))
    return 0 if experiment.metadata["status"] == "promoted" else 1


def cmd_loop(args) -> int:
    orchestrator = Orchestrator(load_config(args.config), ROOT)
    for _ in range(args.experiments):
        experiment = orchestrator.start()
        _print(_summary(experiment))
    return 0


def cmd_resume(args) -> int:
    orchestrator = Orchestrator(load_config(args.config), ROOT)
    experiment = orchestrator.resume(args.experiment_id)
    _print(_summary(experiment))
    return 0 if experiment.metadata["status"] == "promoted" else 1


def cmd_status(args) -> int:
    champions = ChampionStore(ROOT)
    current = {task: champions.current(task) for task in TASKS}
    references = {
        task: float(record["cost"]) for task, record in champions.references().items()
    }
    _print(
        {
            "champions": current,
            "local_portfolio_score_estimate": leaderboard_estimate(
                champions.costs(), references
            ),
            "recent_experiments": [
                {
                    key: record.get(key)
                    for key in ("experiment_id", "status", "task", "updated_at")
                }
                for record in list_experiments(ROOT)[: args.limit]
            ],
        }
    )
    return 0


def cmd_show(args) -> int:
    _print(Experiment.load(ROOT, args.experiment_id).metadata)
    return 0


def cmd_package(args) -> int:
    provenance = ChampionStore(ROOT).package_portfolio(args.output)
    _print({"output": str(args.output), "champions": provenance})
    return 0


def cmd_verify(args) -> int:
    source = args.source or ChampionStore(ROOT).artifact_dir(args.task)
    run = args.run_dir or (
        ROOT
        / "runs"
        / "autoresearch"
        / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    )
    run, results = run_verification(
        source=source,
        full=args.full,
        task=args.task,
        workers=args.workers,
        run_dir=run,
        salt_env=args.salt_env,
        timeout_seconds=args.timeout_seconds,
        fail_fast=True,
    )
    _print(results)
    return int(results["tasks"][args.task]["status"] != "PASS")


def cmd_doctor(args) -> int:
    config = load_config(args.config)
    report = {"config": config.public_dict(), "checks": {}}
    for package in ("anthropic", "openai", "yaml", "jsonschema"):
        report["checks"][f"import:{package}"] = importlib.util.find_spec(package) is not None
    for role, agent in config.agents.items():
        report["checks"][f"credentials:{role}"] = agent.has_credentials()
    report["checks"]["official_verifiers"] = all(
        (ROOT / "data" / "official" / "verifiers").glob("*/verify*.py")
    )
    champions = ChampionStore(ROOT)
    report["checks"]["champions"] = {
        task: (champions.directory / task / "current.json").is_file() for task in TASKS
    }
    report["note"] = "Offline diagnostics only; no provider or verifier calls were made."
    _print(report)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orchestrate", description=__doc__
    )
    parser.add_argument("--config", help="YAML configuration path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Import hash-checked full local baselines")
    init.set_defaults(function=cmd_init)

    run = subparsers.add_parser("run", help="Run one research experiment")
    run.set_defaults(function=cmd_run)

    loop = subparsers.add_parser("loop", help="Run sequential experiments")
    loop.add_argument("--experiments", type=int, default=1)
    loop.set_defaults(function=cmd_loop)

    resume = subparsers.add_parser("resume", help="Resume a nonterminal experiment")
    resume.add_argument("experiment_id")
    resume.set_defaults(function=cmd_resume)

    status = subparsers.add_parser("status", help="Show champions and recent experiments")
    status.add_argument("--limit", type=int, default=10)
    status.set_defaults(function=cmd_status)

    show = subparsers.add_parser("show", help="Show one experiment's public metadata")
    show.add_argument("experiment_id")
    show.set_defaults(function=cmd_show)

    package = subparsers.add_parser(
        "package-portfolio", help="Package current champions without uploading"
    )
    package.add_argument("--output", type=Path, required=True)
    package.set_defaults(function=cmd_package)

    verify = subparsers.add_parser("verify", help="Verify a champion or explicit source")
    verify.add_argument("--task", choices=TASKS, required=True)
    verify.add_argument("--source", type=Path)
    verify.add_argument("--full", action="store_true")
    verify.add_argument("--workers", type=int, default=1)
    verify.add_argument("--run-dir", type=Path)
    verify.add_argument("--salt-env")
    verify.add_argument("--timeout-seconds", type=float)
    verify.set_defaults(function=cmd_verify)

    doctor = subparsers.add_parser("doctor", help="Inspect offline setup and redacted config")
    doctor.set_defaults(function=cmd_doctor)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "loop" and args.experiments < 1:
        parser.error("--experiments must be positive")
    try:
        return args.function(args)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
