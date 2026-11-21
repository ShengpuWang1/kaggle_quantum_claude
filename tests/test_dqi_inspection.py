"""Test DQI structural inspection with small generated circuit files."""

import sys
from pathlib import Path

import kickmix as km
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import inspect_dqi_circuit as inspect


def circuit_text(extra=""):
    lines = []
    for i in range(70):
        lines.append(f'REGISTER r{i} "S{i}"')
        lines.extend(f"APPEND_TO_REGISTER q{12 * i + k} r{i}" for k in range(12))
    for i in range(4095):
        lines.append(f'REGISTER r{70 + i} "E{i}"')
        lines.extend(f"APPEND_TO_REGISTER b{12 * i + k} r{70 + i}" for k in range(12))
    lines.extend(f"X q{i}" for i in range(840, 897))
    lines.extend(f"BIT_STORE0 b{i}" for i in range(49_140, 103_536))
    if extra:
        lines.append(extra)
    return "\n".join(lines)


def write_circuit(path, text):
    km.Circuit(text).to_file(path, format="kmb")
    return path


def test_valid_dqi_interface_and_canonical_hash(tmp_path):
    path = write_circuit(tmp_path / "dqi.kmb", circuit_text())
    digest = inspect.sha256(path)

    report = inspect.inspect_circuit(path, expected_sha256=digest)

    assert report["qubits"] == 897
    assert report["bits"] == 103_536
    assert report["registers"] == 4165
    assert report["canonical_sha256"] == digest
    assert report["static_toffoli_like"] == 0


def test_register_mismatch_is_rejected(tmp_path):
    path = write_circuit(
        tmp_path / "dqi.kmb", circuit_text('REGISTER r4165 "extra"')
    )
    with pytest.raises(ValueError, match="register mismatch"):
        inspect.inspect_circuit(path, expected_sha256=None, check_canonical=False)


def test_hash_mismatch_and_z_pow_are_rejected(tmp_path):
    path = tmp_path / "dqi.kmb"
    path.write_bytes(b"not the expected circuit")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        inspect.inspect_circuit(path)

    phased = write_circuit(tmp_path / "phased.kmb", "Z_POW q0 0.25")
    with pytest.raises(ValueError, match="forbidden Z_POW"):
        inspect.inspect_circuit(
            phased,
            expected_sha256=None,
            validate_interface=False,
            check_canonical=False,
        )
