"""Profile invsqrt nonlinear gates over official inputs and random HMR outcomes."""

import argparse
import json
import random
from pathlib import Path

import kickmix as km
import numpy as np

INPUT = tuple(range(22))
FULL_MAX_X = 3133452


def register(token):
    return int(token[1:])


def input_qubits(xs):
    qubits = [0] * 63
    for bit, wire in enumerate(INPUT):
        qubits[wire] = sum(((int(x) >> bit) & 1) << shot for shot, x in enumerate(xs))
    return qubits


def run(lines, seed, activity, xs):
    shots = len(xs)
    mask = (1 << shots) - 1
    rng = random.Random(seed)
    qubits = input_qubits(xs)
    bits = {}
    conditions = [mask]
    for index, line in enumerate(lines):
        operation = line.split()
        name = operation[0]
        condition = conditions[-1]
        if operation[-2:-1] == ["if"]:
            condition &= bits.get(register(operation[-1]), 0)
        if name == "PUSH_CONDITION":
            conditions.append(condition)
        elif name == "POP_CONDITION":
            conditions.pop()
        elif name in {"APPEND_TO_REGISTER", "REGISTER", "CZ", "Z", "NEG", "Z_POW"}:
            pass
        elif name == "HMR":
            wire, bit = map(register, operation[1:3])
            qubits[wire] &= mask ^ condition
            outcome = rng.getrandbits(shots)
            bits[bit] = (bits.get(bit, 0) & (mask ^ condition)) | (outcome & condition)
        elif name == "R":
            wire = register(operation[1])
            qubits[wire] &= mask ^ condition
        elif name == "X":
            wire = register(operation[1])
            qubits[wire] ^= condition
        elif name == "CX":
            source, target = operation[1:3]
            if source.startswith("q"):
                qubits[register(target)] ^= qubits[register(source)] & condition
            else:
                source_id, target_id = register(source), register(target)
                bits[target_id] = bits.get(target_id, 0) ^ (bits.get(source_id, 0) & condition)
        elif name == "CCX":
            a, b, target = map(register, operation[1:4])
            fire = qubits[a] & qubits[b] & condition
            activity[index] |= fire
            qubits[target] ^= fire
        elif name == "CCZ":
            a, b = map(register, operation[1:3])
            activity[index] |= qubits[a] & qubits[b] & condition
        elif name == "SWAP":
            a, b = map(register, operation[1:3])
            delta = (qubits[a] ^ qubits[b]) & condition
            qubits[a] ^= delta
            qubits[b] ^= delta
        elif name == "CSWAP":
            control, a, b = map(register, operation[1:4])
            fire = qubits[control] & (qubits[a] ^ qubits[b]) & condition
            activity[index] |= fire
            qubits[a] ^= fire
            qubits[b] ^= fire
        elif name == "BIT_STORE0":
            bit = register(operation[1])
            bits[bit] = bits.get(bit, 0) & (mask ^ condition)
        elif name == "BIT_STORE1":
            bit = register(operation[1])
            bits[bit] = bits.get(bit, 0) | condition
        elif name == "BIT_INVERT":
            bit = register(operation[1])
            bits[bit] = bits.get(bit, 0) ^ condition
        else:
            raise ValueError((index, operation))
    assert len(conditions) == 1
    return qubits


def reference_values(circuit, xs):
    shots = len(xs)
    simulator = km.Simulator(batch_size=shots, seed=913)
    values = np.asarray(xs, dtype=np.uint64)
    input_bits = ((values[None, :] >> np.arange(22, dtype=np.uint64)[:, None]) & 1).astype(np.bool_)
    simulator.write_across_shots(km.array([km.q(wire) for wire in INPUT]), input_bits)
    simulator.do(circuit)
    return [sum(int(value) << shot for shot, value in enumerate(simulator.read_across_shots(km.q(wire)))) for wire in range(63)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("circuit", type=Path)
    parser.add_argument("--max-x", type=int, default=4096)
    parser.add_argument("--shots", type=int, default=4096)
    parser.add_argument("--random-full", action="store_true")
    parser.add_argument("--seeds", type=int, default=8)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    circuit = km.Circuit.from_file(args.circuit, format="kmb")
    lines = str(circuit).splitlines()
    activity = {index: 0 for index, line in enumerate(lines) if line.split()[0] in {"CCX", "CSWAP", "CCZ"}}
    if args.random_full:
        rng = random.Random(81723)
        xs = [rng.randrange(1, FULL_MAX_X + 1) for _ in range(args.shots)]
        domain = f"random x in 1..{FULL_MAX_X}"
    else:
        xs = list(range(1, args.max_x + 1))
        domain = f"all x in 1..{args.max_x}"
    expected = reference_values(circuit, xs)
    for seed in range(args.seeds):
        actual = run(lines, seed, activity, xs)
        mismatches = [wire for wire in range(63) if actual[wire] != expected[wire]]
        if mismatches:
            raise AssertionError({"seed": seed, "value_mismatch_wires": mismatches})
        print(f"seed {seed}: {sum(not value for value in activity.values())} inactive gates", flush=True)
    inert = [
        {"index": index, "line": lines[index]}
        for index, value in sorted(activity.items()) if not value
    ]
    result = {"domain": domain, "seeds": args.seeds, "shots_per_seed": len(xs), "nonlinear_gates": len(activity), "inert": inert}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
