"""Compare exhaustive error and circuit resources for direct quadratic configurations."""

import argparse
import dataclasses
import json
from pathlib import Path

import build_quadratic_invsqrt as quad


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    results = []
    for address_bits in (6, 7, 8):
        for coef_bits in (27, 28, 29):
            for result_bits in (27, 28, 29):
                prec = quad.QuadraticPrecision(
                    coef_bits=coef_bits, result_bits=result_bits
                )
                record = {
                    "address_bits": address_bits,
                    "precision": dataclasses.asdict(prec),
                }
                try:
                    table = quad.coefficient_table(address_bits, prec)
                    record.update(quad.check_domain(prec, address_bits, table))
                    if record["error_over_tolerance"] < 1:
                        circuit = quad.build_circuit(prec, address_bits, table=table)
                        stats = circuit.operation_statistics()
                        record.update(
                            qubits=circuit.num_qubits,
                            toffolis=int(stats.num_toffoli_like),
                            generic_rotations=int(
                                stats.num_z_pow(min_clifford_hierarchy_level=4)
                            ),
                        )
                        record["qubit_toffoli_product"] = (
                            record["qubits"] * record["toffolis"]
                        )
                except (AssertionError, ValueError) as exc:
                    record["error"] = str(exc)
                results.append(record)
                print(json.dumps(record), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
