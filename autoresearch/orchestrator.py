"""Sequential champion–challenger research state machine."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .agents import RoleRunner, result_schemas
from .artifacts import (
    ArtifactError,
    atomic_json,
    candidate_files,
    copy_task,
    manifest,
    verify_manifest,
)
from .champions import ChampionError, ChampionStore
from .config import ROOT, Config
from .experiments import Experiment, utc_now
from .research_tools import ResearchToolContext
from .scoring import comparison, leaderboard_estimate
from .tools import ToolContext, pretty_json
from .verification import VerificationRunner, run_recipe


class Orchestrator:
    def __init__(self, config: Config, root: Path = ROOT):
        self.config = config
        self.root = root
        self.champions = ChampionStore(root)
        self.verifier = VerificationRunner(root, config.settings)
        self.schemas = result_schemas()

    def start(self) -> Experiment:
        experiment = Experiment.create(self.root, self.config.public_dict())
        return self.run(experiment)

    def resume(self, experiment_id: str) -> Experiment:
        experiment = Experiment.load(self.root, experiment_id)
        experiment.require_resumable()
        return self.run(experiment)

    def run(self, experiment: Experiment) -> Experiment:
        try:
            if experiment.metadata["status"] == "new":
                self._plan(experiment)
            self._research_cycles(experiment)
        except Exception as exc:
            metadata = experiment.metadata
            if metadata["status"] not in {"promoted", "rejected", "failed"}:
                reason = str(exc) or type(exc).__name__
                experiment.event("error", error_type=type(exc).__name__, message=reason)
                experiment.transition("failed")
                self._outcome(experiment, "failed", reason)
            raise
        return experiment

    def _tools(self, experiment: Experiment, role: str) -> ToolContext:
        workspace = (
            experiment.workspace
            if role == "implementer"
            else experiment.directory / role
        )
        if role == "director":
            return ResearchToolContext(
                workspace,
                writable=False,
                read_root=self.root,
                max_output_chars=self.config.agents[role].max_tool_output_chars,
                papers_directory=self.root / "docs" / "papers",
            )
        return ToolContext(
            workspace,
            writable=role == "implementer",
            read_root=self.root,
            max_output_chars=self.config.agents[role].max_tool_output_chars,
        )

    def _role(
        self,
        experiment: Experiment,
        role: str,
        prompt: str,
    ):
        tools = self._tools(experiment, role)
        result = RoleRunner(self.config.agents[role], role).run(
            prompt,
            tools=tools,
            result_schema=self.schemas[role],
            event=lambda event: experiment.event(
                event["kind"], **{key: value for key, value in event.items() if key != "kind"}
            ),
        )
        if role == "director":
            tools.validate_evidence(result.data["evidence"])
        return result

    def _plan(self, experiment: Experiment) -> None:
        current = {task: self.champions.current(task) for task in self.champions.references()}
        prompt = (
            "Propose one focused, implementable circuit-optimization experiment. "
            "Read the research roadmap, backlog, decisions, and recent research log first. "
            "Before forming concrete implementation steps, select and inspect either a public "
            "notebook from the competition's score-sorted notebook listing at "
            "https://www.kaggle.com/competitions/google-verifiable-quantum-circuit-compilation/"
            "code?competitionId=161954&sortBy=scoreDescending&excludeNonAccessedDatasources=true "
            "or a relevant research paper. For a paper, download its PDF to docs/papers during "
            "this design phase. Cite the inspected evidence in your structured plan. "
            "Choose exactly one task and avoid repeating a recently rejected hypothesis without "
            "a materially new idea. Current per-task champion state follows.\n\n"
            + pretty_json(current)
        )
        result = self._role(experiment, "director", prompt)
        plan = result.data
        task = plan["task"]
        champion = current[task]
        copy_task(self.champions.artifact_dir(task), task, experiment.workspace)
        source = self.champions.source_dir(task)
        if source.exists():
            shutil.copytree(source, experiment.workspace / "source")
        else:
            (experiment.workspace / "source").mkdir(parents=True)
        experiment.write_json("plan.json", plan)
        (experiment.directory / "proposal.md").write_text(
            f"# {plan['title']}\n\n**Task:** `{task}`\n\n"
            f"## Hypothesis\n\n{plan['hypothesis']}\n\n"
            f"## Expected resource effect\n\n{plan['expected_resource_effect']}\n\n"
            "## Research evidence\n\n"
            + "\n".join(
                f"- **{source['title']}** ({source['source_type']}): {source['url']}\n"
                f"  - {source['insight']}"
                + (f"\n  - Local PDF: `{source['local_path']}`" if source["local_path"] else "")
                for source in plan["evidence"]
            )
            + "\n",
            encoding="utf-8",
        )
        (experiment.directory / "plan.md").write_text(
            "# Implementation plan\n\n"
            + "\n".join(f"{i}. {step}" for i, step in enumerate(plan["implementation_steps"], 1))
            + "\n\n## Acceptance criteria\n\n"
            + "\n".join(f"- {item}" for item in plan["acceptance_criteria"])
            + "\n\n## Risks\n\n"
            + "\n".join(f"- {item}" for item in plan.get("risks", []))
            + "\n",
            encoding="utf-8",
        )
        experiment.update(task=task, parent_id=champion["champion_id"], parent=champion, plan=plan)
        experiment.transition("planned")

    def _research_cycles(self, experiment: Experiment) -> None:
        while True:
            metadata = experiment.metadata
            if metadata["status"] == "planned" or (
                metadata["status"] == "implementing" and not metadata.get("cycles")
            ):
                if metadata["status"] == "planned":
                    experiment.transition("implementing")
                experiment.append_cycle(
                    {"number": len(metadata.get("cycles", [])) + 1, "started_at": utc_now()}
                )
            cycle = experiment.metadata["cycles"][-1]
            number = int(cycle["number"])
            if "implementation" not in cycle:
                self._implement(experiment, cycle)
                cycle = experiment.metadata["cycles"][-1]
            if "checks" not in cycle:
                if experiment.metadata["status"] == "implementing":
                    experiment.transition("checks")
                checks = run_recipe(
                    self.config.tasks[metadata["task"]],
                    workspace=experiment.workspace,
                    log_directory=experiment.directory / f"cycle-{number:02d}-commands",
                    timeout_seconds=self.config.settings.command_timeout_seconds,
                )
                cycle["checks"] = checks
                experiment.replace_last_cycle(cycle)
                if not checks["ok"]:
                    if self._repair_or_reject(experiment, number, "Build or test commands failed"):
                        continue
                    return
            if "smoke" not in cycle:
                try:
                    files = candidate_files(experiment.workspace, metadata["task"])
                except ArtifactError as exc:
                    cycle["artifacts"] = {"ok": False, "error": str(exc)}
                    experiment.replace_last_cycle(cycle)
                    if self._repair_or_reject(
                        experiment,
                        number,
                        f"Candidate artifact validation failed: {exc}",
                    ):
                        continue
                    return
                cycle["artifacts"] = {
                    "ok": True,
                    "files": [
                        path.relative_to(experiment.workspace).as_posix() for path in files
                    ],
                }
                experiment.replace_last_cycle(cycle)
                if experiment.metadata["status"] == "checks":
                    experiment.transition("smoke")
                smoke = self.verifier.verify(
                    workspace=experiment.workspace,
                    task=metadata["task"],
                    full=False,
                    run_directory=experiment.directory / f"cycle-{number:02d}-smoke",
                    experiment_id=experiment.experiment_id,
                )
                cycle["smoke"] = smoke
                experiment.replace_last_cycle(cycle)
                if smoke["status"] != "PASS":
                    if self._repair_or_reject(experiment, number, "Smoke verification failed"):
                        continue
                    return
            if "review" not in cycle:
                if experiment.metadata["status"] == "smoke":
                    experiment.transition("reviewing")
                self._review(experiment, cycle)
                cycle = experiment.metadata["cycles"][-1]
            if cycle["review"]["decision"] != "approve":
                if self._repair_or_reject(experiment, number, "Reviewer requested revisions"):
                    continue
                return
            self._full_verification(experiment, cycle)
            return

    def _implement(self, experiment: Experiment, cycle: dict[str, Any]) -> None:
        metadata = experiment.metadata
        previous = metadata["cycles"][-2] if len(metadata["cycles"]) > 1 else None
        prompt = (
            "Implement the approved experiment in your isolated task workspace. "
            "The champion artifacts are already at the required output paths. "
            "Write reproducible generator/source files below `source/`; do not merely describe "
            "changes. The orchestrator, not you, runs builds and verification. "
            "Use `finish_implementation` when files are ready.\n\n"
            f"Experiment plan:\n{pretty_json(metadata['plan'])}\n"
            f"Project root: {self.root}\nExperiment directory: {experiment.directory}\n"
            f"Configured build/test recipe:\n{pretty_json(self.config.tasks[metadata['task']].public_dict())}\n"
        )
        if previous:
            prompt += (
                "This is a bounded repair cycle. Address the preceding feedback without "
                "claiming verification success.\n"
                f"Previous cycle:\n{pretty_json(previous)}"
            )
        result = self._role(experiment, "implementer", prompt)
        cycle["implementation"] = result.data
        experiment.replace_last_cycle(cycle)
        experiment.write_json(f"cycle-{cycle['number']:02d}-implementation.json", result.data)
        (experiment.directory / f"cycle-{cycle['number']:02d}-implementation.md").write_text(
            f"# Implementation cycle {cycle['number']}\n\n{result.data['summary']}\n\n"
            f"## Changed files\n\n"
            + "\n".join(f"- `{path}`" for path in result.data["changed_files"])
            + f"\n\n## Build notes\n\n{result.data.get('build_notes', '')}\n\n"
            f"## Known limitations\n\n{result.data.get('known_limitations', '')}\n",
            encoding="utf-8",
        )

    def _review(self, experiment: Experiment, cycle: dict[str, Any]) -> None:
        metadata = experiment.metadata
        prompt = (
            "Independently review this implementation in a fresh read-only context. "
            "Check correctness, reproducibility, scope, and whether the generator really "
            "implements the hypothesis. The orchestrator's build and smoke status is evidence, "
            "not proof of optimality. Do not request full-verifier tuning details.\n\n"
            f"Plan:\n{pretty_json(metadata['plan'])}\n"
            f"Implementation:\n{pretty_json(cycle['implementation'])}\n"
            f"Build/test record:\n{pretty_json(cycle['checks'])}\n"
            f"Smoke status: {cycle['smoke']['status']}\n"
            "Return `approve` only if the candidate is ready for one terminal full verification."
        )
        result = self._role(experiment, "reviewer", prompt)
        cycle["review"] = result.data
        experiment.replace_last_cycle(cycle)
        experiment.write_json(f"cycle-{cycle['number']:02d}-review.json", result.data)
        (experiment.directory / f"cycle-{cycle['number']:02d}-review.md").write_text(
            f"# Review cycle {cycle['number']}: {result.data['decision']}\n\n"
            f"{result.data['rationale']}\n\n"
            + "\n".join(
                f"- **{finding['severity']}**: {finding['summary']}"
                for finding in result.data["findings"]
            )
            + "\n",
            encoding="utf-8",
        )

    def _repair_or_reject(
        self, experiment: Experiment, number: int, reason: str
    ) -> bool:
        if number <= self.config.settings.max_repair_cycles:
            experiment.event("repair", cycle=number, reason=reason)
            experiment.transition("implementing")
            experiment.append_cycle({"number": number + 1, "started_at": utc_now()})
            return True
        experiment.transition("rejected")
        self._outcome(experiment, "rejected", f"{reason}; repair budget exhausted")
        return False

    def _full_verification(
        self, experiment: Experiment, cycle: dict[str, Any]
    ) -> None:
        metadata = experiment.metadata
        task = metadata["task"]
        candidate_manifest = manifest(experiment.workspace, task)
        experiment.update(candidate_manifest=candidate_manifest)
        experiment.transition("full")
        metrics = self.verifier.verify(
            workspace=experiment.workspace,
            task=task,
            full=True,
            run_directory=experiment.directory / "full",
            experiment_id=experiment.experiment_id,
        )
        verify_manifest(experiment.workspace, candidate_manifest)
        experiment.write_json("metrics.json", metrics)
        experiment.update(full_metrics=metrics)
        if metrics["status"] != "PASS":
            experiment.transition("rejected")
            self._outcome(
                experiment,
                "rejected",
                "Terminal full verification failed; no further repair is allowed for this salt",
            )
            return
        current_costs = self.champions.costs()
        result = comparison(
            task,
            candidate_cost=metrics["score"],
            champion=metadata["parent"],
            current_costs=current_costs,
        )
        references = {
            name: float(value["cost"]) for name, value in self.champions.references().items()
        }
        result["portfolio_score_estimate"] = leaderboard_estimate(
            result["candidate_costs"], references
        )
        result["champion_portfolio_score_estimate"] = leaderboard_estimate(
            current_costs, references
        )
        experiment.write_json("comparison.json", result)
        experiment.update(comparison=result)
        if not result["improved"]:
            experiment.transition("rejected")
            self._outcome(experiment, "rejected", "Full PASS, but cost did not improve")
            return
        try:
            promoted = self.champions.promote(
                task=task,
                experiment_id=experiment.experiment_id,
                parent_id=metadata["parent_id"],
                candidate_dir=experiment.workspace,
                source_dir=experiment.workspace / "source",
                candidate_manifest=candidate_manifest,
                metrics=metrics,
                result_path=self.root / metrics["result"],
            )
        except ChampionError as exc:
            experiment.transition("rejected")
            self._outcome(experiment, "rejected", str(exc))
            return
        experiment.update(champion=promoted)
        experiment.transition("promoted")
        self._outcome(
            experiment,
            "promoted",
            f"Full PASS; cost improved from {result['champion_cost']} to {result['candidate_cost']}",
        )

    def _outcome(self, experiment: Experiment, status: str, reason: str) -> None:
        metadata = experiment.metadata
        text = (
            f"# {experiment.experiment_id}: {status}\n\n"
            f"**Task:** `{metadata.get('task')}`\n\n{reason}\n"
        )
        (experiment.directory / "outcome.md").write_text(text, encoding="utf-8")
        experiment.event("outcome", status=status, reason=reason)
        research = self.root / "autoresearch" / "research"
        research.mkdir(parents=True, exist_ok=True)
        with (research / "RESEARCH_LOG.md").open("a", encoding="utf-8") as handle:
            handle.write(
                f"\n## {utc_now()} — {experiment.experiment_id}: {status}\n\n"
                f"- Task: `{metadata.get('task')}`\n- {reason}\n"
            )
            if metadata.get("comparison"):
                handle.write(
                    f"- Champion gain: {metadata['comparison']['champion_gain']:.6g}x\n"
                    f"- Local portfolio estimate: "
                    f"{metadata['comparison']['portfolio_score_estimate']:.9g}\n"
                )
        state = {"last_experiment": experiment.experiment_id, "last_status": status}
        try:
            state["champions"] = {
                task: self.champions.current(task)
                for task in self.champions.references()
            }
        except ChampionError:
            state["champions"] = "unavailable"
        atomic_json(research / "STATE.json", state)
