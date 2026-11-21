"""Piecewise-linear QROM seed followed by the official Newton refinement.

Inspired by Gu et al., arXiv:2610.22367, Sec. III.2 of the supplement.
Unlike that paper's absolute-error target, we retain Newton refinement for the
competition's 2**-24 relative accuracy. Official files are imported, not edited.
"""

import argparse
import dataclasses
import json
import math
import sys
from pathlib import Path

import kickmix as km
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data/official/verifiers"))
from invsqrt import nr_reference_circuit as ref

DEFAULT_PRECISION = ref.Precision()


def coefficient_table(address_bits=6, coef_bits=17, slope_bits=17):
    """Secant lines shifted down by half their maximum interpolation error.

    Address is floor(M * 2**address_bits), for normalized M in [1,4).
    Values below M=1 are unused and filled with zero. The extremum of the
    secant error is where f'(M) equals the secant slope.
    """
    table = np.zeros((1 << (address_bits + 2), 2), dtype=np.int64)
    h = 2.0**-address_bits
    for i in range(1 << address_bits, len(table)):
        a = i * h
        slope = (1 / math.sqrt(a) - 1 / math.sqrt(a + h)) / h
        critical = (0.5 / slope) ** (2 / 3)
        err = 1 / math.sqrt(a) - slope * (critical - a) - 1 / math.sqrt(critical)
        table[i] = np.rint(np.array([1 / math.sqrt(a) - err / 2, slope]) * 2**coef_bits)
        # NOTE: If slope_bits differs, we would adjust the slope here, but for slope17 it's same as before.
        # Validate ranges: slope fits in slope_bits, y0 fits in coef_bits
        assert table[i,0] >=0 and table[i,0] < 2**coef_bits
        assert table[i,1] >=0 and table[i,1] < 2**slope_bits
    # At M=1, truncation in Newton's products can otherwise round above 2,
    # overflowing its one-integer-bit result. A small downward seed bias
    # prevents that while Newton squares away the seed error.
    table[1 << address_bits, 0] = min(
        table[1 << address_bits, 0], round(0.99994 * 2**coef_bits)
    )
    assert np.all((table >= 0) & (table < 2**coef_bits))
    return table


def xor_lookup(builder, address, outputs, table):
    """Unary-iteration XOR QROM, valid for arbitrary output-register states.

    Temporary ANDs are erased with HMR and the matching conditional CZ,
    following Gidney, arXiv:1709.06648. All lookup workspace is returned clean.
    """
    bits = list(reversed(address))
    ancillas = builder.alloc_qubits(len(bits) - 1)

    def node(control, level, lo, hi):
        if np.all(table[lo:hi] == table[lo]):
            for reg, value in zip(outputs, table[lo]):
                builder.gf2_iadd(int(value), target=reg, control=control)
            return
        mid = (lo + hi) // 2
        bit, anc = bits[level], ancillas[level - 1]
        builder.x(bit)
        builder.init_and(control, bit, anc)
        builder.x(bit)
        node(anc, level + 1, lo, mid)
        builder.cx(control, anc)
        node(anc, level + 1, mid, hi)
        builder.del_and(control, bit, anc)

    half = len(table) // 2
    builder.x(bits[0])
    node(bits[0], 1, 0, half)
    builder.x(bits[0])
    node(bits[0], 1, half, 2 * half)
    builder.free(ancillas)


def build_circuit(prec=DEFAULT_PRECISION, address_bits=6, n_p=10, slope_bits=17):
    b = km.CircuitBuilder()
    x = b.create_quantum_register(2 * n_p + 2, "x")
    flags = b.alloc_qubits(n_p)
    y0 = b.alloc_qubits(prec.coef_bits)
    slope = b.alloc_qubits(slope_bits)  # Use slope_bits instead of coef_bits here
    square = b.alloc_qubits(prec.square_bits)
    z = b.alloc_qubits(prec.product_bits + 2)
    y1 = b.alloc_qubits(prec.output_bits(n_p))
    scratch = b.alloc_qubits(
        max(prec.square_bits, prec.product_bits + 2, prec.result_bits + 1)
    )
    table = coefficient_table(address_bits, prec.coef_bits, slope_bits)
    address = x[len(x) - 2 - address_bits :]

    def seed(inverse):
        if not inverse:
            xor_lookup(b, address, [y0, slope], table)
        # Use slope_bits instead of coef_bits in the loop range
        for m in range(
            address_bits + 1, min(prec.delta_bits, len(x) - 2, slope_bits - 1) + 1
        ):
            terms = [(slope[i], i - m) for i in range(m, slope_bits)]  # Use slope_bits here
            ref._add_row(
                b, inverse, x[len(x) - 2 - m], terms, y0, scratch, subtract=True
            )
        if inverse:
            xor_lookup(b, address, [y0, slope], table)

    ref._normalize(b, False, x, flags)
    seed(False)
    ref._square(b, False, y0, square, scratch)
    ref._multiply_m(b, False, x, square, z, scratch)
    ref._correct(b, False, z)
    ref._multiply_y0(b, False, y0, z, y1[: len(y1) - len(flags)], scratch)
    ref._denormalize(b, False, flags, y1)
    ref._phase_by_bits(b, y1)
    ref._denormalize(b, True, flags, y1)
    ref._multiply_y0(b, True, y0, z, y1[: len(y1) - len(flags)], scratch)
    ref._correct(b, True, z)
    ref._multiply_m(b, True, x, square, z, scratch)
    ref._square(b, True, y0, square, scratch)
    seed(True)
    ref._normalize(b, True, x, flags)
    for reg in (flags, y0, slope, square, z, y1, scratch):
        b.free(reg)
    return b.finish_circuit()


def fixed_point_model(xs, prec=DEFAULT_PRECISION, address_bits=6, n_p=10, slope_bits=17):
    """Integer model of every truncated partial product, including the seed."""
    xs = np.asarray(xs, dtype=np.int64)
    width = 2 * n_p + 2
    if not np.all((xs >= 1) & (xs < 2**width)):
        raise ValueError("Input outside positive input-register domain")
    s = (width - (np.floor(np.log2(xs)).astype(np.int64) + 1)) // 2
    xn = xs << (2 * s)
    wc, wsq, wz, wp = (
        prec.coef_bits,
        prec.square_bits,
        prec.product_bits,
        prec.result_bits,
    )
    table = coefficient_table(address_bits, wc, slope_bits)
    rows = table[xn >> (width - 2 - address_bits)]
    y0, slope = rows[:, 0].copy(), rows[:, 1]
    # Use slope_bits here instead of wc (coef_bits)
    for m in range(address_bits + 1, min(prec.delta_bits, width - 2, slope_bits - 1) + 1):
        y0 -= ((xn >> (width - 2 - m)) & 1) * (slope >> m)
    assert np.all((y0 > 0) & (y0 < 2**wc))
    y = {k: (y0 >> (wc - k)) & 1 for k in range(1, wc + 1)}
    square = np.zeros_like(xs)
    for k in range(1, wc + 1):
        if 2 * k <= wsq:
            square += y[k] << (wsq - 2 * k)
        for l in range(k + 1, wc + 1):
            if k + l - 1 <= wsq:
                square += (y[k] & y[l]) << (wsq - k - l + 1)
    assert np.all(square < 2**wsq)
    z = np.zeros_like(xs)
    for i in range(width):
        e = wz - wsq + i - width + 2
        z += ((xn >> i) & 1) * (square << e if e >= 0 else square >> -e)
    assert np.all(z < 2 ** (wz + 2))
    correction = (3 << wz) - z
    assert np.all(correction >= 0)
    p = np.zeros_like(xs)
    for k in range(1, wc + 1):
        e = wp - wz - k
        p += y[k] * (correction << e if e >= 0 else correction >> -e)
    assert np.all(p < 2 ** (wp + 1))
    return p << s


def check_domain(prec, address_bits, max_x=3 * (2**10 - 2) ** 2, slope_bits=17):
    worst_error, worst_x = 0.0, 0
    for lo in range(1, max_x + 1, 65536):
        xs = np.arange(lo, min(lo + 65536, max_x + 1), dtype=np.int64)
        approx = fixed_point_model(xs, prec, address_bits, slope_bits=slope_bits) / 2.0 ** prec.output_bits(10)
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
    parser.add_argument("--address-bits", type=int, default=6)
    parser.add_argument("--slope-bits", type=int, default=17)  # Add slope_bits CLI param
    for field in dataclasses.fields(ref.Precision):
        parser.add_argument(
            "--" + field.name.replace("_", "-"), type=int, default=field.default
        )
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    prec = ref.Precision(
        **{f.name: getattr(args, f.name) for f in dataclasses.fields(ref.Precision)}
    )
    report = check_domain(prec, args.address_bits, slope_bits=args.slope_bits)  # Pass slope_bits
    print(json.dumps(report), flush=True)
    if report["error_over_tolerance"] >= 1:
        raise ValueError("Classical model exceeds tolerance")
    circuit = build_circuit(prec, args.address_bits, slope_bits=args.slope_bits)  # Pass slope_bits
    args.output.parent.mkdir(parents=True, exist_ok=True)
    circuit.to_file(args.output, format="kmb")
    report.update(
        precision=dataclasses.asdict(prec),
        address_bits=args.address_bits,
        slope_bits=args.slope_bits,
        qubits=circuit.num_qubits,
        toffolis=int(circuit.operation_statistics().num_toffoli_like),
    )
    args.output.with_suffix(".model.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
