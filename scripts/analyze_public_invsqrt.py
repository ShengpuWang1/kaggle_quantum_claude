"""Recover the exact XOR/AND structure of busyaprime's public invsqrt lookup."""

import argparse
import dataclasses
import json
from pathlib import Path

import kickmix as km

ADDRESS = tuple(range(14, 22))
POOL = (22, *range(24, 63))
WIRES = (*ADDRESS, *POOL)
REGION_START = 262
REGION_END = 16681
MASK = (1 << 256) - 1


def qubit(token):
    assert token.startswith("q")
    return int(token[1:])


def address_table(bit):
    return sum(((address >> bit) & 1) << address for address in range(256))


@dataclasses.dataclass(frozen=True)
class Term:
    start: int
    end: int
    controls: tuple[int, int]


@dataclasses.dataclass(frozen=True)
class Block:
    target: int
    start: int
    end: int
    terms: tuple[Term, ...]


class AffineBasis:
    """GF(2) basis for affine functions, with expressions in selected wires."""

    def __init__(self):
        self.rows = {}
        self.wires = []

    def _reduce(self, value):
        expression = 0
        while value:
            pivot = value.bit_length() - 1
            if pivot not in self.rows:
                break
            row, row_expression = self.rows[pivot]
            value ^= row
            expression ^= row_expression
        return value, expression

    def add(self, value, wire=None):
        reduced, expression = self._reduce(value)
        if not reduced:
            return False
        if wire is None:
            assert not self.wires and not self.rows
            index = 0
        else:
            index = len(self.wires) + 1
            self.wires.append(wire)
        expression ^= 1 << index
        pivot = reduced.bit_length() - 1
        self.rows[pivot] = (reduced, expression)
        return True

    def express(self, value):
        reduced, expression = self._reduce(value)
        if reduced:
            raise ValueError("Function is outside the affine span")
        return expression

    def wire_mask(self, expression):
        constant = expression & 1
        mask = 0
        for index, wire in enumerate(self.wires, 1):
            if (expression >> index) & 1:
                mask |= 1 << WIRES.index(wire)
        return constant, mask


class Lookup:
    def __init__(self, path):
        self.path = Path(path)
        self.circuit = km.Circuit.from_file(self.path, format="kmb")
        self.lines = str(self.circuit).splitlines()
        assert self.circuit.num_qubits == 63
        assert len(self.lines) >= REGION_END
        self.states = self._simulate()
        self.blocks = self._blocks()

    def _simulate(self):
        values = {wire: 0 for wire in WIRES}
        values.update({wire: address_table(i) for i, wire in enumerate(ADDRESS)})
        states = {REGION_START: values.copy()}
        for index in range(REGION_START, REGION_END):
            operation = self.lines[index].split()
            name = operation[0]
            if name == "R":
                values[qubit(operation[1])] = 0
            elif name == "X":
                values[qubit(operation[1])] ^= MASK
            elif name == "CX":
                values[qubit(operation[2])] ^= values[qubit(operation[1])]
            elif name == "CCX":
                a, b, target = map(qubit, operation[1:])
                values[target] ^= values[a] & values[b]
            elif name == "SWAP":
                a, b = map(qubit, operation[1:])
                values[a], values[b] = values[b], values[a]
            elif name == "HMR":
                values[qubit(operation[1])] = 0
            elif name == "CZ":
                pass
            else:
                raise ValueError((index, operation))
            states[index + 1] = values.copy()
        return states

    def _blocks(self):
        operations = [line.split() for line in self.lines]
        starts = [
            index
            for index in range(REGION_START, REGION_END)
            if operations[index][0] in {"R", "HMR"}
        ]
        blocks = []
        for position, start in enumerate(starts):
            stop = starts[position + 1] if position + 1 < len(starts) else REGION_END
            target = qubit(operations[start][1])
            count = sum(
                operations[index][0] == "CCX" for index in range(start + 1, stop)
            )
            if not count:
                continue
            ccx_indices = [
                index
                for index in range(start + 1, stop)
                if operations[index][0] == "CCX"
            ]
            first_ccx, last_ccx = ccx_indices[0], ccx_indices[-1]
            other_wires = tuple(wire for wire in WIRES if wire != target)
            start_signatures = {}
            for candidate in range(start + 1, first_ccx + 1):
                if self.states[candidate][target] == 0:
                    signature = tuple(self.states[candidate][wire] for wire in other_wires)
                    start_signatures[signature] = candidate
            boundaries = None
            for candidate_end in range(last_ccx + 1, stop):
                signature = tuple(self.states[candidate_end][wire] for wire in other_wires)
                if signature in start_signatures:
                    boundaries = (start_signatures[signature], candidate_end)
                    break
            assert boundaries is not None, (start, target)
            block_start, block_end = boundaries
            for index in range(block_start, block_end):
                operation = operations[index]
                if target in map(qubit, operation[1:]):
                    assert operation[0] == "CCX" and qubit(operation[3]) == target
            terms = tuple(Term(ccx, ccx + 1, (ccx, ccx)) for ccx in ccx_indices)
            blocks.append(Block(target, block_start, block_end, terms))
        assert len(blocks) == 67
        assert sum(len(block.terms) for block in blocks) == 172
        return tuple(blocks)

    def basis_at(self, index):
        basis = AffineBasis()
        basis.add(MASK)
        state = self.states[index]
        for wire in WIRES:
            basis.add(state[wire], wire)
        return basis

    def block_representation(self, block):
        basis = self.basis_at(block.start)
        products = []
        for term in block.terms:
            ccx = term.controls[0]
            operation = self.lines[ccx].split()
            a, b, _ = map(qubit, operation[1:])
            state = self.states[ccx]
            products.append((basis.express(state[a]), basis.express(state[b])))
        target = self.states[block.end][block.target]
        residual = target
        for term in block.terms:
            ccx = term.controls[0]
            operation = self.lines[ccx].split()
            a, b, _ = map(qubit, operation[1:])
            before = self.states[ccx]
            residual ^= before[a] & before[b]
        linear = basis.express(residual)
        return basis, products, linear


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("circuit", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    lookup = Lookup(args.circuit)
    report = {
        "circuit": str(args.circuit),
        "region": [REGION_START, REGION_END],
        "address": ADDRESS,
        "pool": POOL,
        "ands": sum(len(block.terms) for block in lookup.blocks),
        "blocks": [
            {
                "target": f"q{block.target}",
                "start": block.start,
                "end": block.end,
                "ands": len(block.terms),
                "affine_basis_size": len(lookup.basis_at(block.start).wires) + 1,
            }
            for block in lookup.blocks
        ],
        "nonzero_outputs": [
            f"q{wire}" for wire in POOL if lookup.states[16278][wire]
        ],
    }
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        if args.output.exists():
            raise FileExistsError(args.output)
        args.output.write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
