"""Check verifier command construction without running the official simulators."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import verify_submission as verify

VERIFIERS = Path("/official/verifiers")


def add_circuit(source, task, extension="kmb"):
    path = source / f"{task}.{extension}"
    path.write_bytes(b"placeholder")
    return path


def test_invsqrt_only_ignores_unselected_missing_and_ambiguous_inputs(tmp_path):
    circuit = add_circuit(tmp_path, "invsqrt")
    add_circuit(tmp_path, "dqi", "kmb")
    add_circuit(tmp_path, "dqi", "kmx")

    commands = verify.build_commands(tmp_path, VERIFIERS, task="invsqrt")

    assert commands == {
        "invsqrt": [
            str(VERIFIERS / "invsqrt/verify_submission_invsqrt.py"),
            str(circuit),
            "--max-workers",
            "1",
            "--max-x",
            "4096",
        ]
    }


@pytest.mark.parametrize("task", ["invsqrt", "dqi"])
def test_missing_selected_circuit_has_clear_error(tmp_path, task):
    with pytest.raises(ValueError, match=f"Expected exactly one {task}"):
        verify.build_commands(tmp_path, VERIFIERS, task=task)


@pytest.mark.parametrize("task", ["invsqrt", "dqi"])
def test_ambiguous_selected_circuit_has_clear_error(tmp_path, task):
    add_circuit(tmp_path, task, "kmb")
    add_circuit(tmp_path, task, "kmx")

    with pytest.raises(ValueError, match="found 2"):
        verify.build_commands(tmp_path, VERIFIERS, task=task)


@pytest.mark.parametrize("task", ["invsqrt", "dqi", "dfthcsos"])
def test_each_task_constructs_only_its_own_command(tmp_path, task):
    if task != "dfthcsos":
        add_circuit(tmp_path, task, "kmx")

    commands = verify.build_commands(tmp_path, VERIFIERS, task=task, full=True)

    assert list(commands) == [task]
    assert "--max-x" not in commands[task]
    assert "--num-shots" not in commands[task]


def test_all_tasks_preserve_legacy_commands_when_salt_is_omitted(tmp_path):
    invsqrt = add_circuit(tmp_path, "invsqrt")
    dqi = add_circuit(tmp_path, "dqi")

    commands = verify.build_commands(tmp_path, VERIFIERS, workers=3)

    assert commands == {
        "invsqrt": [
            str(VERIFIERS / "invsqrt/verify_submission_invsqrt.py"),
            str(invsqrt),
            "--max-workers",
            "3",
            "--max-x",
            "4096",
        ],
        "dqi": [
            str(VERIFIERS / "dqi/verify_submission_dqi.py"),
            str(dqi),
            "--max-workers",
            "3",
            "--num-shots",
            "4096",
        ],
        "dfthcsos": [
            str(VERIFIERS / "dfthcsos/verify.py"),
            str(tmp_path / "dfthcsos"),
        ],
    }


def test_full_mode_and_salt_apply_to_every_task(tmp_path):
    add_circuit(tmp_path, "invsqrt")
    add_circuit(tmp_path, "dqi")

    commands = verify.build_commands(
        tmp_path, VERIFIERS, full=True, workers=2, salt="validation-seed"
    )

    for command in commands.values():
        assert command[-2:] == ["--salt", "validation-seed"]
        assert "--max-x" not in command
        assert "--num-shots" not in command
    assert commands["invsqrt"][2:4] == ["--max-workers", "2"]
    assert commands["dqi"][2:4] == ["--max-workers", "2"]
