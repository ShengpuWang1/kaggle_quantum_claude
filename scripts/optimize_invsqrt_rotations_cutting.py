"""Maximize the exact full-domain invsqrt phase margin with LP cutting planes."""

import argparse
from fractions import Fraction
import json
import sys
from pathlib import Path

import kickmix as km
import numpy as np
from scipy.optimize import linprog

sys.path.insert(0, str(Path(__file__).resolve().parent))
from optimize_invsqrt_rotations import decimal, simulate, official


def rotation_indices(circuit):
    return [
        index for index, line in enumerate(str(circuit).splitlines())
        if line.startswith("Z_POW ") and official.z_pow_class(Fraction(line.split()[2])) == "rotation"
    ]


def response(lines, indices, xs, target, step, step_units):
    circuit = km.Circuit("\n".join(lines))
    theta, error = simulate(circuit, xs, target)
    matrix = np.empty((len(xs), len(indices)), dtype=np.int64)
    for column, index in enumerate(indices):
        operation = lines[index].split()
        operation[2] = decimal(Fraction(operation[2]) + step)
        changed = lines.copy()
        changed[index] = " ".join(operation)
        new_theta, _ = simulate(km.Circuit("\n".join(changed)), xs, target)
        difference = (new_theta - theta).view(np.int64)
        assert np.all(difference % step_units == 0)
        matrix[:, column] = difference // step_units
    return error, matrix


def adjusted(lines, indices, adjustments, step):
    new_lines = lines.copy()
    for index, adjustment in zip(indices, adjustments):
        operation = new_lines[index].split()
        operation[2] = decimal(Fraction(operation[2]) + Fraction(str(float(adjustment))) * step)
        new_lines[index] = " ".join(operation)
    return new_lines


def solve(errors, matrices, tolerance, bound):
    error = np.concatenate(errors)
    matrix = np.concatenate(matrices)
    scale = float(1 << 32)
    scaled = matrix.astype(float) * (1 << 23) / scale
    normalized_error = error.astype(float) / scale
    normalized_tolerance = tolerance.astype(float) / scale
    count = matrix.shape[1]
    objective = np.zeros(count + 1)
    objective[-1] = -1
    upper = np.concatenate([
        np.column_stack([scaled, np.ones(len(error))]),
        np.column_stack([-scaled, np.ones(len(error))]),
    ])
    upper_bound = np.concatenate([
        normalized_tolerance - normalized_error,
        normalized_tolerance + normalized_error,
    ])
    result = linprog(
        objective,
        A_ub=upper,
        b_ub=upper_bound,
        bounds=[((-bound, bound) if bound else (None, None))] * count + [(None, None)],
        method="highs",
    )
    if not result.success:
        raise RuntimeError(result.message)
    return result


def tightest_full_domain(circuit, spec, limit, batch_size):
    all_xs = np.arange(1, spec.max_x + 1, dtype=np.uint64)
    target, tolerance = official.reference_values(spec, all_xs)
    tight_xs = []
    tight_margins = []
    tight_errors = []
    for start in range(0, len(all_xs), batch_size):
        xs = all_xs[start:start + batch_size]
        allowed = tolerance[start:start + batch_size]
        _, error = simulate(circuit, xs, target[start:start + batch_size])
        used = np.abs(error).view(np.uint64)
        margins = allowed.astype(np.int64) - used.astype(np.int64)
        count = min(limit, len(xs))
        selected = np.argpartition(margins, count - 1)[:count]
        tight_xs.extend(xs[selected])
        tight_margins.extend(margins[selected])
        tight_errors.extend(error[selected])
    order = np.argsort(np.asarray(tight_margins, dtype=np.int64))[:limit]
    return [
        {
            "x": int(tight_xs[i]),
            "margin": int(tight_margins[i]),
            "error": int(tight_errors[i]),
        }
        for i in order
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("circuit", type=Path)
    parser.add_argument("--initial-random", type=int, default=4096)
    parser.add_argument("--add-per-iteration", type=int, default=64)
    parser.add_argument("--max-iterations", type=int, default=30)
    parser.add_argument("--bound", type=float, default=0)
    parser.add_argument("--zero-line", type=int, action="append", default=[], help="Fix this rotation line to zero and optimize the others")
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)

    original = km.Circuit.from_file(args.circuit, format="kmb")
    lines = str(original).splitlines()
    all_indices = rotation_indices(original)
    zero_lines = set(args.zero_line)
    if not zero_lines <= set(all_indices):
        raise ValueError("Every --zero-line must identify a non-Clifford rotation")
    for index in zero_lines:
        operation = lines[index].split()
        operation[2] = "0.0"
        lines[index] = " ".join(operation)
    indices = [index for index in all_indices if index not in zero_lines]
    step = Fraction(1, 1 << 40)
    step_units = 1 << 23
    spec = official.ProblemSpecInvSqrt.for_n_p(10, shots_per_x=1)
    generator = np.random.default_rng(81723)
    random_xs = generator.integers(1, spec.max_x + 1, size=args.initial_random, dtype=np.uint64)
    xs = np.unique(np.concatenate([np.arange(1, 4097, dtype=np.uint64), random_xs]))
    target, tolerance = official.reference_values(spec, xs)
    error, matrix = response(lines, indices, xs, target, step, step_units)
    errors = [error]
    matrices = [matrix]
    iterations = []

    for iteration in range(args.max_iterations):
        result = solve(errors, matrices, tolerance, args.bound)
        new_lines = adjusted(lines, indices, result.x[:-1], step)
        candidate = km.Circuit("\n".join(new_lines))
        new_theta, new_error = simulate(candidate, xs, target)
        used = np.abs(new_error).view(np.uint64)
        training_margin = min(int(tolerance[i]) - int(used[i]) for i in range(len(xs)))
        tightest = tightest_full_domain(candidate, spec, args.add_per_iteration, args.batch_size)
        full_margin = tightest[0]["margin"]
        summary = {
            "iteration": iteration,
            "training_inputs": len(xs),
            "lp_min_margin": float(result.x[-1] * (1 << 32)),
            "training_min_margin": training_margin,
            "full_min_margin": full_margin,
            "full_worst_x": tightest[0]["x"],
        }
        iterations.append(summary)
        print(json.dumps(summary), flush=True)
        if full_margin >= training_margin - 16:
            break
        known = set(map(int, xs))
        additions = np.asarray([row["x"] for row in tightest if row["x"] not in known], dtype=np.uint64)
        if not len(additions):
            raise RuntimeError("Full-domain mismatch without new cutting-plane inputs")
        new_target, new_tolerance = official.reference_values(spec, additions)
        new_error, new_matrix = response(lines, indices, additions, new_target, step, step_units)
        xs = np.concatenate([xs, additions])
        target = np.concatenate([target, new_target])
        tolerance = np.concatenate([tolerance, new_tolerance])
        errors.append(new_error)
        matrices.append(new_matrix)
    else:
        raise RuntimeError("Cutting-plane optimization did not converge")

    assert candidate.num_qubits == original.num_qubits == 63
    assert candidate.operation_statistics().num_toffoli_like == original.operation_statistics().num_toffoli_like
    args.output.parent.mkdir(parents=True, exist_ok=True)
    candidate.to_file(args.output, format="kmb")
    report = {
        "status": "converged",
        "rotations": len(indices),
        "zero_lines": sorted(zero_lines),
        "step_power": 40,
        "bound": args.bound,
        "iterations": iterations,
        "final_min_margin": iterations[-1]["full_min_margin"],
        "final_tightest": tightest,
        "adjustments": dict(zip(map(str, indices), result.x[:-1].tolist())),
        "toffoli_like": candidate.operation_statistics().num_toffoli_like,
        "qubits": candidate.num_qubits,
    }
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "final_min_margin": report["final_min_margin"], "iterations": len(iterations)}, indent=2))


if __name__ == "__main__":
    main()
