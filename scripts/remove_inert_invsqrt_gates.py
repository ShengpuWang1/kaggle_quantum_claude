"""Remove profiled inert invsqrt gates and check full value/phase equivalence."""

import argparse
import json
from pathlib import Path

import kickmix as km
import numpy as np

ADDRESS = tuple(range(14, 22))
SHOTS = 256


def simulate(circuit, seed):
    simulator = km.Simulator(batch_size=SHOTS, seed=seed)
    for bit, wire in enumerate(ADDRESS):
        simulator.write_across_shots(
            km.q(wire), np.asarray([(address >> bit) & 1 for address in range(SHOTS)], dtype=np.bool_)
        )
    simulator.do(circuit)
    values = [simulator.read_across_shots(km.q(wire)) for wire in range(63)]
    phases = [simulator.read_shot_phase(shot) for shot in range(SHOTS)]
    return values, phases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("circuit", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("--seeds", type=int, default=16)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    old = km.Circuit.from_file(args.circuit, format="kmb")
    lines = str(old).splitlines()
    profile = json.loads(args.profile.read_text())
    removed = {entry["index"] for entry in profile["inert"]}
    assert all(lines[index] == entry["line"] for entry in profile["inert"] for index in [entry["index"]])
    new_lines = [line for index, line in enumerate(lines) if index not in removed]
    new = km.Circuit("\n".join(new_lines))
    old_stats = old.operation_statistics()
    new_stats = new.operation_statistics()
    assert new.num_qubits == old.num_qubits == 63
    assert old_stats.num_toffoli_like - new_stats.num_toffoli_like == len(removed)
    assert new_stats.num_z_pow() == old_stats.num_z_pow()
    for seed in range(args.seeds):
        old_values, old_phases = simulate(old, seed)
        new_values, new_phases = simulate(new, seed)
        value_mismatches = [wire for wire in range(63) if not np.array_equal(old_values[wire], new_values[wire])]
        phase_mismatches = [shot for shot in range(SHOTS) if old_phases[shot] != new_phases[shot]]
        if value_mismatches or phase_mismatches:
            raise AssertionError({"seed": seed, "value_mismatches": value_mismatches, "phase_mismatches": phase_mismatches[:10]})
        print(f"seed {seed}: all 256 values and phases match", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    new.to_file(args.output, format="kmb")
    result = {
        "removed": len(removed),
        "old_toffoli_like": old_stats.num_toffoli_like,
        "new_toffoli_like": new_stats.num_toffoli_like,
        "qubits": new.num_qubits,
        "seeds": args.seeds,
        "shots": args.seeds * SHOTS,
        "full_value_phase_equivalence": True,
    }
    args.report.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
