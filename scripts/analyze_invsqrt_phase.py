"""Measure invsqrt phase margins on selected official inputs."""

import argparse
import json
import sys
from pathlib import Path

import kickmix as km
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data/official/verifiers/invsqrt"))
import verify_submission_invsqrt as official


def phase_errors(circuit, xs, seed=913):
    xs = np.asarray(xs, dtype=np.uint64)
    spec = official.ProblemSpecInvSqrt.for_n_p(10, shots_per_x=1)
    target, tolerance = official.reference_values(spec, xs)
    simulator = km.Simulator(batch_size=len(xs), seed=seed)
    simulator.write_across_shots(km.array([km.q(i) for i in range(22)]), official.to_bits(xs, 22))
    simulator.do(circuit)
    theta = np.asarray([
        official.half_turns_to_units(simulator.read_shot_phase(i)) for i in range(len(xs))
    ], dtype=np.uint64)
    error = (theta - target).view(np.int64)
    used = np.abs(error).view(np.uint64)
    ratio = np.divide(used, tolerance, out=np.zeros(len(xs), dtype=float), where=tolerance > 0)
    return error, tolerance, ratio


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("circuit", type=Path)
    parser.add_argument("--max-x", type=int, default=4096)
    parser.add_argument("--random-full", type=int, default=0, help="Add deterministic random full-domain inputs")
    parser.add_argument("--seed", type=int, default=81723)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    circuit = km.Circuit.from_file(args.circuit, format="kmb")
    xs = np.arange(1, args.max_x + 1, dtype=np.uint64)
    spec = official.ProblemSpecInvSqrt.for_n_p(10, shots_per_x=1)
    if args.random_full:
        generator = np.random.default_rng(args.seed)
        random_xs = generator.integers(1, spec.max_x + 1, size=args.random_full, dtype=np.uint64)
        xs = np.unique(np.concatenate([xs, random_xs]))
    error, tolerance, ratio = phase_errors(circuit, xs)
    order = np.argsort(ratio)[::-1][:30]
    rows = [
        {"x": int(xs[i]), "error": int(error[i]), "tolerance": int(tolerance[i]), "ratio": float(ratio[i])}
        for i in order
    ]
    used = np.abs(error).view(np.uint64)
    tight_order = sorted(range(len(xs)), key=lambda i: int(tolerance[i]) - int(used[i]))[:30]
    tightest = [
        {"x": int(xs[i]), "margin": int(tolerance[i]) - int(used[i]), "ratio": float(ratio[i])}
        for i in tight_order
    ]
    result = {
        "max_x": args.max_x,
        "random_full": args.random_full,
        "seed": args.seed,
        "inputs": len(xs),
        "min_margin": tightest[0]["margin"],
        "worst_ratio": float(ratio.max()),
        "worst": rows,
        "tightest": tightest,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key not in {"worst", "tightest"}}, indent=2))


if __name__ == "__main__":
    main()
