"""Search exact split-ANF syntheses of the public invsqrt lookup.

The rank-pairing construction follows the Apache-2.0 `paired_anf.py` method
published in SomeJoint's chemistry notebook. This is an independent, table-only
implementation; no downloaded notebook code is executed.
"""

import argparse
import dataclasses
import json
import time
from pathlib import Path

import numpy as np
from analyze_public_invsqrt import POOL, Lookup


def bits(value):
    while value:
        bit = value & -value
        yield bit.bit_length() - 1
        value ^= bit


def coefficient_polys(words, output_count):
    """Mobius-transform packed output words into one polynomial per output."""
    coefficients = [int(word) for word in words]
    for bit in range(8):
        for mask in range(256):
            if mask & (1 << bit):
                coefficients[mask] ^= coefficients[mask ^ (1 << bit)]
    return [
        sum(1 << mask for mask, coefficient in enumerate(coefficients) if coefficient >> output & 1)
        for output in range(output_count)
    ]


def output_basis(polys):
    pivots = {}
    basis = []
    coordinates = []
    for poly in polys:
        reduced, coordinate = poly, 0
        while reduced:
            pivot = reduced.bit_length() - 1
            if pivot not in pivots:
                index = len(basis)
                basis.append(reduced)
                pivots[pivot] = reduced, 1 << index
                coordinate ^= 1 << index
                break
            row, row_coordinate = pivots[pivot]
            reduced ^= row
            coordinate ^= row_coordinate
        coordinates.append(coordinate)
    fanouts = [
        sum(1 << output for output, coordinate in enumerate(coordinates) if coordinate >> index & 1)
        for index in range(len(basis))
    ]
    return basis, fanouts


def matrix(poly, low_bits):
    stride = 1 << low_bits
    columns = [0] * (256 >> low_bits)
    pure_low = pure_high = 0
    for monomial in bits(poly):
        low, high = monomial & (stride - 1), monomial >> low_bits
        if high == 0:
            pure_low ^= 1 << low
        elif low == 0:
            pure_high ^= 1 << high
        else:
            columns[high - 1] ^= 1 << low
    return columns, pure_low, pure_high


def rank_decomposition(columns):
    pivots = {}
    lefts = []
    rights = []
    for column_index, original in enumerate(columns, 1):
        reduced, coordinate = original, 0
        while reduced:
            pivot = reduced.bit_length() - 1
            if pivot not in pivots:
                index = len(lefts)
                lefts.append(reduced)
                rights.append(0)
                pivots[pivot] = reduced, 1 << index
                coordinate ^= 1 << index
                break
            row, row_coordinate = pivots[pivot]
            reduced ^= row
            coordinate ^= row_coordinate
        for index in bits(coordinate):
            rights[index] ^= 1 << column_index
    return list(zip(lefts, rights))


def poly_product(left, right, max_mask):
    result = 0
    for i in bits(left):
        for j in bits(right):
            if (i | j) <= max_mask:
                result ^= 1 << (i | j)
    return result


def parity_value(poly, address):
    return sum(address & monomial == monomial for monomial in bits(poly)) & 1


@dataclasses.dataclass
class Product:
    left1: int
    right1: int
    left2: int
    right2: int
    fanout: int


@dataclasses.dataclass
class Plan:
    low_bits: int
    products: list
    pure: dict
    cache_masks: list

    @property
    def cost(self):
        return len(self.products) + len(self.cache_masks)

    def evaluate(self, address):
        low = address & ((1 << self.low_bits) - 1)
        high = address >> self.low_bits
        result = 0
        for product in self.products:
            left = parity_value(product.left1, low) ^ parity_value(product.right2, high)
            right = parity_value(product.left2, low) ^ parity_value(product.right1, high)
            if left & right:
                result ^= product.fanout
        for mask, fanout in self.pure.items():
            if address & mask == mask:
                result ^= fanout
        return result


def product_cost(poly, low_bits, cache):
    if poly not in cache:
        cache[poly] = (len(rank_decomposition(matrix(poly, low_bits)[0])) + 1) // 2
    return cache[poly]


def mix_output_basis(funcs, fanouts, low_bits, steps, rng, plateau=False):
    funcs, fanouts = funcs[:], fanouts[:]
    costs = {}
    current = [product_cost(poly, low_bits, costs) for poly in funcs]
    for _ in range(steps):
        i, j = rng.choice(len(funcs), 2, replace=False)
        new = funcs[i] ^ funcs[j]
        new_cost = product_cost(new, low_bits, costs)
        if new_cost < current[i] or (plateau and new_cost == current[i]):
            funcs[i] = new
            fanouts[j] ^= fanouts[i]
            current[i] = new_cost
    return funcs, fanouts


def make_plan(funcs, fanouts, low_bits, share_odd=False):
    funcs, fanouts = funcs[:], fanouts[:]
    products = []
    if share_odd:
        low_rank = (1 << low_bits) - 1
        high_rank = 255 >> low_bits
        full_rank = min(low_rank, high_rank)
        eligible = [
            i
            for i, poly in enumerate(funcs)
            if len(rank_decomposition(matrix(poly, low_bits)[0])) == full_rank
        ]
        if full_rank >= 3 and full_rank & 1:
            for i, j in zip(eligible[::2], eligible[1::2]):
                left_columns = matrix(funcs[i], low_bits)[0]
                right_columns = matrix(funcs[j], low_bits)[0]
                if low_rank <= high_rank:
                    left1, left2 = 1 << 1, 1 << 2
                    right1 = sum(
                        1 << (high + 1)
                        for high, column in enumerate(left_columns)
                        if column >> 1 & 1
                    )
                    right2 = sum(
                        1 << (high + 1)
                        for high, column in enumerate(right_columns)
                        if column >> 2 & 1
                    )
                else:
                    left1, left2 = left_columns[0], right_columns[1]
                    right1, right2 = 1 << 1, 1 << 2
                products.append(Product(left1, right1, left2, right2, fanouts[i] ^ fanouts[j]))
                full_poly = 0
                for low in bits(left1):
                    for high in bits(right1):
                        full_poly ^= 1 << (low | (high << low_bits))
                for low in bits(left2):
                    for high in bits(right2):
                        full_poly ^= 1 << (low | (high << low_bits))
                full_poly ^= poly_product(left1, left2, (1 << low_bits) - 1)
                for high in bits(poly_product(right1, right2, 255 >> low_bits)):
                    full_poly ^= 1 << (high << low_bits)
                funcs[i] ^= full_poly
                funcs[j] ^= full_poly
    pure = {}
    low_max, high_max = (1 << low_bits) - 1, 255 >> low_bits

    def add_pure(poly, fanout, shift):
        for monomial in bits(poly):
            full = monomial << shift
            pure[full] = pure.get(full, 0) ^ fanout

    for poly, fanout in zip(funcs, fanouts):
        columns, low, high = matrix(poly, low_bits)
        factors = rank_decomposition(columns)
        for index in range(0, len(factors), 2):
            left1, right1 = factors[index]
            left2, right2 = factors[index + 1] if index + 1 < len(factors) else (0, 0)
            products.append(Product(left1, right1, left2, right2, fanout))
            low ^= poly_product(left1, left2, low_max)
            high ^= poly_product(right1, right2, high_max)
        add_pure(low, fanout, 0)
        add_pure(high, fanout, low_bits)
    pure = {mask: fanout for mask, fanout in pure.items() if fanout}
    used = set(pure)
    for product in products:
        used.update(bits(product.left1 | product.left2))
        used.update(mask << low_bits for mask in bits(product.right1 | product.right2))
    for mask in list(used):
        while mask and mask.bit_count() >= 2:
            used.add(mask)
            mask ^= 1 << (mask.bit_length() - 1)
    cache_masks = sorted(mask for mask in used if mask.bit_count() >= 2)
    return Plan(low_bits, products, pure, cache_masks)


def plan_record(plan):
    return {
        "ands": plan.cost,
        "products": len(plan.products),
        "cache_monomials": len(plan.cache_masks),
        "low_bits": plan.low_bits,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("circuit", type=Path)
    parser.add_argument("--steps", type=int, default=100000)
    parser.add_argument("--restarts", type=int, default=4)
    parser.add_argument("--seed", type=int, default=913)
    parser.add_argument("--low-bits", type=int, default=4)
    parser.add_argument("--share-odd", action="store_true")
    parser.add_argument("--plateau", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    lookup = Lookup(args.circuit)
    outputs = [wire for wire in POOL if lookup.states[16278][wire]]
    words = np.array(
        [
            sum(((lookup.states[16278][wire] >> address) & 1) << i for i, wire in enumerate(outputs))
            for address in range(256)
        ],
        dtype=np.int64,
    )
    polys = coefficient_polys(words, len(outputs))
    # The wires at 16278 already carry the public search's optimized invertible
    # output basis. Preserve that starting point instead of replacing it with
    # an arbitrary Gaussian-elimination basis.
    initial = polys, [1 << i for i in range(len(outputs))]
    baseline = make_plan(*initial, args.low_bits, args.share_odd)
    assert all(baseline.evaluate(address) == int(words[address]) for address in range(256))
    best = baseline
    records = [{"restart": "baseline", **plan_record(best)}]
    rng = np.random.default_rng(args.seed)
    start = time.monotonic()
    for restart in range(args.restarts):
        funcs, fanouts = mix_output_basis(
            *initial, args.low_bits, args.steps, rng, plateau=args.plateau
        )
        plan = make_plan(funcs, fanouts, args.low_bits, args.share_odd)
        assert all(plan.evaluate(address) == int(words[address]) for address in range(256))
        records.append({"restart": restart, **plan_record(plan)})
        if plan.cost < best.cost:
            best = plan
        print(json.dumps(records[-1]), flush=True)
    result = {
        "seconds": time.monotonic() - start,
        "seed": args.seed,
        "steps": args.steps,
        "share_odd": args.share_odd,
        "plateau": args.plateau,
        "best": plan_record(best),
        "runs": records,
    }
    print(json.dumps(result, indent=2))
    if args.report:
        args.report.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
