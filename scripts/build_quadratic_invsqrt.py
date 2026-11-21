"""Direct piecewise-quadratic inverse square root without Newton refinement.

Uses the in-place Horner form from Gu et al., arXiv:2610.22367, supplement III.1.
The polynomial approximates 2/sqrt(M) so the official denormalization and phase
routines can be reused. Every truncated integer update is modeled exhaustively.
"""

import argparse
import dataclasses
import hashlib
import json
from pathlib import Path

import build_linear_invsqrt as linear
import kickmix as km
import numpy as np

ref = linear.ref


@dataclasses.dataclass(frozen=True)
class QuadraticPrecision:
    delta_bits: int = 20
    coef_bits: int = 28
    result_bits: int = 28

    def output_bits(self, n_p):
        return self.result_bits + n_p + 1


DEFAULT_PRECISION = QuadraticPrecision()


def coefficient_widths(address_bits, prec):
    return (
        prec.result_bits + 1,
        prec.coef_bits - address_bits,
        prec.coef_bits - 2 * address_bits + 1,
    )


def coefficient_table(address_bits=7, prec=DEFAULT_PRECISION):
    """Centered Chebyshev quadratic interpolants in local coordinates."""
    widths = coefficient_widths(address_bits, prec)
    if min(widths) <= 0:
        raise ValueError("Coefficient widths must be positive")
    table = np.zeros((1 << (address_bits + 2), 3), dtype=np.int64)
    h = 2.0**-address_bits
    nodes = (1 + np.cos((2 * np.arange(3) + 1) * np.pi / 6)) / 2
    grid = np.linspace(0, 1, 2001)
    for i in range(1 << address_bits, len(table)):
        a = i * h
        exact_nodes = 2 / np.sqrt(a + h * nodes)
        q0, q1, q2 = np.polynomial.polynomial.polyfit(nodes, exact_nodes, 2)
        residual = q0 + q1 * grid + q2 * grid**2 - 2 / np.sqrt(a + h * grid)
        q0 -= (np.max(residual) + np.min(residual)) / 2
        table[i] = np.rint(
            np.array([q0 * 2**prec.result_bits, -q1 * 2**prec.coef_bits, q2 * 2**prec.coef_bits])
        )
    # p has one integer bit and must stay strictly below two at M=1.
    table[1 << address_bits, 0] = min(
        table[1 << address_bits, 0], (1 << (prec.result_bits + 1)) - 1
    )
    for column, width in enumerate(widths):
        assert np.all((table[:, column] >= 0) & (table[:, column] < 2**width))
    return table


def row_shift(address_bits, prec, m):
    return m - address_bits - prec.result_bits + prec.coef_bits


def build_circuit(prec=DEFAULT_PRECISION, address_bits=7, n_p=10, table=None):
    if table is None:
        table = coefficient_table(address_bits, prec)
    b = km.CircuitBuilder()
    x = b.create_quantum_register(2 * n_p + 2, "x")
    flags = b.alloc_qubits(n_p)
    y1 = b.alloc_qubits(prec.output_bits(n_p))
    _, c1_width, c2_width = coefficient_widths(address_bits, prec)
    c1 = b.alloc_qubits(c1_width)
    c2 = b.alloc_qubits(c2_width)
    p = y1[: len(y1) - len(flags)]
    scratch = b.alloc_qubits(max(len(p), len(c1)))
    address = x[len(x) - 2 - address_bits :]

    def inner_horner(inverse):
        for m in range(address_bits + 1, min(prec.delta_bits, len(x) - 2) + 1):
            shift = m - address_bits
            terms = [(c2[j], j - shift) for j in range(shift, len(c2))]
            if not terms:
                break
            ref._add_row(
                b, inverse, x[len(x) - 2 - m], terms, c1, scratch, subtract=True
            )

    def outer_horner(inverse):
        for m in range(address_bits + 1, min(prec.delta_bits, len(x) - 2) + 1):
            shift = row_shift(address_bits, prec, m)
            terms = [(c1[j], j - shift) for j in range(max(0, shift), len(c1))]
            if not terms:
                break
            ref._add_row(
                b, inverse, x[len(x) - 2 - m], terms, p, scratch, subtract=True
            )

    def polynomial(inverse):
        if inverse:
            outer_horner(True)
            inner_horner(True)
            linear.xor_lookup(b, address, [p, c1, c2], table)
        else:
            linear.xor_lookup(b, address, [p, c1, c2], table)
            inner_horner(False)
            outer_horner(False)

    ref._normalize(b, False, x, flags)
    polynomial(False)
    ref._denormalize(b, False, flags, y1)
    ref._phase_by_bits(b, y1)
    ref._denormalize(b, True, flags, y1)
    polynomial(True)
    ref._normalize(b, True, x, flags)
    for reg in (flags, c1, c2, y1, scratch):
        b.free(reg)
    return b.finish_circuit()


def fixed_point_model(xs, prec=DEFAULT_PRECISION, address_bits=7, n_p=10, table=None):
    """Integer model of the exact truncated in-place Horner computation."""
    if table is None:
        table = coefficient_table(address_bits, prec)
    xs = np.asarray(xs, dtype=np.int64)
    width = 2 * n_p + 2
    if not np.all((xs >= 1) & (xs < 2**width)):
        raise ValueError("Input outside positive input-register domain")
    s = (width - (np.floor(np.log2(xs)).astype(np.int64) + 1)) // 2
    xn = xs << (2 * s)
    rows = table[xn >> (width - 2 - address_bits)]
    p, c1, c2 = rows[:, 0].copy(), rows[:, 1].copy(), rows[:, 2]
    _, c1_width, c2_width = coefficient_widths(address_bits, prec)
    for m in range(address_bits + 1, min(prec.delta_bits, width - 2) + 1):
        shift = m - address_bits
        if shift >= c2_width:
            break
        c1 -= ((xn >> (width - 2 - m)) & 1) * (c2 >> shift)
    assert np.all(c1 >= 0)
    for m in range(address_bits + 1, min(prec.delta_bits, width - 2) + 1):
        shift = row_shift(address_bits, prec, m)
        if shift >= c1_width:
            break
        contribution = c1 << -shift if shift < 0 else c1 >> shift
        p -= ((xn >> (width - 2 - m)) & 1) * contribution
    assert np.all((p > 0) & (p < 2 ** (prec.result_bits + 1)))
    return p << s


def check_domain(prec, address_bits, table, max_x=3 * (2**10 - 2) ** 2):
    worst_error, worst_x = 0.0, 0
    for lo in range(1, max_x + 1, 65536):
        xs = np.arange(lo, min(lo + 65536, max_x + 1), dtype=np.int64)
        approx = fixed_point_model(xs, prec, address_bits, table=table) / 2.0 ** prec.output_bits(10)
        errors = np.abs(approx * np.sqrt(xs) - 1)
        idx = int(np.argmax(errors))
        if errors[idx] > worst_error:
            worst_error, worst_x = float(errors[idx]), int(xs[idx])
    return {
        "max_x": max_x,
        "worst_relative_error": worst_error,
        "worst_x": worst_x,
        "error_over_tolerance": worst_error * 2**24,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--address-bits", type=int, default=7)
    for field in dataclasses.fields(QuadraticPrecision):
        parser.add_argument(
            "--" + field.name.replace("_", "-"), type=int, default=field.default
        )
    args = parser.parse_args()
    prec = QuadraticPrecision(
        **{f.name: getattr(args, f.name) for f in dataclasses.fields(QuadraticPrecision)}
    )
    model_output = args.output.with_suffix(".model.json")
    table_output = args.output.with_suffix(".coefficients.json")
    for path in (args.output, model_output, table_output):
        if path.exists():
            raise FileExistsError(path)
    table = coefficient_table(args.address_bits, prec)
    report = check_domain(prec, args.address_bits, table)
    print(json.dumps(report), flush=True)
    if report["error_over_tolerance"] >= 1:
        raise ValueError("Classical model exceeds tolerance")
    circuit = build_circuit(prec, args.address_bits, table=table)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    circuit.to_file(args.output, format="kmb")
    table_output.write_text(json.dumps({"rows": table.tolist()}, indent=2) + "\n")
    with args.output.open("rb") as stream:
        circuit_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    report.update(
        precision=dataclasses.asdict(prec),
        address_bits=args.address_bits,
        coefficient_widths=coefficient_widths(args.address_bits, prec),
        qubits=circuit.num_qubits,
        toffolis=int(circuit.operation_statistics().num_toffoli_like),
        circuit_sha256=circuit_hash,
    )
    model_output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
