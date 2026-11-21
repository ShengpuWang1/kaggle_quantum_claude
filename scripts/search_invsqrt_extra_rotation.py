"""Search for one inserted Z rotation that improves the full-domain invsqrt margin."""

import argparse
from fractions import Fraction
import heapq
import json
import math
import random
import sys
from pathlib import Path

import kickmix as km
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from optimize_invsqrt_rotations import decimal, simulate, official
from optimize_invsqrt_rotations_cutting import response, solve, tightest_full_domain
from profile_invsqrt_gates import input_qubits, register


def feature_locations(lines, xs, active, weights, limit, seed=913):
    shots = len(xs)
    mask = (1 << shots) - 1
    rng = random.Random(seed)
    qubits = input_qubits(xs)
    bits = {}
    conditions = [mask]
    seen = set()
    heap = []
    serial = 0

    def offer(value, line, wire):
        nonlocal serial
        if not value or value in seen:
            return
        seen.add(value)
        reduced = sum(weight for position, weight in zip(active, weights) if (value >> position) & 1) / 512
        improvement = -reduced
        if improvement <= 1e-10:
            return
        serial += 1
        row = (improvement, serial, value, line, wire)
        if len(heap) < limit:
            heapq.heappush(heap, row)
        elif improvement > heap[0][0]:
            heapq.heapreplace(heap, row)

    for index, line in enumerate(lines):
        condition = conditions[-1]
        for wire in range(63):
            offer(qubits[wire] & condition, index, wire)
        operation = line.split()
        name = operation[0]
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
            qubits[register(operation[1])] &= mask ^ condition
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
            qubits[target] ^= qubits[a] & qubits[b] & condition
        elif name == "SWAP":
            a, b = map(register, operation[1:3])
            delta = (qubits[a] ^ qubits[b]) & condition
            qubits[a] ^= delta
            qubits[b] ^= delta
        elif name == "CSWAP":
            control, a, b = map(register, operation[1:4])
            fire = qubits[control] & (qubits[a] ^ qubits[b]) & condition
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
        elif name != "CCZ":
            raise ValueError((index, operation))
    assert len(conditions) == 1
    return sorted(heap, reverse=True), len(seen)


def feature_vector(value, shots):
    return np.asarray([(value >> shot) & 1 for shot in range(shots)], dtype=np.int64)


def estimated_score(min_margin, rotations=42):
    if min_margin <= 0:
        return None
    eps = math.pi * min_margin / 2**64 / rotations
    t_count = 1 + rotations * official.rotation_t_count(eps)
    return 63 * (1329.5002244928278 + t_count / official.T_PER_TOFFOLI)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("circuit", type=Path)
    parser.add_argument("--tightest", type=int, default=512)
    parser.add_argument("--screen-limit", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)

    original = km.Circuit.from_file(args.circuit, format="kmb")
    lines = str(original).splitlines()
    indices = [
        index for index, line in enumerate(lines)
        if line.startswith("Z_POW ") and official.z_pow_class(Fraction(line.split()[2])) == "rotation"
    ]
    spec = official.ProblemSpecInvSqrt.for_n_p(10, shots_per_x=1)
    tightest = tightest_full_domain(original, spec, args.tightest, args.batch_size)
    xs = np.asarray([row["x"] for row in tightest], dtype=np.uint64)
    target, tolerance = official.reference_values(spec, xs)
    step = Fraction(1, 1 << 40)
    error, matrix = response(lines, indices, xs, target, step, 1 << 23)
    baseline = solve([error], [matrix], tolerance, 0)
    dual = baseline.ineqlin.marginals
    difference = dual[:len(xs)] - dual[len(xs):]
    active = [int(i) for i in np.flatnonzero(np.abs(difference) > 1e-10)]
    weights = difference[active]
    print(json.dumps({"training_inputs": len(xs), "baseline_margin": baseline.x[-1] * 2**32, "active_dual_rows": len(active), "feature_location": "scanning"}), flush=True)
    screened, unique = feature_locations(lines, xs, active, weights, args.screen_limit)
    print(json.dumps({"unique_features": unique, "screened_features": len(screened)}), flush=True)

    best = None
    for rank, (improvement, _, value, line, wire) in enumerate(screened):
        column = feature_vector(value, len(xs))
        expanded = np.column_stack([matrix, column])
        result = solve([error], [expanded], tolerance, 0)
        margin = result.x[-1] * 2**32
        if best is None or margin > best[0]:
            best = margin, result, value, line, wire, improvement
        if (rank + 1) % 100 == 0:
            print(json.dumps({"solved": rank + 1, "best_training_margin": best[0]}), flush=True)
    if best is None:
        raise RuntimeError("No improving phase feature passed the dual screen")

    margin, result, value, line, wire, improvement = best
    new_lines = lines.copy()
    for index, adjustment in zip(indices, result.x[:-2]):
        operation = new_lines[index].split()
        operation[2] = decimal(Fraction(operation[2]) + Fraction(str(float(adjustment))) * step)
        new_lines[index] = " ".join(operation)
    angle = decimal(Fraction(str(float(result.x[-2]))) * step)
    new_lines.insert(line, f"Z_POW q{wire} {angle}")
    candidate = km.Circuit("\n".join(new_lines))
    full = tightest_full_domain(candidate, spec, args.tightest, args.batch_size)
    report = {
        "baseline_training_margin": float(baseline.x[-1] * 2**32),
        "best_training_margin": float(margin),
        "full_min_margin": full[0]["margin"],
        "full_worst_x": full[0]["x"],
        "estimated_full_score": estimated_score(full[0]["margin"]),
        "insert_before_line": line,
        "wire": wire,
        "angle": angle,
        "dual_improvement": improvement,
        "unique_features": unique,
        "screened_features": len(screened),
        "existing_adjustments": dict(zip(map(str, indices), result.x[:-2].tolist())),
        "full_tightest": full,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    candidate.to_file(args.output, format="kmb")
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key not in {"existing_adjustments", "full_tightest"}}, indent=2))


if __name__ == "__main__":
    main()
