"""Check the new QROM on arbitrary targets and the circuit against its integer model."""

import dataclasses
import sys
from fractions import Fraction
from pathlib import Path

import kickmix as km
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_linear_invsqrt as opt


def bits(values, width):
    return (
        (np.asarray(values, dtype=np.int64)[None, :] >> np.arange(width)[:, None]) & 1
    ).astype(bool)


def integers(values):
    return np.sum(values.astype(np.int64) << np.arange(len(values))[:, None], axis=0)


@pytest.mark.parametrize("seed", [13, 927])
def test_qrom_arbitrary_targets_and_clean_phase(seed):
    rng = np.random.default_rng(seed)
    table = opt.coefficient_table()
    b = km.CircuitBuilder()
    addr = b.create_quantum_register(8, "address")
    outputs = [b.create_quantum_register(17, "a"), b.create_quantum_register(17, "b")]
    opt.xor_lookup(b, addr, outputs, table)
    c = b.finish_circuit()
    scratch = km.array([km.q(i) for i in range(42, c.num_qubits)])
    # Include invalid/unused addresses too: the QROM is a total XOR oracle.
    addresses = np.repeat(np.arange(256), 4)
    incoming = rng.integers(0, 2**17, size=(2, len(addresses)))
    sim = km.Simulator(batch_size=len(addresses), seed=seed)
    sim.write_across_shots(addr, bits(addresses, 8))
    for reg, values in zip(outputs, incoming):
        sim.write_across_shots(reg, bits(values, 17))
    for step in range(2):
        sim.do(c)
        assert np.array_equal(integers(sim.read_across_shots(addr)), addresses)
        assert not sim.read_across_shots(scratch).any()
        assert not sim.read_phase_flipped_across_shots().any()
        for j, reg in enumerate(outputs):
            expected = incoming[j] ^ table[addresses, j] if step == 0 else incoming[j]
            assert np.array_equal(integers(sim.read_across_shots(reg)), expected)


@pytest.mark.parametrize(
    "address_bits,delta_bits,result_bits",
    [(5, 12, 29), (5, 14, 29), (6, 14, 29), (5, 13, 28)],
)
def test_full_circuit_matches_integer_model(address_bits, delta_bits, result_bits):
    prec = dataclasses.replace(
        opt.ref.Precision(), delta_bits=delta_bits, result_bits=result_bits
    )
    c = opt.build_circuit(prec, address_bits)
    rng = np.random.default_rng(445)
    # Powers of two, interval transitions, smallest values and random domain points.
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
            rng.integers(1, 3133453, size=512),
        ]
    )
    xs = xs[(xs > 0) & (xs < 2**22)]
    xs = np.resize(xs, ((len(xs) + 63) // 64) * 64)
    sim = km.Simulator(batch_size=len(xs), seed=128)
    x = c.register_data["x"]
    sim.write_across_shots(x, bits(xs, 22))
    sim.do(c)
    assert np.array_equal(integers(sim.read_across_shots(x)), xs)
    assert not sim.read_across_shots(
        km.array([km.q(i) for i in range(22, c.num_qubits)])
    ).any()
    expected = opt.fixed_point_model(xs, prec, address_bits)
    for i, value in enumerate(expected):
        assert (
            sim.read_shot_phase(i)
            == Fraction(2 * int(value), 2 ** prec.output_bits(10)) % 2
        )
