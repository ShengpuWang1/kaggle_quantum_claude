"""Check the new QROM on arbitrary targets and the circuit against its integer model."""

import dataclasses
import sys
from fractions import Fraction
from pathlib import Path

import kickmix as km
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_linear_invsqrt as opt_v1
import build_linear_invsqrt_v2 as opt_v2


def bits(values, width):
    return (
        (np.asarray(values, dtype=np.int64)[None, :] >> np.arange(width)[:, None]) & 1
    ).astype(bool)


def integers(values):
    return np.sum(values.astype(np.int64) << np.arange(len(values))[:, None], axis=0)


def test_slope16_table_bounds():
    """Verify that slope16 has slopes < 2^16 and table entries are within bounds."""
    address_bits = 5
    slope_bits = 16
    coef_bits = 17
    table = opt_v2.coefficient_table(address_bits, coef_bits, slope_bits)
    # All slopes should be < 2^slope_bits = 2^16 = 65536
    assert np.all((table[:,1] >=0) & (table[:,1] < 2**slope_bits))
    # All y0 (intercepts) should be < 2^coef_bits
    assert np.all((table[:,0] >=0) & (table[:,0] < 2**coef_bits))
    # For slope16, the maximum slope should be less than 2^16
    assert table[:,1].max() < 2**16


def test_v1_v2_model_equality():
    """Verify that v1 and v2 models produce identical results for slope17 and matching configs."""
    address_bits = 6
    slope_bits = 17  # Same as v1's coef_bits, so should be identical
    prec = dataclasses.replace(opt_v1.ref.Precision(), delta_bits=14, square_bits=28, product_bits=28, result_bits=29)
    # Test on same samples as original test
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
            rng.integers(1, 3133453, size=512),
        ]
    )
    xs = xs[(xs > 0) & (xs < 2**22)]
    xs = np.resize(xs, ((len(xs) + 63) // 64) * 64)

    # Compute model outputs from v1 and v2
    model_v1 = opt_v1.fixed_point_model(xs, prec, address_bits)
    model_v2 = opt_v2.fixed_point_model(xs, prec, address_bits, slope_bits=slope_bits)

    # They should be identical when slope_bits=17 (matches v1's coef_bits)
    assert np.array_equal(model_v1, model_v2)


def test_circuit_model_agreement_safe_config():
    """Test safe config: address=5, delta=12, slope=16, square=28, product=27, result=28, plus worst x281726."""
    address_bits =5
    delta_bits =12
    slope_bits=16
    square_bits=28
    product_bits=27
    result_bits=28

    # Create precision matching the safe config
    prec = dataclasses.replace(
        opt_v1.ref.Precision(),
        delta_bits=delta_bits,
        square_bits=square_bits,
        product_bits=product_bits,
        result_bits=result_bits
    )

    # Build v2 circuit
    c = opt_v2.build_circuit(prec, address_bits, slope_bits=slope_bits)
    rng = np.random.default_rng(445)

    # Test cases: small, powers, boundaries, worst x281726, random
    test_xs = np.concatenate([
        np.arange(1, 65),
        2 ** np.arange(20),
        # Boundaries around address intervals
        np.array([(1<<address_bits)-2, (1<<address_bits)-1, 1<<address_bits, (1<<address_bits)+1, (1<<address_bits)+2]),
        np.array([2*(1<<address_bits)-2, 2*(1<<address_bits)-1, 2*(1<<address_bits), 2*(1<<address_bits)+1, 2*(1<<address_bits)+2]),
        np.array([281726]),  # Worst case x from the task
        rng.integers(1, 1000000, size=256),
    ])
    test_xs = test_xs[(test_xs >0) & (test_xs < 2**20)]
    test_xs = np.resize(test_xs, ((len(test_xs)+63)//64)*64)

    # Simulate circuit
    sim = km.Simulator(batch_size=len(test_xs), seed=128)
    x = c.register_data["x"]
    sim.write_across_shots(x, bits(test_xs, 2*10 +2))  # n_p=10 gives 2*10+2=22 bits

    # Run circuit and check input restoration
    sim.do(c)
    assert np.array_equal(integers(sim.read_across_shots(x)), test_xs)
    # Check scratch is clean
    assert not sim.read_across_shots(
        km.array([km.q(i) for i in range(22, c.num_qubits)])
    ).any()

    # Compare with model
    expected = opt_v2.fixed_point_model(test_xs, prec, address_bits, slope_bits=slope_bits)
    for i, value in enumerate(expected):
        assert (
            sim.read_shot_phase(i)
            == Fraction(2 * int(value), 2 ** prec.output_bits(10)) % 2
        )


def test_safe_config_worst_x():
    """Specific test for the worst x281726."""
    address_bits=5
    delta_bits=12
    slope_bits=16
    square_bits=28
    product_bits=27
    result_bits=28
    x_val=281726

    prec = dataclasses.replace(
        opt_v1.ref.Precision(),
        delta_bits=delta_bits,
        square_bits=square_bits,
        product_bits=product_bits,
        result_bits=result_bits
    )

    # Compute model value
    model_val = opt_v2.fixed_point_model(np.array([x_val]), prec, address_bits, slope_bits=slope_bits)[0]

    # Build small circuit and check
    c = opt_v2.build_circuit(prec, address_bits, slope_bits=slope_bits)
    sim = km.Simulator(batch_size=1, seed=42)
    x = c.register_data["x"]
    # Write single x: bits returns (22,1) array, transpose is (1,22), so write_across_shots takes (22,1)
    sim.write_across_shots(x, bits(np.array([x_val]), 22))
    sim.do(c)
    # Check phase matches (single shot, so index 0)
    expected_phase = Fraction(2 * int(model_val), 2 ** prec.output_bits(10)) % 2
    assert sim.read_shot_phase(0) == expected_phase
