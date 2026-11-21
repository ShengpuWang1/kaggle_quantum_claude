import json

import pytest

from autoresearch.artifacts import atomic_json, manifest, sha256
from autoresearch.champions import ChampionError, ChampionStore
from autoresearch.config import AgentConfig, Config, Settings, TaskRecipe
from autoresearch.experiments import Experiment
from autoresearch.orchestrator import Orchestrator
from autoresearch.research_tools import ResearchToolContext
from autoresearch.verification import VerificationRunner


def fake_root(tmp_path):
    root = tmp_path / "project"
    champions = ChampionStore(root)
    for task, cost in (("invsqrt", 100), ("dqi", 200), ("dfthcsos", 400)):
        generation = champions.directory / task / "generations" / "baseline"
        artifacts = generation / "artifacts"
        source = generation / "source"
        source.mkdir(parents=True)
        if task in {"invsqrt", "dqi"}:
            artifacts.mkdir(parents=True)
            (artifacts / f"{task}.kmb").write_bytes(b"baseline")
        else:
            (artifacts / "dfthcsos").mkdir(parents=True)
            (artifacts / "dfthcsos" / "angle_k_0.kmb").write_bytes(b"angle")
            (artifacts / "dfthcsos" / "submission.npz").write_bytes(b"npz")
        (source / "STARTING_POINT.md").write_text("baseline", encoding="utf-8")
        atomic_json(
            champions.directory / task / "current.json",
            {
                "champion_id": "baseline",
                "task": task,
                "cost": cost,
                "reference_cost": cost,
                "artifacts": manifest(artifacts, task),
            },
        )
    atomic_json(
        champions.reference_path,
        {"tasks": {task: {"cost": cost} for task, cost in (("invsqrt", 100), ("dqi", 200), ("dfthcsos", 400))}},
    )
    (root / "autoresearch" / "research").mkdir(parents=True, exist_ok=True)
    (root / "autoresearch" / "research" / "RESEARCH_LOG.md").write_text("# Log\n")
    return root


def fake_config(tmp_path, review="approve", build_source=None, max_repair_cycles=1):
    plan = {
        "title": "Tiny artifact test",
        "task": "invsqrt",
        "evidence": [
            {
                "source_type": "notebook",
                "title": "Tiny public notebook",
                "url": "https://www.kaggle.com/code/example/tiny-notebook",
                "local_path": "",
                "insight": "Use a deterministic generator",
            }
        ],
        "hypothesis": "Changing a test artifact exercises promotion",
        "implementation_steps": ["Generate a tiny artifact"],
        "expected_resource_effect": "Lower fake cost",
        "acceptance_criteria": ["Full fake verification passes"],
    }
    if build_source is None:
        build_source = "from pathlib import Path\nPath('invsqrt.kmb').write_bytes(b'candidate')\n"
    agents = {
        "director": AgentConfig(
            provider="fake",
            model="fake",
            options={
                "responses": [
                    {
                        "tool_calls": [
                            {
                                "name": "fetch_research_source",
                                "arguments": {
                                    "url": "https://www.kaggle.com/code/example/tiny-notebook"
                                },
                            }
                        ]
                    },
                    {"tool_calls": [{"name": "submit_plan", "arguments": plan}]},
                ]
            },
        ),
        "implementer": AgentConfig(
            provider="fake",
            model="fake",
            options={
                "responses": [
                    {
                        "tool_calls": [
                            {
                                "name": "write_file",
                                "arguments": {"path": "source/build.py", "content": build_source},
                            }
                        ]
                    },
                    {
                        "tool_calls": [
                            {
                                "name": "finish_implementation",
                                "arguments": {"summary": "Wrote generator", "changed_files": ["source/build.py"]},
                            }
                        ]
                    },
                ]
            },
        ),
        "reviewer": AgentConfig(
            provider="fake",
            model="fake",
            options={
                "responses": [
                    {
                        "tool_calls": [
                            {
                                "name": "submit_review",
                                "arguments": {"decision": review, "rationale": "Test review", "findings": []},
                            }
                        ]
                    }
                ]
            },
        ),
    }
    return Config(
        path=tmp_path / "config.yaml",
        agents=agents,
        settings=Settings(max_repair_cycles=max_repair_cycles),
        tasks={"invsqrt": TaskRecipe(build=["{python}", "source/build.py"]), "dqi": TaskRecipe(), "dfthcsos": TaskRecipe()},
        raw={},
    )


def install_fake_verifier(monkeypatch, root, full_status="PASS", calls=None):
    notebook_source = json.dumps(
        {"cells": [{"cell_type": "code", "source": ["deterministic_generator = True"]}]}
    )
    notebook_response = json.dumps(
        {
            "metadata": {
                "title": "Tiny public notebook",
                "kernelType": "notebook",
                "isPrivate": False,
                "competitionDataSources": [
                    "google-verifiable-quantum-circuit-compilation"
                ],
            },
            "blob": {"source": notebook_source},
        }
    ).encode()
    monkeypatch.setattr(
        ResearchToolContext,
        "_fetch",
        lambda self, url, *, max_bytes: (url, "application/json", notebook_response),
    )

    def verify(self, *, workspace, task, full, run_directory, experiment_id):
        if calls is not None:
            calls.append((task, full))
        run_directory.mkdir(parents=True)
        result = run_directory / f"{task}.json"
        score = 90 if full else 10_000
        result.write_text(json.dumps({"status": full_status if full else "PASS", "score": score}))
        return {
            "mode": "full" if full else "smoke",
            "status": full_status if full else "PASS",
            "score": score,
            "returncode": 0,
            "timed_out": False,
            "seconds": 0.01,
            "run_directory": str(run_directory.relative_to(root)),
            "result": str(result.relative_to(root)),
            "result_sha256": sha256(result),
        }

    monkeypatch.setattr(VerificationRunner, "verify", verify)


def test_complete_fake_experiment_promotes_full_cost_only(tmp_path, monkeypatch):
    root = fake_root(tmp_path)
    install_fake_verifier(monkeypatch, root)
    experiment = Orchestrator(fake_config(tmp_path), root).start()
    metadata = experiment.metadata
    assert metadata["status"] == "promoted"
    assert metadata["comparison"]["candidate_cost"] == 90
    assert metadata["cycles"][0]["smoke"]["score"] == 10_000
    assert ChampionStore(root).current("invsqrt")["cost"] == 90
    assert (experiment.workspace / "invsqrt.kmb").read_bytes() == b"candidate"


def test_exit_zero_missing_artifact_rejects_before_smoke(tmp_path, monkeypatch):
    root = fake_root(tmp_path)
    install_fake_verifier(monkeypatch, root)
    verify_calls = []

    def unexpected_verify(*args, **kwargs):
        verify_calls.append((args, kwargs))
        raise AssertionError("Verification must not run without a candidate")

    monkeypatch.setattr(VerificationRunner, "verify", unexpected_verify)
    config = fake_config(
        tmp_path,
        build_source="from pathlib import Path\nPath('invsqrt.kmb').unlink()\n",
        max_repair_cycles=0,
    )
    experiment = Orchestrator(config, root).start()
    cycle = experiment.metadata["cycles"][0]
    assert experiment.metadata["status"] == "rejected"
    assert cycle["checks"]["ok"] is True
    assert cycle["artifacts"]["ok"] is False
    assert "Expected exactly one invsqrt circuit" in cycle["artifacts"]["error"]
    assert "smoke" not in cycle
    assert "Candidate artifact validation failed" in (
        experiment.directory / "outcome.md"
    ).read_text()
    assert verify_calls == []
    assert ChampionStore(root).current("invsqrt")["cost"] == 100


def test_invalid_artifact_uses_bounded_repair_and_can_recover(tmp_path, monkeypatch):
    root = fake_root(tmp_path)
    verify_calls = []
    install_fake_verifier(monkeypatch, root, calls=verify_calls)
    build_source = (
        "from pathlib import Path\n"
        "marker = Path('source/attempted')\n"
        "if marker.exists():\n"
        "    Path('invsqrt.kmb').write_bytes(b'candidate')\n"
        "else:\n"
        "    marker.write_text('first attempt')\n"
        "    Path('invsqrt.kmb').unlink()\n"
    )
    experiment = Orchestrator(
        fake_config(tmp_path, build_source=build_source, max_repair_cycles=1), root
    ).start()
    cycles = experiment.metadata["cycles"]
    assert experiment.metadata["status"] == "promoted"
    assert len(cycles) == 2
    assert cycles[0]["artifacts"]["ok"] is False
    assert "smoke" not in cycles[0]
    assert cycles[1]["artifacts"] == {"ok": True, "files": ["invsqrt.kmb"]}
    assert verify_calls == [("invsqrt", False), ("invsqrt", True)]


def test_empty_exception_message_records_exception_type(tmp_path, monkeypatch):
    root = fake_root(tmp_path)
    orchestrator = Orchestrator(fake_config(tmp_path), root)
    experiment = Experiment.create(root, orchestrator.config.public_dict())
    monkeypatch.setattr(orchestrator, "_plan", lambda experiment: None)

    def fail_without_message(experiment):
        raise StopIteration

    monkeypatch.setattr(orchestrator, "_research_cycles", fail_without_message)
    with pytest.raises(StopIteration):
        orchestrator.run(experiment)
    assert experiment.metadata["status"] == "failed"
    assert "StopIteration" in (experiment.directory / "outcome.md").read_text()
    events = [
        json.loads(line)
        for line in experiment.events_path.read_text().splitlines()
        if line.strip()
    ]
    error = next(event for event in events if event.get("kind") == "error")
    assert error["message"] == "StopIteration"


def test_resume_from_planned_does_not_repeat_director(tmp_path, monkeypatch):
    root = fake_root(tmp_path)
    install_fake_verifier(monkeypatch, root)
    config = fake_config(tmp_path)
    orchestrator = Orchestrator(config, root)
    experiment = Experiment.create(root, config.public_dict())
    orchestrator._plan(experiment)
    resumed = orchestrator.resume(experiment.experiment_id)
    assert resumed.metadata["status"] == "promoted"
    director_events = [
        line
        for line in (experiment.events_path).read_text().splitlines()
        if '"role": "director"' in line and '"kind": "provider_turn"' in line
    ]
    assert len(director_events) == 2


def test_full_failure_is_terminal_without_repair(tmp_path, monkeypatch):
    root = fake_root(tmp_path)
    install_fake_verifier(monkeypatch, root, full_status="FAIL")
    experiment = Orchestrator(fake_config(tmp_path), root).start()
    assert experiment.metadata["status"] == "rejected"
    assert len(experiment.metadata["cycles"]) == 1
    assert "Terminal full verification failed" in (
        experiment.directory / "outcome.md"
    ).read_text()


def test_review_revision_consumes_bounded_repair(tmp_path, monkeypatch):
    root = fake_root(tmp_path)
    install_fake_verifier(monkeypatch, root)
    experiment = Orchestrator(fake_config(tmp_path, review="revise"), root).start()
    assert experiment.metadata["status"] == "rejected"
    assert len(experiment.metadata["cycles"]) == 2
    assert ChampionStore(root).current("invsqrt")["cost"] == 100


def test_stale_parent_cannot_promote(tmp_path):
    root = fake_root(tmp_path)
    store = ChampionStore(root)
    candidate = root / "candidate"
    candidate.mkdir()
    (candidate / "invsqrt.kmb").write_bytes(b"candidate")
    source = root / "source"
    source.mkdir()
    result = root / "result.json"
    result.write_text(json.dumps({"status": "PASS", "score": 90}))
    with pytest.raises(ChampionError, match="Stale parent"):
        store.promote(
            task="invsqrt",
            experiment_id="EXP-test",
            parent_id="older-parent",
            candidate_dir=candidate,
            source_dir=source,
            candidate_manifest=manifest(candidate, "invsqrt"),
            metrics={"status": "PASS", "score": 90},
            result_path=result,
        )
