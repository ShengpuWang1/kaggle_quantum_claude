"""Focused tests for exact public-lookup analysis and synthesis primitives."""

import hashlib
import sys
import zipfile
from pathlib import Path

import pytest
from pysat.solvers import Solver

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import materialize_public_baseline as materializer
from analyze_public_invsqrt import MASK, AffineBasis, address_table
from optimize_public_invsqrt_lookup import BlockSynthesis, Cnf


def test_materialize_checks_hashes_and_maps_chemistry_names(tmp_path, monkeypatch):
    payloads = {"invsqrt.kmb": b"invsqrt", "dfthcsos__submission.npz": b"chemistry"}
    expected = {
        name: hashlib.sha256(payloads[materializer.archive_name(name)]).hexdigest()
        for name in ("invsqrt.kmb", "dfthcsos/submission.npz")
    }
    monkeypatch.setattr(materializer, "EXPECTED", expected)
    archive = tmp_path / "public.zip"
    with zipfile.ZipFile(archive, "w") as output:
        for name, payload in payloads.items():
            output.writestr(name, payload)

    destination = tmp_path / "candidate"
    records = materializer.materialize(archive, destination)
    assert (destination / "invsqrt.kmb").read_bytes() == b"invsqrt"
    assert (destination / "dfthcsos/submission.npz").read_bytes() == b"chemistry"
    assert records["invsqrt.kmb"] == {"bytes": 7, "sha256": expected["invsqrt.kmb"]}


def test_materialize_hash_failure_leaves_no_output(tmp_path, monkeypatch):
    monkeypatch.setattr(materializer, "EXPECTED", {"invsqrt.kmb": "00" * 32})
    archive = tmp_path / "public.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("invsqrt.kmb", b"corrupt")
    destination = tmp_path / "candidate"

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        materializer.materialize(archive, destination)
    assert not destination.exists()
    assert list(tmp_path.iterdir()) == [archive]


def test_materialize_refuses_to_overwrite(tmp_path):
    destination = tmp_path / "candidate"
    destination.mkdir()
    sentinel = destination / "keep"
    sentinel.write_text("unchanged")
    with pytest.raises(FileExistsError):
        materializer.materialize(tmp_path / "unused.zip", destination)
    assert sentinel.read_text() == "unchanged"


@pytest.mark.parametrize("left", range(4))
@pytest.mark.parametrize("right", range(4))
def test_cnf_lexicographic_constraint(left, right):
    cnf = Cnf()
    a = [cnf.variable(), cnf.variable()]
    b = [cnf.variable(), cnf.variable()]
    cnf.lex_leq(a, b)
    assumptions = [
        variable if value else -variable
        for variables, number in ((a, left), (b, right))
        for variable, value in zip(variables, (number & 1, number >> 1))
    ]
    with Solver(name="cadical195", bootstrap_with=cnf.clauses) as solver:
        assert solver.solve(assumptions=assumptions) == (left <= right)


def test_affine_basis_expression_and_wire_mask():
    basis = AffineBasis()
    basis.add(MASK)
    basis.add(address_table(0), 14)
    basis.add(address_table(1), 22)
    expression = basis.express(MASK ^ address_table(0) ^ address_table(1))
    assert expression == 0b111
    assert basis.wire_mask(expression) == (1, (1 << 0) | (1 << 8))
    with pytest.raises(ValueError, match="outside the affine span"):
        basis.express(address_table(2))


def test_product_normalization_preserves_truth_table_and_rejects_defect():
    synthesis = BlockSynthesis.__new__(BlockSynthesis)
    synthesis.tables = [MASK, address_table(0), address_table(1)]
    x, y = 0b10, 0b100
    synthesis.existing_products = [(x | 1, y), (x, y | 1)]
    synthesis.existing_linear = x
    synthesis.target = synthesis.evaluate(x, synthesis.tables)
    for a, b in synthesis.existing_products:
        synthesis.target ^= synthesis.evaluate(a, synthesis.tables) & synthesis.evaluate(
            b, synthesis.tables
        )

    products, linear = synthesis.normalized_existing()
    synthesis.verify(products, linear)
    with pytest.raises(AssertionError):
        synthesis.verify(products, linear ^ y)
