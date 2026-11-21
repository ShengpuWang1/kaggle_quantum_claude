"""Check direct quadratic QROM behavior and exact circuit/model agreement."""

import sys
from fractions import Fraction
from pathlib import Path

import kickmix as km
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_quadratic_invsqrt as quad


def bits(values, width):
    return (
        (np.asarray(values, dtype=np.int64)[None, :] >> np.arange(width)[:, None]) & 1
    ).astype(bool)


def integers(values):
    return np.sum(values.astype(np.int64) << np.arange(len(values))[:, None], axis=0)


def test_coefficient_bounds_and_exhaustive_error():
    prec = quad.QuadraticPrecision()
    table = quad.coefficient_table(7, prec)
    for column, width in enumerate(quad.coefficient_widths(7, prec)):
        assert np.all((table[:, column] >= 0) & (table[:, column] < 2**width))
    assert not table[: 1 << 7].any()
    report = quad.check_domain(prec, 7, table)
    assert report["error_over_tolerance"] < 0.8
    assert report["worst_x"] == 3116927


@pytest.mark.parametrize("seed", [13, 927])
def test_qrom_arbitrary_targets_and_clean_phase(seed):
    rng = np.random.default_rng(seed)
    prec = quad.QuadraticPrecision()
    table = quad.coefficient_table(7, prec)
    widths = quad.coefficient_widths(7, prec)
    b = km.CircuitBuilder()
    address = b.create_quantum_register(9, "address")
    outputs = [b.create_quantum_register(width, f"c{i}") for i, width in enumerate(widths)]
    quad.linear.xor_lookup(b, address, outputs, table)
    circuit = b.finish_circuit()
    first_scratch = len(address) + sum(widths)
    scratch = km.array([km.q(i) for i in range(first_scratch, circuit.num_qubits)])
    addresses = np.repeat(np.arange(512), 2)
    incoming = [rng.integers(0, 2**width, size=len(addresses)) for width in widths]
    sim = km.Simulator(batch_size=len(addresses), seed=seed)
    sim.write_across_shots(address, bits(addresses, len(address)))
    for reg, values, width in zip(outputs, incoming, widths):
        sim.write_across_shots(reg, bits(values, width))
    for step in range(2):
        sim.do(circuit)
        assert np.array_equal(integers(sim.read_across_shots(address)), addresses)
        assert not sim.read_across_shots(scratch).any()
        assert not sim.read_phase_flipped_across_shots().any()
        for j, (reg, width) in enumerate(zip(outputs, widths)):
            expected = incoming[j] ^ table[addresses, j] if step == 0 else incoming[j]
            assert np.array_equal(integers(sim.read_across_shots(reg)), expected)


@pytest.mark.parametrize(
    ("address_bits", "prec"),
    [
        (7, quad.QuadraticPrecision()),
        (6, quad.QuadraticPrecision(coef_bits=27)),
        (7, quad.QuadraticPrecision(coef_bits=27, result_bits=27)),
    ],
    ids=["default", "a6_c27_r28", "a7_c27_r27"],
)
def test_full_circuit_matches_integer_model(address_bits, prec):
    table = quad.coefficient_table(address_bits, prec)
    circuit = quad.build_circuit(prec, address_bits, table=table)
    rng = np.random.default_rng(445)
    endpoints = np.array(
        [
            i * 2 ** (20 - address_bits) + offset
            for i in range(1 << address_bits, 4 << address_bits)
            for offset in [-1, 0, 1]
        ]
    )
    xs = np.concatenate(
        [
            np.arange(1, 65),
            2 ** np.arange(22),
            endpoints,
            [1060815, 2764799, 3116927, 3133452],
            rng.integers(1, 3133453, size=512),
        ]
    )
    xs = xs[(xs > 0) & (xs < 2**22)]
    xs = np.resize(xs, ((len(xs) + 63) // 64) * 64)
    sim = km.Simulator(batch_size=len(xs), seed=128)
    x = circuit.register_data["x"]
    sim.write_across_shots(x, bits(xs, 22))
    sim.do(circuit)
    assert np.array_equal(integers(sim.read_across_shots(x)), xs)
    assert not sim.read_across_shots(
        km.array([km.q(i) for i in range(22, circuit.num_qubits)])
    ).any()
    expected = quad.fixed_point_model(xs, prec, address_bits, table=table)
    for i, value in enumerate(expected):
        assert sim.read_shot_phase(i) == Fraction(
            2 * int(value), 2 ** prec.output_bits(10)
        ) % 2
