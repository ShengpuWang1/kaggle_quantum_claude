"""Jointly synthesize two four-AND invsqrt outputs with one shared product."""

import argparse
import itertools
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import kickmix as km
from pysat.solvers import Solver

from analyze_public_invsqrt import MASK, REGION_END, WIRES, Lookup
from optimize_public_invsqrt_lookup import BlockSynthesis, Cnf, simulate_region


class JointSynthesis:
    def __init__(self, lookup, first, second):
        self.lookup = lookup
        self.first = first
        self.second = second
        self.bases = [lookup.basis_at(first.start), lookup.basis_at(second.start)]
        self.tables_by_output = [
            [MASK] + [lookup.states[index][wire] for wire in basis.wires]
            for index, basis in zip((first.start, second.start), self.bases)
        ]
        self.tables = self.tables_by_output[0]
        self.targets = [lookup.states[first.end][first.target], lookup.states[second.end][second.target]]
        self.existing = []
        for block in self.first, self.second:
            _, products, linear = lookup.block_representation(block)
            self.existing.append((products, linear))
        self.storage = self._storage_wire()
        bit_ids = [
            int(token[1:])
            for line in lookup.lines
            for token in line.split()
            if token.startswith("b") and token[1:].isdigit()
        ]
        self.phase_bit = max(bit_ids, default=-1) + 1
        self.cnf = Cnf()
        dimensions = [len(self.tables_by_output[0 if index < 4 else 1]) for index in range(7)]
        self.a_variables = [self._form(dimension) for dimension in dimensions]
        self.b_variables = [self._form(dimension) for dimension in dimensions]
        for variables in [*self.a_variables, *self.b_variables]:
            self.cnf.unit(variables[0], False)
        self.linear_variables = [self._form(len(tables)) for tables in self.tables_by_output]
        for a, b in zip(self.a_variables, self.b_variables):
            self.cnf.lex_leq(a, b)
        for group in (range(1, 4), range(4, 7)):
            for left, right in zip(group, list(group)[1:]):
                self.cnf.lex_leq(self.a_variables[left], self.a_variables[right])
        self._encode()

    def _storage_wire(self):
        for wire in WIRES:
            if wire in {self.first.target, self.second.target}:
                continue
            if self.lookup.states[self.first.start][wire]:
                continue
            touched = False
            for index in range(self.first.end, self.second.start):
                operation = self.lookup.lines[index].split()
                if wire in [int(token[1:]) for token in operation[1:] if token.startswith("q")]:
                    touched = True
                    break
            if not touched:
                return wire
        raise ValueError("No clean storage wire persists between the blocks")

    def _form(self, dimension):
        return [self.cnf.variable() for _ in range(dimension)]

    def _affine(self, variables, address, tables):
        return self.cnf.xor(
            variables[bit] for bit, table in enumerate(tables) if (table >> address) & 1
        )

    def _encode(self):
        for address in range(256):
            products = []
            for index, (a_variables, b_variables) in enumerate(zip(self.a_variables, self.b_variables)):
                tables = self.tables_by_output[0 if index < 4 else 1]
                a = self._affine(a_variables, address, tables)
                b = self._affine(b_variables, address, tables)
                products.append(self.cnf.conjunction(a, b))
            linear = [self._affine(variables, address, tables) for variables, tables in zip(self.linear_variables, self.tables_by_output)]
            first = self.cnf.xor([*products[:4], linear[0]])
            second = self.cnf.xor([products[0], *products[4:], linear[1]])
            self.cnf.unit(first, bool((self.targets[0] >> address) & 1))
            self.cnf.unit(second, bool((self.targets[1] >> address) & 1))

    def require_nondegenerate(self):
        """Exclude products that are affine, duplicated, or mergeable within an output."""
        groups = ([0, 1, 2, 3], [0, 4, 5, 6])
        for group in groups:
            controls = [control for index in group for control in (self.a_variables[index], self.b_variables[index])]
            for variables in controls:
                self.cnf.clauses.append(variables[1:])
            for left, right in itertools.combinations(controls, 2):
                differences = [self.cnf.xor([a, b]) for a, b in zip(left, right)]
                self.cnf.clauses.append(differences)

    def _hints(self):
        products = [self.existing[0][0][0], *self.existing[0][0][1:], *self.existing[1][0][:3]]
        linears = [self.existing[0][1], self.existing[1][1]]
        normalized = []
        for index, (a, b) in enumerate(products):
            linear = linears[0 if index < 4 else 1]
            alpha, beta = a & 1, b & 1
            if alpha:
                linear ^= b
            if beta:
                linear ^= a
            if alpha and beta:
                linear ^= 1
            normalized.append((tuple(sorted((a ^ alpha, b ^ beta))), linear))
        hints = []
        for index, ((a, b), _) in enumerate(normalized):
            for expression, variables in ((a, self.a_variables[index]), (b, self.b_variables[index])):
                hints.extend(variable if (expression >> bit) & 1 else -variable for bit, variable in enumerate(variables))
        for index, linear in enumerate(linears):
            hints.extend(variable if (linear >> bit) & 1 else -variable for bit, variable in enumerate(self.linear_variables[index]))
        return hints

    @staticmethod
    def evaluate(expression, tables):
        value = 0
        for bit, table in enumerate(tables):
            if (expression >> bit) & 1:
                value ^= table
        return value

    def verify(self, products, linears):
        outputs = [self.evaluate(linear, tables) for linear, tables in zip(linears, self.tables_by_output)]
        for index, (a, b) in enumerate(products):
            tables = self.tables_by_output[0 if index < 4 else 1]
            value = self.evaluate(a, tables) & self.evaluate(b, tables)
            if index < 4:
                outputs[0] ^= value
            if index == 0 or index >= 4:
                outputs[1] ^= value
        assert outputs == self.targets

    def solve(self, conflicts, solver_name):
        start = time.monotonic()
        with Solver(name=solver_name, bootstrap_with=self.cnf.clauses) as solver:
            try:
                solver.set_phases(self._hints())
            except NotImplementedError:
                pass
            if conflicts:
                solver.conf_budget(conflicts)
                result = solver.solve_limited()
            else:
                result = solver.solve()
            if result is not True:
                return {"status": "unsat" if result is False else "unknown", "seconds": time.monotonic() - start}
            model = set(solver.get_model())
            stats = solver.accum_stats()
        def decode(variables):
            return sum(1 << bit for bit, variable in enumerate(variables) if variable in model)
        products = [(decode(a), decode(b)) for a, b in zip(self.a_variables, self.b_variables)]
        linears = [decode(variables) for variables in self.linear_variables]
        self.verify(products, linears)
        return {
            "status": "sat",
            "seconds": time.monotonic() - start,
            "variables": self.cnf.variables,
            "clauses": len(self.cnf.clauses),
            "conflicts": stats.get("conflicts"),
            "products": products,
            "linears": linears,
        }

    def _product_operations(self, a, b, target, forbidden, basis, phase_bit=None):
        operations = []
        choices = None
        _, a_mask = basis.wire_mask(a)
        _, b_mask = basis.wire_mask(b)
        for a_wire, b_wire in itertools.permutations(WIRES, 2):
            if a_wire in forbidden or b_wire in forbidden:
                continue
            ai, bi = WIRES.index(a_wire), WIRES.index(b_wire)
            if not (a_mask >> ai) & 1 or not (b_mask >> bi) & 1:
                continue
            if (a_mask >> bi) & 1 or (b_mask >> ai) & 1:
                continue
            choices = a_wire, b_wire
            break
        if choices is None:
            raise ValueError("Cannot allocate independent control accumulators")
        a_wire, b_wire = choices
        pre = []
        for expression, mask, accumulator in ((a, a_mask, a_wire), (b, b_mask, b_wire)):
            for index, wire in enumerate(WIRES):
                if wire != accumulator and (mask >> index) & 1:
                    pre.append(f"CX q{wire} q{accumulator}")
            if expression & 1:
                pre.append(f"X q{accumulator}")
        operation = f"CZ q{a_wire} q{b_wire} if b{phase_bit}" if phase_bit is not None else f"CCX q{a_wire} q{b_wire} q{target}"
        return [*pre, operation, *reversed(pre)]

    def _linear_operations(self, expression, target, basis):
        constant, mask = basis.wire_mask(expression)
        operations = [f"CX q{wire} q{target}" for index, wire in enumerate(WIRES) if (mask >> index) & 1]
        if constant:
            operations.append(f"X q{target}")
        return operations

    def emit(self, products, linears):
        forbidden = {self.first.target, self.second.target, self.storage}
        first = []
        a, b = products[0]
        first.extend(self._product_operations(a, b, self.storage, forbidden, self.bases[0]))
        first.append(f"CX q{self.storage} q{self.first.target}")
        for a, b in products[1:4]:
            first.extend(self._product_operations(a, b, self.first.target, forbidden, self.bases[0]))
        first.extend(self._linear_operations(linears[0], self.first.target, self.bases[0]))
        second = [
            f"CX q{self.storage} q{self.second.target}",
            f"HMR q{self.storage} b{self.phase_bit}",
        ]
        second.extend(self._product_operations(a, b, self.storage, forbidden, self.bases[0], self.phase_bit))
        for a, b in products[4:]:
            second.extend(self._product_operations(a, b, self.second.target, forbidden, self.bases[1]))
        second.extend(self._linear_operations(linears[1], self.second.target, self.bases[1]))
        lines = [
            *self.lookup.lines[:self.first.start],
            *first,
            *self.lookup.lines[self.first.end:self.second.start],
            *second,
            *self.lookup.lines[self.second.end:],
        ]
        return lines


def compatible_pairs(lookup):
    for first_index in range(32, 66):
        first, second = lookup.blocks[first_index:first_index + 2]
        if len(first.terms) != 4 or len(second.terms) != 4:
            continue
        try:
            JointSynthesis(lookup, first, second)
        except ValueError:
            continue
        yield first_index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("circuit", type=Path)
    parser.add_argument("--first-block", type=int, default=32)
    parser.add_argument("--second-block", type=int)
    parser.add_argument("--conflicts", type=int, default=1000000)
    parser.add_argument("--solver", default="cadical195")
    parser.add_argument("--nondegenerate", action="store_true")
    parser.add_argument("--list-compatible", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    lookup = Lookup(args.circuit)
    if args.list_compatible:
        result = {"compatible_first_blocks": list(compatible_pairs(lookup))}
    else:
        second_block = args.second_block if args.second_block is not None else args.first_block + 1
        first, second = lookup.blocks[args.first_block], lookup.blocks[second_block]
        synthesis = JointSynthesis(lookup, first, second)
        if args.nondegenerate:
            synthesis.require_nondegenerate()
        result = synthesis.solve(args.conflicts, args.solver)
        result.update(first_block=args.first_block, second_block=second_block)
        if result["status"] == "sat":
            lines = synthesis.emit(result["products"], result["linears"])
            values, phases = simulate_region(lookup.lines)
            new_values, new_phases = simulate_region(lines)
            assert values == new_values and phases == new_phases
            candidate = km.Circuit("\n".join(lines))
            old_stats = lookup.circuit.operation_statistics()
            new_stats = candidate.operation_statistics()
            assert candidate.num_qubits == lookup.circuit.num_qubits == 63
            assert old_stats.num_toffoli_like - new_stats.num_toffoli_like == 1
            assert new_stats.num_z_pow == old_stats.num_z_pow
            result.update(exhaustive_region_equivalence=True, old_toffoli_like=old_stats.num_toffoli_like, new_toffoli_like=new_stats.num_toffoli_like)
            if args.output:
                if args.output.exists():
                    raise FileExistsError(args.output)
                args.output.parent.mkdir(parents=True, exist_ok=True)
                candidate.to_file(args.output, format="kmb")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
