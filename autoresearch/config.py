"""Configuration loading and secret-safe representations."""

from __future__ import annotations

import copy
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = Path(__file__).with_name("config.yaml")
ROLES = ("director", "implementer", "reviewer")
TASKS = ("invsqrt", "dqi", "dfthcsos")
PROVIDERS = {"anthropic", "openai", "fake"}
SECRET_PARTS = ("api_key", "apikey", "secret", "password", "salt", "authorization")


class ConfigError(ValueError):
    """Raised when the research configuration is invalid."""


def redact(value: Any) -> Any:
    """Return a copy with values under secret-looking keys removed."""
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            lowered = str(key).lower()
            secret_key = any(part in lowered for part in SECRET_PARTS) or (
                lowered == "token" or lowered.endswith("_token")
            )
            if secret_key and not lowered.endswith("_env"):
                result[str(key)] = "<redacted>"
            else:
                result[str(key)] = redact(item)
        return result
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    return copy.deepcopy(value)


def _positive_int(data: Mapping[str, Any], key: str, default: int) -> int:
    value = int(data.get(key, default))
    if value <= 0:
        raise ConfigError(f"{key} must be positive, got {value}")
    return value


@dataclass
class AgentConfig:
    provider: str
    model: str
    api_key: str | None = None
    api_key_env: str | None = None
    auth_token: str | None = None
    auth_token_env: str | None = None
    base_url: str | None = None
    effort: str | None = None
    max_tokens: int = 16000
    max_turns: int = 20
    timeout_seconds: int = 600
    max_retries: int = 2
    max_tool_output_chars: int = 30000
    stream: bool = True
    prompt: str | None = None
    options: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, role: str, data: Mapping[str, Any]) -> AgentConfig:
        provider = str(data.get("provider", "")).lower()
        if provider not in PROVIDERS:
            raise ConfigError(
                f"agents.{role}.provider must be one of {sorted(PROVIDERS)}"
            )
        model = str(data.get("model", "")).strip()
        if provider != "fake" and not model:
            raise ConfigError(f"agents.{role}.model is required")
        api_key = data.get("api_key")
        api_key_env = data.get("api_key_env")
        if api_key is not None and not isinstance(api_key, str):
            raise ConfigError(f"agents.{role}.api_key must be a string")
        if api_key_env is not None and not isinstance(api_key_env, str):
            raise ConfigError(f"agents.{role}.api_key_env must be a string")
        auth_token = data.get("auth_token")
        auth_token_env = data.get("auth_token_env")
        if auth_token is not None and not isinstance(auth_token, str):
            raise ConfigError(f"agents.{role}.auth_token must be a string")
        if auth_token_env is not None and not isinstance(auth_token_env, str):
            raise ConfigError(f"agents.{role}.auth_token_env must be a string")
        if (api_key or api_key_env) and (auth_token or auth_token_env):
            raise ConfigError(
                f"agents.{role} must use either API-key or auth-token authentication, not both"
            )
        if provider != "anthropic" and (auth_token or auth_token_env):
            raise ConfigError(f"agents.{role}.auth_token is only supported by anthropic")
        options = dict(data.get("options", {}))
        reserved = {"model", "messages", "tools", "system", "api_key", "auth_token"}
        overlap = reserved & options.keys()
        if overlap:
            raise ConfigError(
                f"agents.{role}.options cannot override {sorted(overlap)}"
            )
        return cls(
            provider=provider,
            model=model or "fake",
            api_key=api_key,
            api_key_env=api_key_env,
            auth_token=auth_token,
            auth_token_env=auth_token_env,
            base_url=data.get("base_url"),
            effort=data.get("effort"),
            max_tokens=_positive_int(data, "max_tokens", 16000),
            max_turns=_positive_int(data, "max_turns", 20),
            timeout_seconds=_positive_int(data, "timeout_seconds", 600),
            max_retries=int(data.get("max_retries", 2)),
            max_tool_output_chars=_positive_int(data, "max_tool_output_chars", 30000),
            stream=bool(data.get("stream", True)),
            prompt=data.get("prompt"),
            options=options,
        )

    def resolved_api_key(self, environ: Mapping[str, str] | None = None) -> str | None:
        if self.api_key:
            return self.api_key
        if self.api_key_env:
            return (environ or os.environ).get(self.api_key_env)
        return None

    def require_api_key(self, environ: Mapping[str, str] | None = None) -> str:
        if self.provider == "fake":
            return "fake"
        key = self.resolved_api_key(environ)
        if not key:
            source = self.api_key_env or f"agents.{self.provider}.api_key"
            raise ConfigError(f"No API key found; set {source}")
        return key

    def resolved_auth_token(
        self, environ: Mapping[str, str] | None = None
    ) -> str | None:
        if self.auth_token:
            return self.auth_token
        if self.auth_token_env:
            return (environ or os.environ).get(self.auth_token_env)
        return None

    def require_auth_token(self, environ: Mapping[str, str] | None = None) -> str:
        token = self.resolved_auth_token(environ)
        if not token:
            source = self.auth_token_env or f"agents.{self.provider}.auth_token"
            raise ConfigError(f"No auth token found; set {source}")
        return token

    def has_credentials(self, environ: Mapping[str, str] | None = None) -> bool:
        return self.provider == "fake" or bool(
            self.resolved_api_key(environ) or self.resolved_auth_token(environ)
        )

    def public_dict(self) -> dict[str, Any]:
        return redact(
            {
                "provider": self.provider,
                "model": self.model,
                "api_key": self.api_key,
                "api_key_env": self.api_key_env,
                "auth_token": self.auth_token,
                "auth_token_env": self.auth_token_env,
                "base_url": self.base_url,
                "effort": self.effort,
                "max_tokens": self.max_tokens,
                "max_turns": self.max_turns,
                "timeout_seconds": self.timeout_seconds,
                "max_retries": self.max_retries,
                "max_tool_output_chars": self.max_tool_output_chars,
                "stream": self.stream,
                "prompt": self.prompt,
                "options": self.options,
            }
        )


@dataclass
class Settings:
    workers: int = 1
    smoke_timeout_seconds: int = 1800
    full_timeout_seconds: int = 7200
    max_repair_cycles: int = 2
    command_timeout_seconds: int = 300
    command_output_chars: int = 30000


@dataclass
class TaskRecipe:
    build: list[str] = field(default_factory=list)
    tests: list[list[str]] = field(default_factory=list)

    def public_dict(self) -> dict[str, Any]:
        return {"build": self.build, "tests": self.tests}


@dataclass
class Config:
    path: Path
    agents: dict[str, AgentConfig]
    settings: Settings
    tasks: dict[str, TaskRecipe]
    raw: dict[str, Any]

    def public_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "agents": {role: self.agents[role].public_dict() for role in ROLES},
            "settings": redact(vars(self.settings)),
            "tasks": {task: self.tasks[task].public_dict() for task in TASKS},
        }


def load_config(path: str | Path | None = None) -> Config:
    config_path = Path(path or DEFAULT_CONFIG).expanduser().resolve()
    if not config_path.is_file():
        raise ConfigError(
            f"Configuration not found: {config_path}. "
            "Copy autoresearch/config.example.yaml to autoresearch/config.yaml."
        )
    with config_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ConfigError("The top-level YAML value must be a mapping")
    if int(raw.get("version", 1)) != 1:
        raise ConfigError("Only configuration version 1 is supported")
    agents_raw = raw.get("agents", {})
    missing = [role for role in ROLES if role not in agents_raw]
    if missing:
        raise ConfigError(f"Missing agent configurations: {missing}")
    agents = {
        role: AgentConfig.from_dict(role, agents_raw[role]) for role in ROLES
    }
    values = raw.get("settings", {})
    settings = Settings(
        workers=_positive_int(values, "workers", 1),
        smoke_timeout_seconds=_positive_int(values, "smoke_timeout_seconds", 1800),
        full_timeout_seconds=_positive_int(values, "full_timeout_seconds", 7200),
        max_repair_cycles=int(values.get("max_repair_cycles", 2)),
        command_timeout_seconds=_positive_int(values, "command_timeout_seconds", 300),
        command_output_chars=_positive_int(values, "command_output_chars", 30000),
    )
    if settings.max_repair_cycles < 0:
        raise ConfigError("settings.max_repair_cycles cannot be negative")
    task_values = raw.get("tasks", {})
    if not isinstance(task_values, dict):
        raise ConfigError("tasks must be a mapping")
    tasks = {}
    for task in TASKS:
        recipe = task_values.get(task, {})
        if not isinstance(recipe, dict):
            raise ConfigError(f"tasks.{task} must be a mapping")
        build = recipe.get("build", [])
        tests = recipe.get("tests", [])
        if not isinstance(build, list) or not all(
            isinstance(part, str) and part for part in build
        ):
            raise ConfigError(f"tasks.{task}.build must be an argument array")
        if not isinstance(tests, list) or not all(
            isinstance(command, list)
            and command
            and all(isinstance(part, str) and part for part in command)
            for command in tests
        ):
            raise ConfigError(f"tasks.{task}.tests must be a list of argument arrays")
        tasks[task] = TaskRecipe(build=build, tests=tests)
    return Config(config_path, agents, settings, tasks, raw)
