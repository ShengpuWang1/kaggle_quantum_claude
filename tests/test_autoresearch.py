import json
import math
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml

from autoresearch.agents import RoleRunner, result_schemas
from autoresearch.artifacts import copy_task, manifest, verify_manifest
from autoresearch.config import AgentConfig, load_config, redact
from autoresearch.providers import AnthropicProvider, OpenAIProvider, ToolCall
from autoresearch.scoring import leaderboard_estimate
from autoresearch.tools import ToolContext
from scripts import autoresearch_verifier as verifier


def test_config_and_redaction(tmp_path):
    source = yaml.safe_load(
        Path("autoresearch/config.example.yaml").read_text(encoding="utf-8")
    )
    source["agents"]["director"]["api_key"] = "not-for-records"
    source["agents"]["director"]["options"] = {"nested": {"token": "hidden"}}
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(source), encoding="utf-8")
    config = load_config(path)
    public = json.dumps(config.public_dict())
    assert "not-for-records" not in public
    assert "hidden" not in public
    assert "AUTORESEARCH_DIRECTOR_API_KEY" in public
    assert config.tasks["invsqrt"].build[0] == "{python}"
    assert config.public_dict()["agents"]["director"]["max_tokens"] == 16000
    assert redact({"salt_env": "SALT_NAME", "salt": "value"}) == {
        "salt_env": "SALT_NAME",
        "salt": "<redacted>",
    }


def test_tool_confinement_and_role_loop(tmp_path):
    root = tmp_path / "root"
    workspace = root / "workspace"
    workspace.mkdir(parents=True)
    (root / ".secrets").mkdir()
    (root / ".secrets" / "key").write_text("secret", encoding="utf-8")
    tools = ToolContext(workspace, writable=True, read_root=root)
    assert tools.execute(type("Call", (), {"name": "read_file", "arguments": {"path": "../.secrets/key"}})()).is_error
    result = tools.execute(ToolCall("1", "write_file", {"path": "source/example.py", "content": "ok"}))
    assert not result.is_error
    assert (workspace / "source/example.py").read_text() == "ok"
    assert tools.execute(ToolCall("2", "write_file", {"path": "../outside", "content": "bad"})).is_error

    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "director.md").write_text("test", encoding="utf-8")
    plan = {
        "title": "Test",
        "task": "invsqrt",
        "evidence": [
            {
                "source_type": "notebook",
                "title": "Inspected notebook",
                "url": "https://www.kaggle.com/code/example/notebook",
                "local_path": "",
                "insight": "A tested idea",
            }
        ],
        "hypothesis": "A test hypothesis",
        "implementation_steps": ["Do one thing"],
        "expected_resource_effect": "None",
        "acceptance_criteria": ["Valid result"],
    }
    agent = AgentConfig(
        provider="fake",
        model="fake",
        prompt=str(prompts / "director.md"),
        options={"responses": [{"tool_calls": [{"name": "submit_plan", "arguments": plan}]}]},
    )
    result = RoleRunner(agent, "director").run(
        "plan", tools=tools, result_schema=result_schemas()["director"]
    )
    assert result.data == plan


def test_tool_error_events_omit_urls_and_credentials(tmp_path, monkeypatch):
    root = tmp_path / "root"
    workspace = root / "workspace"
    workspace.mkdir(parents=True)
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "director.md").write_text("test", encoding="utf-8")
    monkeypatch.setenv("TEST_TOOL_EVENT_KEY", "environment-secret")
    tools = ToolContext(workspace, writable=False, read_root=root)

    def fail(_args):
        raise ValueError(
            "bad configured-secret and environment-secret\n"
            "https://example.com/source?api_key=url-secret"
        )

    tools._handlers["read_file"] = fail
    plan = {
        "title": "Test",
        "task": "invsqrt",
        "evidence": [
            {
                "source_type": "notebook",
                "title": "Inspected notebook",
                "url": "https://www.kaggle.com/code/example/notebook",
                "local_path": "",
                "insight": "A tested idea",
            }
        ],
        "hypothesis": "A test hypothesis",
        "implementation_steps": ["Do one thing"],
        "expected_resource_effect": "None",
        "acceptance_criteria": ["Valid result"],
    }
    agent = AgentConfig(
        provider="fake",
        model="fake",
        api_key="configured-secret",
        api_key_env="TEST_TOOL_EVENT_KEY",
        prompt=str(prompts / "director.md"),
        options={
            "responses": [
                {
                    "tool_calls": [
                        {"name": "read_file", "arguments": {"path": "anything"}}
                    ]
                },
                {"tool_calls": [{"name": "submit_plan", "arguments": plan}]},
            ]
        },
    )
    events = []
    RoleRunner(agent, "director").run(
        "plan",
        tools=tools,
        result_schema=result_schemas()["director"],
        event=events.append,
    )
    error = next(event for event in events if event["kind"] == "tool_result")
    assert error["is_error"]
    assert error["error_summary"] == (
        "ValueError: bad <redacted> and <redacted> <url>"
    )
    assert "url-secret" not in error["error_summary"]
    assert len(error["error_summary"]) <= 300


def test_anthropic_bearer_auth_uses_auth_token_without_network(monkeypatch):
    monkeypatch.setenv("TEST_ARK_KEY", "secret-token")
    config = AgentConfig(
        provider="anthropic",
        model="ark-code-latest",
        auth_token_env="TEST_ARK_KEY",
        base_url="https://ark.cn-beijing.volces.com/api/plan",
    )
    with patch("anthropic.Anthropic") as client:
        AnthropicProvider(config)
    kwargs = client.call_args.kwargs
    assert kwargs["auth_token"] == "secret-token"
    assert "api_key" not in kwargs
    assert kwargs["base_url"] == "https://ark.cn-beijing.volces.com/api/plan"
    assert config.has_credentials()
    assert "secret-token" not in json.dumps(config.public_dict())


def test_provider_payload_translation_without_network():
    config = AgentConfig(
        provider="anthropic", model="model", api_key="key", effort="high", stream=False
    )
    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider.config = config
    captured = {}

    class Messages:
        def create(self, **request):
            captured.update(request)
            return SimpleNamespace(
                stop_reason="tool_use",
                content=[
                    SimpleNamespace(
                        type="thinking", model_dump=lambda exclude_none: {"type": "thinking", "thinking": "t", "signature": "s"}
                    ),
                    SimpleNamespace(
                        type="tool_use",
                        id="call-1",
                        name="read_file",
                        input={"path": "README.md"},
                        model_dump=lambda exclude_none: {
                            "type": "tool_use", "id": "call-1", "name": "read_file", "input": {"path": "README.md"}
                        },
                    ),
                ],
                usage=None,
            )

    provider.client = SimpleNamespace(messages=Messages())
    turn = provider.complete(system="system", messages=[], tools=[])
    assert captured["thinking"] == {"type": "adaptive"}
    assert captured["output_config"] == {"effort": "high"}
    assert turn.assistant_message["content"][0]["signature"] == "s"
    assert turn.tool_calls[0].arguments == {"path": "README.md"}

    openai = OpenAIProvider.__new__(OpenAIProvider)
    openai.config = AgentConfig(provider="openai", model="model", api_key="key", effort="medium")
    message = SimpleNamespace(
        content=None,
        tool_calls=[
            SimpleNamespace(
                id="call-2",
                function=SimpleNamespace(name="read_file", arguments='{"path":"README.md"}'),
            )
        ],
        model_dump=lambda exclude_none: {"role": "assistant", "content": None},
    )
    response = SimpleNamespace(
        choices=[SimpleNamespace(finish_reason="tool_calls", message=message)], usage=None
    )
    openai.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **request: response)
        )
    )
    turn = openai.complete(system="system", messages=[], tools=[])
    assert turn.tool_calls[0].name == "read_file"


def test_manifest_and_score(tmp_path):
    (tmp_path / "invsqrt.kmb").write_bytes(b"candidate")
    expected = manifest(tmp_path, "invsqrt")
    verify_manifest(tmp_path, expected)
    destination = tmp_path / "copy"
    copy_task(tmp_path, "invsqrt", destination)
    assert manifest(destination, "invsqrt")["digest"] == expected["digest"]
    (tmp_path / "invsqrt.kmb").write_bytes(b"changed")
    with pytest.raises(ValueError):
        verify_manifest(tmp_path, expected)
    score = leaderboard_estimate(
        {"invsqrt": 1, "dqi": 4, "dfthcsos": 2},
        {"invsqrt": 2, "dqi": 4, "dfthcsos": 8},
    )
    assert math.isclose(score, (2 * 1 * 4) ** (1 / 3))


def test_task_only_command_building(tmp_path):
    (tmp_path / "invsqrt.kmb").write_bytes(b"candidate")
    commands = verifier.build_commands(
        tmp_path, full=False, workers=1, task="invsqrt"
    )
    assert set(commands) == {"invsqrt"}
    assert "--max-x" in commands["invsqrt"]


@pytest.mark.parametrize("task", ["invsqrt", "dqi"])
def test_command_building_rejects_missing_or_ambiguous_circuits(tmp_path, task):
    with pytest.raises(ValueError, match=f"Expected exactly one {task}.*found 0"):
        verifier.build_commands(tmp_path, full=False, workers=1, task=task)
    (tmp_path / f"{task}.kmb").write_bytes(b"candidate")
    (tmp_path / f"{task}.kmx").write_bytes(b"candidate")
    with pytest.raises(ValueError, match=f"Expected exactly one {task}.*found 2"):
        verifier.build_commands(tmp_path, full=False, workers=1, task=task)


@pytest.mark.parametrize("task", ["invsqrt", "dqi"])
def test_command_building_accepts_kmx(tmp_path, task):
    circuit = tmp_path / f"{task}.kmx"
    circuit.write_bytes(b"candidate")
    commands = verifier.build_commands(tmp_path, full=False, workers=1, task=task)
    assert commands[task][1] == str(circuit)


def test_missing_artifact_never_starts_verifier(tmp_path, monkeypatch):
    popen_calls = []

    def unexpected_popen(*args, **kwargs):
        popen_calls.append((args, kwargs))
        raise AssertionError("Verifier subprocess must not start")

    monkeypatch.setattr(verifier.subprocess, "Popen", unexpected_popen)
    with pytest.raises(ValueError, match="Expected exactly one invsqrt.*found 0"):
        verifier.run_verification(
            source=tmp_path,
            task="invsqrt",
            run_dir=tmp_path / "run",
        )
    assert popen_calls == []


def test_verifier_redaction_and_timeout(tmp_path, monkeypatch):
    secret = "private-validation-value"
    script = tmp_path / "fake_verifier.py"
    script.write_text(
        "import argparse,json,sys,time\n"
        "p=argparse.ArgumentParser();p.add_argument('--salt');p.add_argument('--sleep',type=float,default=0);a=p.parse_args()\n"
        "time.sleep(a.sleep)\n"
        "print(json.dumps({'status':'PASS','score':12.5,'echo':a.salt}))\n",
        encoding="utf-8",
    )

    def commands(source, *, full, workers, salt=None, task="all"):
        command = [str(script), "--sleep", "0"]
        if salt is not None:
            command += ["--salt", salt]
        return {"invsqrt": command}

    monkeypatch.setattr(verifier, "build_commands", commands)
    monkeypatch.setenv("TEST_PRIVATE_SALT", secret)
    run, results = verifier.run_verification(
        source=tmp_path,
        task="invsqrt",
        run_dir=tmp_path / "run",
        salt_env="TEST_PRIVATE_SALT",
    )
    assert results["tasks"]["invsqrt"]["score"] == 12.5
    assert secret not in (run / "invsqrt.json").read_text()
    assert secret not in (run / "run.json").read_text()
    assert "<redacted>" in (run / "invsqrt.json").read_text()

    def sleeping(source, *, full, workers, salt=None, task="all"):
        return {"invsqrt": [str(script), "--sleep", "10"]}

    monkeypatch.setattr(verifier, "build_commands", sleeping)
    start = time.monotonic()
    run, results = verifier.run_verification(
        source=tmp_path,
        task="invsqrt",
        run_dir=tmp_path / "timeout",
        timeout_seconds=0.1,
    )
    assert time.monotonic() - start < 5
    assert results["tasks"]["invsqrt"]["timed_out"] is True
    assert results["tasks"]["invsqrt"]["status"] == "FAIL"
