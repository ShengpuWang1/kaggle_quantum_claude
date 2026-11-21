"""Share an existing invsqrt product, then synthesize the other residual with three ANDs."""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import kickmix as km
from analyze_public_invsqrt import MASK, Lookup
from optimize_public_invsqrt_joint import JointSynthesis
from optimize_public_invsqrt_lookup import BlockSynthesis, simulate_region


def normalized(block, products, linear):
    result = []
    for a, b in products:
        alpha, beta = a & 1, b & 1
        if alpha:
            linear ^= b
        if beta:
            linear ^= a
        if alpha and beta:
            linear ^= 1
        result.append(tuple(sorted((a ^ alpha, b ^ beta))))
    return result, linear


def solve_residual(lookup, block, basis, target, products, linear, conflicts, solver):
    synthesis = BlockSynthesis(
        lookup,
        block,
        3,
        basis=basis,
        target=target,
        existing_products=products,
        existing_linear=linear,
    )
    simple = synthesis.simple_search()
    if simple is not None:
        products, linear = simple
        synthesis.verify(products, linear)
        return {"status": "sat", "products": products, "linear": linear, "method": "simple", "seconds": 0.0}
    return synthesis.solve(conflicts, solver_name=solver)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("circuit", type=Path)
    parser.add_argument("--first-block", type=int, default=32)
    parser.add_argument("--conflicts", type=int, default=200000)
    parser.add_argument("--solver", default="cadical195")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    lookup = Lookup(args.circuit)
    first, second = lookup.blocks[args.first_block:args.first_block + 2]
    joint = JointSynthesis(lookup, first, second)
    first_raw = lookup.block_representation(first)
    second_raw = lookup.block_representation(second)
    first_products, first_linear = normalized(first, first_raw[1], first_raw[2])
    second_products, second_linear = normalized(second, second_raw[1], second_raw[2])
    targets = joint.targets
    attempts = []
    start = time.monotonic()
    result = None

    def attempt(kind, index, shared, residual_side, residual_target, residual_existing, residual_linear):
        nonlocal result
        if result is not None:
            return
        block, basis = (second, joint.bases[1]) if residual_side == "second" else (first, joint.bases[0])
        report = solve_residual(
            lookup, block, basis, residual_target, residual_existing, residual_linear,
            args.conflicts, args.solver,
        )
        report.update(kind=kind, existing_product=index, residual_side=residual_side)
        attempts.append(report)
        print(json.dumps({key: report[key] for key in ("kind", "existing_product", "residual_side", "status", "seconds")}), flush=True)
        if report["status"] != "sat":
            return
        if residual_side == "second":
            products = [shared, *(p for i, p in enumerate(first_products) if i != index), *report["products"]]
            linears = [first_linear, report["linear"]]
        else:
            products = [shared, *report["products"], *(p for i, p in enumerate(second_products) if i != index)]
            linears = [report["linear"], second_linear]
        joint.verify(products, linears)
        result = {"status": "sat", "products": products, "linears": linears}

    for index, shared in enumerate(first_products):
        value = joint.evaluate(shared[0], joint.tables_by_output[0]) & joint.evaluate(shared[1], joint.tables_by_output[0])
        attempt("first", index, shared, "second", targets[1] ^ value, second_raw[1], second_raw[2])

    for index, (a, b) in enumerate(second_products):
        try:
            shared = tuple(
                joint.bases[0].express(joint.evaluate(expression, joint.tables_by_output[1]))
                for expression in (a, b)
            )
        except ValueError:
            attempts.append({"kind": "second", "existing_product": index, "status": "outside_first_basis"})
            continue
        value = joint.evaluate(a, joint.tables_by_output[1]) & joint.evaluate(b, joint.tables_by_output[1])
        attempt("second", index, shared, "first", targets[0] ^ value, first_raw[1], first_raw[2])

    summary = {
        "first_block": args.first_block,
        "second_block": args.first_block + 1,
        "seconds": time.monotonic() - start,
        "attempts": attempts,
    }
    if result is not None:
        lines = joint.emit(result["products"], result["linears"])
        values, phases = simulate_region(lookup.lines)
        new_values, new_phases = simulate_region(lines)
        assert values == new_values and phases == new_phases
        candidate = km.Circuit("\n".join(lines))
        old_stats = lookup.circuit.operation_statistics()
        new_stats = candidate.operation_statistics()
        assert candidate.num_qubits == lookup.circuit.num_qubits == 63
        assert old_stats.num_toffoli_like - new_stats.num_toffoli_like >= 1
        assert new_stats.num_z_pow == old_stats.num_z_pow
        summary.update(
            status="sat", products=result["products"], linears=result["linears"],
            exhaustive_region_equivalence=True,
            old_toffoli_like=old_stats.num_toffoli_like,
            new_toffoli_like=new_stats.num_toffoli_like,
        )
        if args.output:
            if args.output.exists():
                raise FileExistsError(args.output)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            candidate.to_file(args.output, format="kmb")
    else:
        summary["status"] = "unknown" if any(a["status"] == "unknown" for a in attempts) else "unsat"
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({key: value for key, value in summary.items() if key != "attempts"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
