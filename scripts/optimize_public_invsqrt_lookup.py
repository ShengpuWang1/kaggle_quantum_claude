"""Use exact SAT synthesis to remove an AND from one public lookup block."""

import argparse
import itertools
import json
import time
from pathlib import Path

import kickmix as km
from analyze_public_invsqrt import (
    ADDRESS,
    MASK,
    POOL,
    REGION_END,
    REGION_START,
    WIRES,
    Lookup,
)
from pysat.solvers import Solver


class Cnf:
    def __init__(self):
        self.clauses = []
        self.variables = 0

    def variable(self):
        self.variables += 1
        return self.variables

    def unit(self, value, expected=True):
        if isinstance(value, bool):
            assert value == expected
        else:
            self.clauses.append([value if expected else -value])

    def xor(self, values):
        constant = False
        variables = []
        for value in values:
            if isinstance(value, bool):
                constant ^= value
            else:
                variables.append(value)
        if not variables:
            return constant
        while len(variables) > 1:
            reduced = []
            for index in range(0, len(variables) - 1, 2):
                left, right = variables[index : index + 2]
                output = self.variable()
                self.clauses.extend(
                    [
                        [-left, -right, -output],
                        [left, right, -output],
                        [left, -right, output],
                        [-left, right, output],
                    ]
                )
                reduced.append(output)
            if len(variables) % 2:
                reduced.append(variables[-1])
            variables = reduced
        result = variables[0]
        if constant:
            output = self.variable()
            self.clauses.extend([[-result, -output], [result, output]])
            result = output
        return result

    def conjunction(self, left, right):
        if isinstance(left, bool):
            return right if left else False
        if isinstance(right, bool):
            return left if right else False
        output = self.variable()
        self.clauses.extend([[-output, left], [-output, right], [output, -left, -right]])
        return output

    def lex_leq(self, left, right):
        """Break control-swapping and product-permutation symmetries."""
        equal = True
        for a, b in reversed(list(zip(left, right))):
            if equal is True:
                self.clauses.append([-a, b])
            else:
                self.clauses.append([-equal, -a, b])
            same = self.variable()
            self.clauses.extend(
                [[-same, -a, b], [-same, a, -b], [same, a, b], [same, -a, -b]]
            )
            equal = same if equal is True else self.conjunction(equal, same)


class BlockSynthesis:
    def __init__(
        self,
        lookup,
        block,
        and_count,
        basis=None,
        target=None,
        existing_products=None,
        existing_linear=None,
        tables=None,
    ):
        self.lookup = lookup
        self.block = block
        self.and_count = and_count
        if basis is None:
            self.basis, self.existing_products, self.existing_linear = (
                lookup.block_representation(block)
            )
            self.target = lookup.states[block.end][block.target]
        else:
            self.basis = basis
            self.existing_products = existing_products or []
            self.existing_linear = existing_linear or 0
            self.target = target
        if tables is None:
            tables = [lookup.states[block.start][wire] for wire in self.basis.wires]
        self.tables = [MASK] + list(tables)
        self.dimension = len(self.tables)
        self.cnf = Cnf()
        self.a_variables = self._form_variables()
        self.b_variables = self._form_variables()
        for variables in [*self.a_variables, *self.b_variables]:
            # (a+1)b = ab+b, so affine constants can always be absorbed into
            # the free linear output. Restrict product controls to linear forms.
            self.cnf.unit(variables[0], False)
        self.linear_variables = self._form_variables(count=1)[0]
        for a, b in zip(self.a_variables, self.b_variables):
            self.cnf.lex_leq(a, b)
        for left, right in zip(self.a_variables, self.a_variables[1:]):
            self.cnf.lex_leq(left, right)
        self._encode()

    def normalized_existing(self):
        products = []
        linear = self.existing_linear
        for a, b in self.existing_products:
            alpha, beta = a & 1, b & 1
            if alpha:
                linear ^= b
            if beta:
                linear ^= a
            if alpha and beta:
                linear ^= 1
            products.append(tuple(sorted((a ^ alpha, b ^ beta))))
        products.sort()
        return products, linear

    def require_nondegenerate(self):
        """Restrict the search to representations using exactly `and_count` products.

        A constant or repeated control makes its product affine. A control shared
        by two products lets those products merge, e.g. ab+ac=a(b+c).
        """
        controls = [*self.a_variables, *self.b_variables]
        for variables in controls:
            self.cnf.clauses.append(variables[1:])
        for left, right in itertools.combinations(controls, 2):
            differences = [self.cnf.xor([a, b]) for a, b in zip(left, right)]
            self.cnf.clauses.append(differences)

    def _form_variables(self, count=None):
        count = self.and_count if count is None else count
        return [
            [self.cnf.variable() for _ in range(self.dimension)]
            for _ in range(count)
        ]

    def _affine_value(self, variables, address):
        return self.cnf.xor(
            variables[bit]
            for bit, table in enumerate(self.tables)
            if (table >> address) & 1
        )

    def _encode(self):
        for address in range(256):
            products = []
            for a_variables, b_variables in zip(self.a_variables, self.b_variables):
                a = self._affine_value(a_variables, address)
                b = self._affine_value(b_variables, address)
                products.append(self.cnf.conjunction(a, b))
            linear = self._affine_value(self.linear_variables, address)
            result = self.cnf.xor([*products, linear])
            self.cnf.unit(result, bool((self.target >> address) & 1))

    def _hints(self, products, linear):
        expressions = []
        for a, b in products:
            expressions.extend([a, b])
        expressions.append(linear)
        variables = []
        for a, b in zip(self.a_variables, self.b_variables):
            variables.extend([a, b])
        variables.append(self.linear_variables)
        hints = []
        for expression, form_variables in zip(expressions, variables):
            for bit, variable in enumerate(form_variables):
                hints.append(variable if (expression >> bit) & 1 else -variable)
        return hints

    def solve(self, conflicts, validate_existing=False, solver_name="cadical195"):
        existing_products, existing_linear = self.normalized_existing()
        products = existing_products[: self.and_count]
        linear = existing_linear
        start = time.monotonic()
        with Solver(name=solver_name, bootstrap_with=self.cnf.clauses) as solver:
            hints = self._hints(products, linear)
            try:
                solver.set_phases(hints)
            except NotImplementedError:
                # Kissat does not expose phase hints through PySAT.
                pass
            if validate_existing:
                result = solver.solve(assumptions=hints)
            elif conflicts:
                solver.conf_budget(conflicts)
                result = solver.solve_limited()
            else:
                result = solver.solve()
            if result is not True:
                return {
                    "status": "unsat" if result is False else "unknown",
                    "seconds": time.monotonic() - start,
                    "variables": self.cnf.variables,
                    "clauses": len(self.cnf.clauses),
                }
            model = set(solver.get_model())
            stats = solver.accum_stats()
        def decode(variables):
            return sum((1 << bit) for bit, variable in enumerate(variables) if variable in model)

        products = [
            (decode(a), decode(b)) for a, b in zip(self.a_variables, self.b_variables)
        ]
        linear = decode(self.linear_variables)
        self.verify(products, linear)
        return {
            "status": "sat",
            "seconds": time.monotonic() - start,
            "variables": self.cnf.variables,
            "clauses": len(self.cnf.clauses),
            "conflicts": stats.get("conflicts"),
            "products": products,
            "linear": linear,
        }

    def product_pool(self, max_form_weight=1):
        forms = [1 << bit for bit in range(1, self.dimension)]
        if max_form_weight >= 2:
            forms.extend(
                (1 << left) | (1 << right)
                for left, right in itertools.combinations(range(1, self.dimension), 2)
            )
        products = {}
        for left_index, left in enumerate(forms):
            left_value = self.evaluate(left, self.tables)
            for right in forms[left_index + 1 :]:
                value = left_value & self.evaluate(right, self.tables)
                residue, _ = self.basis._reduce(value)
                products.setdefault(residue, (value, (left, right)))
        return products

    def neighborhood_search(self):
        """Try three products near any three of the existing four products."""
        existing, _ = self.normalized_existing()
        if len(existing) != 4 or self.and_count != 3:
            return None
        target_residue, _ = self.basis._reduce(self.target)
        deltas = [0] + [1 << bit for bit in range(1, self.dimension)]
        for removed in range(4):
            retained = [product for index, product in enumerate(existing) if index != removed]
            pools = []
            for a, b in retained:
                pool = {}
                a_value = self.evaluate(a, self.tables)
                b_value = self.evaluate(b, self.tables)
                for da in deltas:
                    av = a_value ^ self.evaluate(da, self.tables)
                    for db in deltas:
                        bv = b_value ^ self.evaluate(db, self.tables)
                        value = av & bv
                        residue, _ = self.basis._reduce(value)
                        pool.setdefault(residue, (value, (a ^ da, b ^ db)))
                pools.append(pool)
            first, second, third = pools
            for left_residue, (left_value, left_form) in first.items():
                for right_residue, (right_value, right_form) in second.items():
                    needed = target_residue ^ left_residue ^ right_residue
                    if needed not in third:
                        continue
                    third_value, third_form = third[needed]
                    linear = self.basis.express(
                        self.target ^ left_value ^ right_value ^ third_value
                    )
                    return [left_form, right_form, third_form], linear
        return None

    def simple_search(self, weight_two=False):
        """Meet-in-the-middle search over low-weight linear control forms."""
        products = self.product_pool(2 if weight_two else 1)
        simple_items = list(self.product_pool(1).items()) if weight_two else list(products.items())
        target_residue, _ = self.basis._reduce(self.target)
        for left_residue, (left_value, left_form) in products.items():
            needed = target_residue ^ left_residue
            if needed in products:
                right_value, right_form = products[needed]
                linear = self.basis.express(self.target ^ left_value ^ right_value)
                return [left_form, right_form], linear
        for index, (left_residue, (left_value, left_form)) in enumerate(simple_items):
            for right_residue, (right_value, right_form) in simple_items[index:]:
                needed = target_residue ^ left_residue ^ right_residue
                if needed not in products:
                    continue
                third_value, third_form = products[needed]
                linear = self.basis.express(
                    self.target ^ left_value ^ right_value ^ third_value
                )
                return [left_form, right_form, third_form], linear
        return None

    @staticmethod
    def evaluate(expression, tables):
        value = 0
        for bit, table in enumerate(tables):
            if (expression >> bit) & 1:
                value ^= table
        return value

    def verify(self, products, linear):
        result = self.evaluate(linear, self.tables)
        for a, b in products:
            result ^= self.evaluate(a, self.tables) & self.evaluate(b, self.tables)
        assert result == self.target

    def emit(self, products, linear):
        simplified = []
        for a, b in products:
            av = self.evaluate(a, self.tables)
            bv = self.evaluate(b, self.tables)
            if not av or not bv:
                continue
            if av == MASK:
                linear ^= b
            elif bv == MASK or av == bv:
                linear ^= a
            else:
                simplified.append((a, b))
        operations = []
        for a, b in simplified:
            _, a_mask = self.basis.wire_mask(a)
            _, b_mask = self.basis.wire_mask(b)
            choices = None
            for a_wire in WIRES:
                if not (a_mask >> WIRES.index(a_wire)) & 1:
                    continue
                for b_wire in WIRES:
                    if not (b_mask >> WIRES.index(b_wire)) & 1:
                        continue
                    if a_wire == b_wire:
                        continue
                    if (a_mask >> WIRES.index(b_wire)) & 1:
                        continue
                    if (b_mask >> WIRES.index(a_wire)) & 1:
                        continue
                    choices = (a_wire, b_wire)
                    break
                if choices:
                    break
            if choices is None:
                raise ValueError("Cannot allocate independent control accumulators")
            a_wire, b_wire = choices
            pre = []
            for expression, mask, accumulator in (
                (a, a_mask, a_wire),
                (b, b_mask, b_wire),
            ):
                for index, wire in enumerate(WIRES):
                    if wire != accumulator and (mask >> index) & 1:
                        pre.append(f"CX q{wire} q{accumulator}")
                if expression & 1:
                    pre.append(f"X q{accumulator}")
            operations.extend(pre)
            operations.append(f"CCX q{a_wire} q{b_wire} q{self.block.target}")
            operations.extend(reversed(pre))
        constant, mask = self.basis.wire_mask(linear)
        for index, wire in enumerate(WIRES):
            if (mask >> index) & 1:
                operations.append(f"CX q{wire} q{self.block.target}")
        if constant:
            operations.append(f"X q{self.block.target}")
        return operations


def simulate_region(lines, seed=913):
    circuit = km.Circuit("\n".join(lines[REGION_START:REGION_END]))
    simulator = km.Simulator(batch_size=256, seed=seed)
    address_values = []
    for bit, wire in enumerate(ADDRESS):
        values = [bool((address >> bit) & 1) for address in range(256)]
        simulator.write_across_shots(km.q(wire), values)
        address_values.append(values)
    simulator.do(circuit)
    values = {
        wire: list(simulator.read_across_shots(km.q(wire))) for wire in (*ADDRESS, *POOL)
    }
    phases = [simulator.read_shot_phase(index) for index in range(256)]
    return values, phases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("circuit", type=Path)
    parser.add_argument("--block", type=int, default=66, help="Zero-based block index")
    parser.add_argument("--conflicts", type=int, default=100000)
    parser.add_argument("--solver", default="cadical195")
    parser.add_argument("--validate-existing", action="store_true")
    parser.add_argument(
        "--nondegenerate",
        action="store_true",
        help="Require all controls to be nonconstant and pairwise distinct",
    )
    parser.add_argument("--simple", action="store_true", help="Search individual-wire products")
    parser.add_argument("--weight-two", action="store_true", help="Search two-wire control forms")
    parser.add_argument("--neighborhood", action="store_true", help="Search near existing products")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    lookup = Lookup(args.circuit)
    block = lookup.blocks[args.block]
    and_count = len(block.terms) if args.validate_existing else len(block.terms) - 1
    if and_count < 0:
        raise ValueError("Cannot reduce this block")
    synthesis = BlockSynthesis(lookup, block, and_count)
    if args.nondegenerate:
        if not and_count:
            raise ValueError("A zero-product representation cannot be nondegenerate")
        synthesis.require_nondegenerate()
    if args.simple or args.weight_two or args.neighborhood:
        start = time.monotonic()
        simple = (
            synthesis.neighborhood_search()
            if args.neighborhood
            else synthesis.simple_search(args.weight_two)
        )
        if simple is None:
            result = {"status": "unknown", "seconds": time.monotonic() - start}
        else:
            products, linear = simple
            synthesis.verify(products, linear)
            result = {
                "status": "sat",
                "seconds": time.monotonic() - start,
                "products": products,
                "linear": linear,
            }
    else:
        result = synthesis.solve(args.conflicts, args.validate_existing, args.solver)
    result.update(
        block=args.block,
        target=f"q{block.target}",
        and_count=and_count,
        nondegenerate=args.nondegenerate,
    )
    print(json.dumps(result, indent=2), flush=True)
    if result["status"] != "sat" or args.validate_existing:
        if args.report:
            args.report.write_text(json.dumps(result, indent=2) + "\n")
        return
    operations = synthesis.emit(result["products"], result["linear"])
    lines = [*lookup.lines[: block.start], *operations, *lookup.lines[block.end :]]
    values, phases = simulate_region(lookup.lines)
    new_values, new_phases = simulate_region(lines)
    assert values == new_values
    assert phases == new_phases
    candidate = km.Circuit("\n".join(lines))
    assert candidate.num_qubits == lookup.circuit.num_qubits == 63
    old_stats = lookup.circuit.operation_statistics()
    new_stats = candidate.operation_statistics()
    removed = old_stats.num_toffoli_like - new_stats.num_toffoli_like
    assert removed >= 1
    assert new_stats.num_z_pow == old_stats.num_z_pow
    result.update(
        emitted_operations=len(operations),
        old_instructions=len(lookup.lines),
        new_instructions=len(lines),
        old_toffoli_like=old_stats.num_toffoli_like,
        new_toffoli_like=new_stats.num_toffoli_like,
        exhaustive_region_equivalence=True,
    )
    if args.output:
        if args.output.exists():
            raise FileExistsError(args.output)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        candidate.to_file(args.output, format="kmb")
    if args.report:
        args.report.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
