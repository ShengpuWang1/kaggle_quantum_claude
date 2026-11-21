"""Checkpoint the experimental external node before reverse normalization."""

import importlib
import sys
from pathlib import Path

import kickmix as km
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "candidates/busyaprime_v9_dqi_full_replay/source/dqi"
sys.modules["circ"] = km
sys.path[:0] = [
    str(SOURCE / "exp/r-main/stream"),
    str(SOURCE / "playbook/kit/decoder"),
    str(SOURCE / "playbook/kit/decoder/exp/convert"),
    str(SOURCE / "playbook/kit/decoder/exp/arithmetic"),
    str(SOURCE / "playbook/kit"),
]
replay = importlib.import_module("replay_erase")
ref = replay.ref


def bits(values, width):
    values = np.asarray(values, dtype=np.int64)
    return ((values[None, :] >> np.arange(width)[:, None]) & 1).astype(bool)


def integers(values):
    return np.sum(values.astype(np.int64) << np.arange(len(values))[:, None], axis=0)


def build(gi, experimental):
    b = km.CircuitBuilder()
    words = [b.alloc_qubits(12) for _ in range(4 * gi + 4)]
    token = ref.external_node_chain(b, words, gi)
    live_bit_ids = {bit.id for bit in [*token["gauge"], *token["norm"]]}
    g = ref.groups[gi]
    N = replay.combine(words[g["word"]:g["word"] + 2])
    L = replay.combine(words[g["word"] + 2:g["word"] + 4])
    heads = [words[2 * i:2 * i + 2] for i in range(2 * gi)]
    params = []
    c = 0
    for i in range(2 * gi):
        q = ref.ks[i] ^ g["kap"]
        params.append((q, c))
        c ^= replay.inv(q)
    pole = token["pole"]
    D = b.alloc_qubits(24)
    b.x(D[0])
    b.cswap(pole, N, D)
    q0 = params[0][0]
    for i in reversed(range(1, len(heads))):
        head, (q, c) = heads[i], params[i]
        if experimental and i == 1:
            replay.scalepair(b, N, replay.inv(q))
            b.swap(N, D)
            for j in replay.ar.bits(q0):
                b.x(N[j])
            m = b.alloc_bits(24)
            print("mask overlap", live_bit_ids & {bit.id for bit in m}, flush=True)
            b.hmr(N, m)
            a, h = head
            replay.cx(b, h, a, g["c"])
            replay.phase_product24(b, replay.combine(head), D, m, replay.K)
            replay.cx(b, h, a, g["c"])
            for j in replay.ar.bits(q0):
                b.z(m[j])
            b.free(m)
            for j in replay.ar.bits(q0):
                b.x(N[j])
            replay.scalepair(b, L, replay.inv(q))
            ref.external_square24(b, D)
            ref.external_corrected_product(b, head, D, L, g["c"], c)
            ref.external_square24(b, D, True)
        else:
            ref.external_chain_step(b, head, N, D, L, q, g["c"], c, True)
    replay.scalepair(b, N, replay.inv(q0))
    b.swap(N, D)
    replay.scalepair(b, L, replay.inv(q0))
    a, h = heads[0]
    replay.cx(b, h, a, g["c"])
    b.cx(replay.combine(heads[0]), N)
    replay.cx(b, h, a, g["c"])
    b.cx(h, L[:12])
    return b.finish_circuit(), words


def main():
    rng = np.random.default_rng(76123)
    shots = 128
    gi = 8
    reference, words = build(gi, False)
    experiment, _ = build(gi, True)
    values = [rng.integers(0, 1 << 12, size=shots) for _ in words]

    def run(circuit):
        sim = km.Simulator(batch_size=shots, seed=76123)
        for register, value in zip(words, values):
            sim.write_across_shots(register, bits(value, 12))
        sim.do(circuit)
        output = [integers(sim.read_across_shots(register)) for register in words]
        return output, sim.read_phase_flipped_across_shots()

    expected, expected_phase = run(reference)
    actual, actual_phase = run(experiment)
    for i, (want, got) in enumerate(zip(expected, actual)):
        mismatches = np.flatnonzero(want != got)
        if len(mismatches):
            print("word", i, "mismatches", len(mismatches), "first", mismatches[:5].tolist())
    print("value mismatches", sum(int(np.count_nonzero(want != got)) for want, got in zip(expected, actual)))
    print("phase mismatches", int(np.count_nonzero(expected_phase != actual_phase)))
    assert all(np.array_equal(want, got) for want, got in zip(expected, actual))
    assert np.array_equal(expected_phase, actual_phase)


if __name__ == "__main__":
    main()
