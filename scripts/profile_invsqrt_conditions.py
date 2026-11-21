"""Find classical bits that safely guard each invsqrt nonlinear gate."""

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import kickmix as km
from profile_invsqrt_gates import FULL_MAX_X, input_qubits, reference_values, register


def run(lines, seed, xs, valid, statistics=None, executions=None, actions=None):
    shots = len(xs)
    mask = (1 << shots) - 1
    rng = random.Random(seed)
    qubits = input_qubits(xs)
    bits = {}
    conditions = [mask]

    def guard(index, fire, condition):
        if statistics is not None:
            executions[index] += condition.bit_count()
            actions[index] += fire.bit_count()
            for bit in valid.get(index, ()):
                statistics[index, bit] += (condition & (mask ^ bits.get(bit, 0))).bit_count()
            return
        if not fire or index not in valid:
            return
        invalid = [bit for bit in valid[index] if fire & (mask ^ bits.get(bit, 0))]
        valid[index].difference_update(invalid)

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
            qubits[register(operation[1])] ^= condition
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
            guard(index, fire, condition)
            qubits[target] ^= fire
        elif name == "CCZ":
            a, b = map(register, operation[1:3])
            guard(index, qubits[a] & qubits[b] & condition, condition)
        elif name == "SWAP":
            a, b = map(register, operation[1:3])
            delta = (qubits[a] ^ qubits[b]) & condition
            qubits[a] ^= delta
            qubits[b] ^= delta
        elif name == "CSWAP":
            control, a, b = map(register, operation[1:4])
            fire = qubits[control] & (qubits[a] ^ qubits[b]) & condition
            guard(index, fire, condition)
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("circuit", type=Path)
    parser.add_argument("--shots", type=int, default=4096)
    parser.add_argument("--seeds", type=int, default=2)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    circuit = km.Circuit.from_file(args.circuit, format="kmb")
    lines = str(circuit).splitlines()
    bit_ids = sorted({register(token) for line in lines for token in line.split() if token.startswith("b") and token[1:].isdigit()})
    gates = [index for index, line in enumerate(lines) if line.split()[0] in {"CCX", "CSWAP", "CCZ"}]
    valid = {index: set(bit_ids) for index in gates}
    domains = [list(range(1, args.shots + 1))]
    rng = random.Random(81723)
    domains.append([rng.randrange(1, FULL_MAX_X + 1) for _ in range(args.shots)])
    for domain_index, xs in enumerate(domains):
        expected = reference_values(circuit, xs)
        for seed in range(args.seeds):
            actual = run(lines, 1000 * domain_index + seed, xs, valid)
            mismatches = [wire for wire in range(63) if actual[wire] != expected[wire]]
            if mismatches:
                raise AssertionError({"domain": domain_index, "seed": seed, "value_mismatch_wires": mismatches})
        print(f"domain {domain_index}: {sum(bool(candidates) for candidates in valid.values())} gates have guards", flush=True)
    candidates = [
        {"index": index, "line": lines[index], "bits": sorted(valid[index])}
        for index in gates if valid[index]
    ]
    statistics = {(index, bit): 0 for index in gates for bit in valid[index]}
    executions = {index: 0 for index in gates}
    actions = {index: 0 for index in gates}
    for domain_index, xs in enumerate(domains):
        for seed in range(args.seeds):
            run(lines, 1000 * domain_index + seed, xs, valid, statistics, executions, actions)
    total_shots = len(domains) * args.seeds * args.shots
    ranked = sorted(
        (
            {
                "index": index,
                "line": lines[index],
                "bit": bit,
                "average_original_executions": executions[index] / total_shots,
                "average_actions": actions[index] / total_shots,
                "average_skipped": skipped / total_shots,
            }
            for (index, bit), skipped in statistics.items() if skipped
        ),
        key=lambda entry: entry["average_skipped"], reverse=True,
    )
    result = {"shots_per_domain": args.shots, "seeds_per_domain": args.seeds, "candidates": candidates, "ranked": ranked}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"candidate_gates": len(candidates), "top_guards": ranked[:30]}, indent=2))


if __name__ == "__main__":
    main()
