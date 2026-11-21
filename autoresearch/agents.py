"""Bounded, fresh-context role sessions."""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema

from .config import ROOT, AgentConfig
from .providers import make_provider
from .tools import ToolContext, terminal_name, terminal_spec


class AgentError(RuntimeError):
    """Raised when a role cannot produce a valid result within its budget."""


def _error_summary(text: str, config: AgentConfig) -> str:
    summary = re.sub(r"https?://\S+", "<url>", text, flags=re.IGNORECASE)
    secret_values = [config.api_key, config.auth_token]
    for name in (config.api_key_env, config.auth_token_env):
        secret_values.append(os.environ.get(name) if name else None)
    for secret in secret_values:
        if secret:
            summary = summary.replace(secret, "<redacted>")
    return " ".join(summary.split())[:300]


@dataclass
class AgentResult:
    role: str
    data: dict[str, Any]
    text: str
    turns: int


class RoleRunner:
    def __init__(self, config: AgentConfig, role: str):
        self.config = config
        self.role = role
        prompt_path = (
            Path(config.prompt).expanduser().resolve()
            if config.prompt
            else ROOT / "autoresearch" / "prompts" / f"{role}.md"
        )
        self.system_prompt = prompt_path.read_text(encoding="utf-8")

    def run(
        self,
        prompt: str,
        *,
        tools: ToolContext,
        result_schema: dict[str, Any],
        event: Callable[[dict[str, Any]], None] | None = None,
    ) -> AgentResult:
        provider = make_provider(self.config)
        messages = [{"role": "user", "content": prompt}]
        file_specs = tools.specs()
        specs = [*file_specs, terminal_spec(self.role, result_schema)]
        started = time.monotonic()

        def record(kind: str, **values: Any) -> None:
            if event:
                event({"role": self.role, "kind": kind, **values})

        for turn_number in range(1, self.config.max_turns + 1):
            if time.monotonic() - started > self.config.timeout_seconds:
                raise AgentError(f"{self.role} exceeded its overall time budget")
            turn = provider.complete(
                system=self.system_prompt, messages=messages, tools=specs
            )
            messages.append(turn.assistant_message)
            record(
                "provider_turn",
                turn=turn_number,
                stop_reason=turn.stop_reason,
                usage=turn.usage,
                tool_calls=[call.name for call in turn.tool_calls],
            )
            terminal = terminal_name(self.role)
            terminal_calls = [call for call in turn.tool_calls if call.name == terminal]
            if terminal_calls:
                if len(turn.tool_calls) != 1:
                    raise AgentError(f"{self.role} combined its terminal tool with other tools")
                call = terminal_calls[0]
                try:
                    jsonschema.validate(call.arguments, result_schema)
                except jsonschema.ValidationError as exc:
                    raise AgentError(f"Invalid {self.role} result: {exc.message}") from exc
                record("finished", turns=turn_number)
                return AgentResult(self.role, call.arguments, turn.text, turn_number)
            if turn.stop_reason == "pause_turn":
                continue
            if not turn.tool_calls:
                raise AgentError(
                    f"{self.role} did not call {terminal}; response: {turn.text[:500]}"
                )
            results = []
            for call in turn.tool_calls:
                if call.name not in {spec.name for spec in file_specs}:
                    results.append((call, f"Unknown tool: {call.name}", True))
                    continue
                result = tools.execute(call)
                details = (
                    {"error_summary": _error_summary(result.content, self.config)}
                    if result.is_error
                    else {}
                )
                record(
                    "tool_result",
                    turn=turn_number,
                    tool=call.name,
                    is_error=result.is_error,
                    **details,
                )
                results.append((call, result.content, result.is_error))
            messages.extend(provider.tool_result_messages(results))
        raise AgentError(f"{self.role} exceeded {self.config.max_turns} turns")


def result_schemas() -> dict[str, dict[str, Any]]:
    return {
        "director": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "minLength": 1},
                "task": {"type": "string", "enum": ["invsqrt", "dqi", "dfthcsos"]},
                "evidence": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "source_type": {
                                "type": "string",
                                "enum": ["notebook", "paper"],
                            },
                            "title": {"type": "string", "minLength": 1},
                            "url": {"type": "string", "minLength": 1},
                            "local_path": {"type": "string"},
                            "insight": {"type": "string", "minLength": 1},
                        },
                        "required": [
                            "source_type",
                            "title",
                            "url",
                            "local_path",
                            "insight",
                        ],
                        "allOf": [
                            {
                                "if": {
                                    "properties": {
                                        "source_type": {"const": "paper"}
                                    }
                                },
                                "then": {
                                    "properties": {
                                        "local_path": {
                                            "pattern": r"^docs/papers/.+\.pdf$"
                                        }
                                    }
                                },
                            }
                        ],
                        "additionalProperties": False,
                    },
                },
                "hypothesis": {"type": "string", "minLength": 1},
                "implementation_steps": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "minItems": 1,
                },
                "expected_resource_effect": {"type": "string"},
                "risks": {"type": "array", "items": {"type": "string"}},
                "acceptance_criteria": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
            },
            "required": [
                "title",
                "task",
                "evidence",
                "hypothesis",
                "implementation_steps",
                "expected_resource_effect",
                "acceptance_criteria",
            ],
            "additionalProperties": False,
        },
        "implementer": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "minLength": 1},
                "changed_files": {"type": "array", "items": {"type": "string"}},
                "build_notes": {"type": "string"},
                "known_limitations": {"type": "string"},
            },
            "required": ["summary", "changed_files"],
            "additionalProperties": False,
        },
        "reviewer": {
            "type": "object",
            "properties": {
                "decision": {"type": "string", "enum": ["approve", "revise"]},
                "rationale": {"type": "string"},
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "severity": {
                                "type": "string",
                                "enum": ["low", "medium", "high", "critical"],
                            },
                            "file": {"type": "string"},
                            "line": {"type": "integer", "minimum": 1},
                            "summary": {"type": "string"},
                        },
                        "required": ["severity", "summary"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["decision", "rationale", "findings"],
            "additionalProperties": False,
        },
    }
