"""Center invsqrt phase errors by continuously tuning existing rotation angles."""

import argparse
from decimal import Decimal, localcontext
from fractions import Fraction
import json
import sys
from pathlib import Path

import kickmix as km
import numpy as np
from scipy.optimize import linprog

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data/official/verifiers/invsqrt"))
import verify_submission_invsqrt as official

MASK64 = (1 << 64) - 1


def decimal(value):
    with localcontext() as context:
        context.prec = 100
        return format(Decimal(value.numerator) / Decimal(value.denominator), "f")


def simulate(circuit, xs, target):
    simulator = km.Simulator(batch_size=len(xs), seed=913)
    simulator.write_across_shots(km.array([km.q(i) for i in range(22)]), official.to_bits(xs, 22))
    simulator.do(circuit)
    theta = np.asarray([
        official.half_turns_to_units(simulator.read_shot_phase(i)) for i in range(len(xs))
    ], dtype=np.uint64)
    return theta, (theta - target).view(np.int64)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("circuit", type=Path)
    parser.add_argument("--max-x", type=int, default=4096)
    parser.add_argument("--random-full", type=int, default=0, help="Add this many deterministic random full-domain inputs")
    parser.add_argument("--step-power", type=int, default=40)
    parser.add_argument("--bound", type=float, default=1024, help="Adjustment bound in step units; 0 means unbounded")
    parser.add_argument("--objective", choices=("ratio", "margin"), default="ratio")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    circuit = km.Circuit.from_file(args.circuit, format="kmb")
    lines = str(circuit).splitlines()
    indices = [
        index for index, line in enumerate(lines)
        if line.startswith("Z_POW ") and official.z_pow_class(Fraction(line.split()[2])) == "rotation"
    ]
    xs = np.arange(1, args.max_x + 1, dtype=np.uint64)
    spec = official.ProblemSpecInvSqrt.for_n_p(10, shots_per_x=1)
    if args.random_full:
        generator = np.random.default_rng(81723)
        random_xs = generator.integers(1, spec.max_x + 1, size=args.random_full, dtype=np.uint64)
        xs = np.unique(np.concatenate([xs, random_xs]))
    target, tolerance = official.reference_values(spec, xs)
    theta, error = simulate(circuit, xs, target)
    step = Fraction(1, 1 << args.step_power)
    step_units = 1 << (63 - args.step_power)
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
        print(f"rotation {column + 1}/{len(indices)} at line {index}", flush=True)
    count = len(indices)
    objective = np.zeros(count + 1)
    if args.objective == "ratio":
        scaled = matrix.astype(float) * (step_units / tolerance.astype(float))[:, None]
        normalized_error = error.astype(float) / tolerance.astype(float)
        objective[-1] = 1
        upper = np.concatenate([
            np.column_stack([scaled, -np.ones(len(xs))]),
            np.column_stack([-scaled, -np.ones(len(xs))]),
        ])
        bound = np.concatenate([-normalized_error, normalized_error])
    else:
        scale = float(1 << 32)
        scaled = matrix.astype(float) * (step_units / scale)
        normalized_error = error.astype(float) / scale
        normalized_tolerance = tolerance.astype(float) / scale
        objective[-1] = -1
        upper = np.concatenate([
            np.column_stack([scaled, np.ones(len(xs))]),
            np.column_stack([-scaled, np.ones(len(xs))]),
        ])
        bound = np.concatenate([
            normalized_tolerance - normalized_error,
            normalized_tolerance + normalized_error,
        ])
    result = linprog(
        objective,
        A_ub=upper,
        b_ub=bound,
        bounds=[((-args.bound, args.bound) if args.bound else (None, None))] * count + [(0, None)],
        method="highs",
    )
    if not result.success:
        raise RuntimeError(result.message)
    adjustments = result.x[:count]
    new_lines = lines.copy()
    for index, adjustment in zip(indices, adjustments):
        operation = new_lines[index].split()
        operation[2] = decimal(Fraction(operation[2]) + Fraction(str(float(adjustment))) * step)
        new_lines[index] = " ".join(operation)
    candidate = km.Circuit("\n".join(new_lines))
    new_theta, new_error = simulate(candidate, xs, target)
    used = np.abs(new_error).view(np.uint64)
    ratios = np.divide(used, tolerance, out=np.zeros(len(xs), dtype=float), where=tolerance > 0)
    order = np.argsort(ratios)[::-1][:20]
    worst = [
        {"x": int(xs[i]), "error": int(new_error[i]), "tolerance": int(tolerance[i]), "ratio": float(ratios[i])}
        for i in order
    ]
    old_used = np.abs(error).view(np.uint64)
    old_ratios = np.divide(old_used, tolerance, out=np.zeros(len(xs), dtype=float), where=tolerance > 0)
    report = {
        "max_x": args.max_x,
        "random_full": args.random_full,
        "training_inputs": len(xs),
        "rotations": len(indices),
        "step_power": args.step_power,
        "bound": args.bound,
        "objective": args.objective,
        "lp_status": result.message,
        "lp_worst_ratio": float(result.x[-1]) if args.objective == "ratio" else None,
        "lp_min_margin": float(result.x[-1] * (1 << 32)) if args.objective == "margin" else None,
        "old_worst_ratio": float(old_ratios.max()),
        "new_worst_ratio": float(ratios.max()),
        "new_min_margin": min(int(tolerance[i]) - int(used[i]) for i in range(len(xs))),
        "adjustments": dict(zip(map(str, indices), adjustments.tolist())),
        "worst": worst,
        "toffoli_like": candidate.operation_statistics().num_toffoli_like,
        "qubits": candidate.num_qubits,
    }
    assert candidate.num_qubits == circuit.num_qubits == 63
    assert candidate.operation_statistics().num_toffoli_like == circuit.operation_statistics().num_toffoli_like
    args.output.parent.mkdir(parents=True, exist_ok=True)
    candidate.to_file(args.output, format="kmb")
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
