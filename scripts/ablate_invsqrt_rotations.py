"""Measure the exact full-domain cost effect of removing each invsqrt rotation."""

import argparse
from fractions import Fraction
import json
import math
import sys
from pathlib import Path

import kickmix as km
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from optimize_invsqrt_rotations import simulate, official
from optimize_invsqrt_rotations_cutting import rotation_indices


def full_margin(circuit, spec, target, tolerance, batch_size):
    best_margin = 1 << 64
    worst_x = 0
    all_xs = np.arange(1, spec.max_x + 1, dtype=np.uint64)
    for start in range(0, len(all_xs), batch_size):
        xs = all_xs[start:start + batch_size]
        _, error = simulate(circuit, xs, target[start:start + batch_size])
        used = np.abs(error).view(np.uint64)
        margins = tolerance[start:start + batch_size].astype(np.int64) - used.astype(np.int64)
        index = int(np.argmin(margins))
        if int(margins[index]) < best_margin:
            best_margin = int(margins[index])
            worst_x = int(xs[index])
    return best_margin, worst_x


def estimated_score(min_margin, rotations):
    if min_margin <= 0:
        return None
    eps = math.pi * min_margin / 2**64 / rotations
    t_count = 1 + rotations * official.rotation_t_count(eps)
    return 63 * (1329.5002244928278 + t_count / official.T_PER_TOFFOLI)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("circuit", type=Path)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)

    original = km.Circuit.from_file(args.circuit, format="kmb")
    lines = str(original).splitlines()
    indices = rotation_indices(original)
    spec = official.ProblemSpecInvSqrt.for_n_p(10, shots_per_x=1)
    all_xs = np.arange(1, spec.max_x + 1, dtype=np.uint64)
    target, tolerance = official.reference_values(spec, all_xs)
    results = []
    best = None
    for number, index in enumerate(indices, 1):
        changed = lines.copy()
        operation = changed[index].split()
        operation[2] = "0.0"
        changed[index] = " ".join(operation)
        candidate = km.Circuit("\n".join(changed))
        margin, worst_x = full_margin(candidate, spec, target, tolerance, args.batch_size)
        rotations = sum(
            official.z_pow_class(Fraction(line.split()[2])) == "rotation"
            for line in changed if line.startswith("Z_POW ")
        )
        score = estimated_score(margin, rotations)
        row = {
            "line": index,
            "old_angle": lines[index].split()[2],
            "rotations": rotations,
            "min_margin": margin,
            "worst_x": worst_x,
            "estimated_score": score,
        }
        results.append(row)
        print(json.dumps({"rotation": number, "total": len(indices), **row}), flush=True)
        if score is not None and (best is None or score < best[0]):
            best = score, candidate, row

    report = {"baseline_estimated_score": estimated_score(58597850, 41), "ablations": results}
    if best is not None and best[0] < report["baseline_estimated_score"]:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        best[1].to_file(args.output, format="kmb")
        report["best"] = best[2]
        report["output"] = str(args.output)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"best": report.get("best"), "baseline": report["baseline_estimated_score"]}, indent=2))


if __name__ == "__main__":
    main()
