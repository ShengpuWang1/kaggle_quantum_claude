"""Inspect a DQI circuit and enforce the published decoder's structural contract."""

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

import kickmix as km

EXPECTED_SHA256 = "53d8b2edf251e2a0c54c401a97d1396c7ed309e1cbfaab8d54a2c99a11ed6552"
EXPECTED_QUBITS = 897
EXPECTED_BITS = 103_536


def sha256(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def expected_registers():
    expected = {
        f"S{i}": [f"q{12 * i + k}" for k in range(12)] for i in range(70)
    }
    expected.update(
        {
            f"E{i}": [f"b{12 * i + k}" for k in range(12)]
            for i in range(4095)
        }
    )
    return expected


def validate_registers(circuit):
    actual = {
        name: [str(token) for token in tokens]
        for name, tokens in circuit.register_data.items()
    }
    expected = expected_registers()
    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        mismatched = sorted(
            name for name in set(actual) & set(expected) if actual[name] != expected[name]
        )
        raise ValueError(
            "DQI register mismatch: "
            f"missing={missing[:5]}, extra={extra[:5]}, mismatched={mismatched[:5]}"
        )


def inspect_circuit(
    path,
    *,
    expected_sha256=EXPECTED_SHA256,
    validate_interface=True,
    check_canonical=True,
):
    path = Path(path)
    raw_sha256 = sha256(path)
    if expected_sha256 is not None and raw_sha256 != expected_sha256:
        raise ValueError(
            f"DQI SHA-256 mismatch: expected {expected_sha256}, got {raw_sha256}"
        )
    circuit = km.Circuit.from_file(path, format="kmb")
    if validate_interface:
        if circuit.num_qubits != EXPECTED_QUBITS:
            raise ValueError(f"Expected {EXPECTED_QUBITS} qubits, got {circuit.num_qubits}")
        if circuit.num_bits != EXPECTED_BITS:
            raise ValueError(f"Expected {EXPECTED_BITS} bits, got {circuit.num_bits}")
        validate_registers(circuit)
    statistics = circuit.operation_statistics()
    if statistics["Z_POW"]:
        raise ValueError("DQI circuit contains forbidden Z_POW operations")
    canonical_sha256 = None
    if check_canonical:
        with tempfile.TemporaryDirectory(prefix="inspect-dqi-") as directory:
            canonical = Path(directory) / "canonical.kmb"
            circuit.to_file(canonical, format="kmb")
            canonical_sha256 = sha256(canonical)
        if canonical_sha256 != raw_sha256:
            raise ValueError(
                f"Canonical KMB hash differs: raw={raw_sha256}, canonical={canonical_sha256}"
            )
    return {
        "path": str(path),
        "sha256": raw_sha256,
        "canonical_sha256": canonical_sha256,
        "qubits": circuit.num_qubits,
        "bits": circuit.num_bits,
        "registers": circuit.num_registers,
        "operations": len(circuit),
        "static_toffoli_like": statistics.num_toffoli_like,
        "static_t_like": statistics.num_t_like,
        "reaction_depth": circuit.reaction_depth(),
        "operation_counts": dict(statistics.items()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("circuit", type=Path)
    parser.add_argument("--output", type=Path, help="Optional new JSON report path")
    parser.add_argument("--skip-interface", action="store_true")
    parser.add_argument("--skip-canonical", action="store_true")
    args = parser.parse_args()
    if args.output and args.output.exists():
        raise FileExistsError(f"Refusing to overwrite {args.output}")
    report = inspect_circuit(
        args.circuit.resolve(),
        validate_interface=not args.skip_interface,
        check_canonical=not args.skip_canonical,
    )
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
