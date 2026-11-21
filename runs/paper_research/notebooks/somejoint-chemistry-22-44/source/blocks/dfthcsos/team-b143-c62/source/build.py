"""Build our research team's chemistry submission from its frozen plans: the 15 angle circuits, written as
OUTPUT/angle_k_K.kmb, and the factorization file, copied to OUTPUT/submission.npz.

SPDX-License-Identifier: Apache-2.0
Usage: python -B build.py OUTPUT, with Kickmix importable. The official verifier's dfthcsos package is taken from
beside Kickmix, for its submission digest. data/submission.npz holds the factorization (R = 8, B = 143, C = 62) and
its angle words; data/BUILD.json holds each circuit's plan and schedule, as the team froze them on 28 October 2026.
Circuit k loads, for every row, the XOR of the row's batches k and k - 1 of five words. Each circuit must come out
with the SHA-256 the team recorded, and the circuits must load exactly the submitted words.
"""
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import time

import kickmix as km
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(Path(km.__file__).resolve().parents[1] / 'verifiers'), str(HERE / 'exp/loader_port')]
import loader  # noqa: E402
from staged_b154.paired_anf import Plan, Product  # noqa: E402
from dfthcsos.scoreinfra.circuits import recover_words_from_circuits, submission_sha256  # noqa: E402

DIGEST = '377c00809b8bb12f5d16dbf5d0a4874e718be7eefe08c8ced513f908345a1d9e'


def from_dict(d):
    """A plan as the team's build script reads it back from BUILD.json."""
    return Plan(d['addresses'], d['batch'], d['brot'], d['low_bits'],
                [Product(**p) for p in d['products']], {int(k): v for k, v in d['pure'].items()},
                d['ranks'], d['cache_masks'],
                blocks=None if d['blocks'] is None else [from_dict(x) for x in d['blocks']],
                parity_scratch=d['parity_scratch'])


def main(out):
    start = time.time()
    out.mkdir(parents=True, exist_ok=True)
    frozen = json.loads((HERE / 'data/BUILD.json').read_text())
    shutil.copyfile(HERE / 'data/submission.npz', out / 'submission.npz')
    z = dict(np.load(out / 'submission.npz', allow_pickle=False))
    words, brot = np.asarray(z['angle_words'], np.int64), int(z['brot'])
    # The circuits keep a word's top bit as scratch, so every word must have its top two bits equal.
    assert brot == 8 and words.shape[1] == 75 and np.all((words >> 7) == ((words >> 6) & 1))
    batches = words.reshape(len(words), 15, 5)
    deltas = batches.copy()
    deltas[:, 1:] ^= batches[:, :-1]
    circuits, rows = [], []
    for k, r in enumerate(frozen['batches']):
        assert r['batch'] == k
        c, m, _, _ = loader.build_delta(deltas[:, k], plan=from_dict(r['plan']), saved_schedule=r['schedule'],
                                        brot=brot)
        stream = io.BytesIO()
        c.to_file(stream, format='kmb')
        blob = stream.getvalue()
        assert hashlib.sha256(blob).hexdigest() == r['circuit_sha256'], f'angle_k_{k}: not the frozen circuit'
        assert m['Q'] <= 128
        (out / f'angle_k_{k}.kmb').write_bytes(blob)
        circuits.append(c)
        rows.append(dict(batch=k, T=m['T'], Q=m['Q'], sha256=r['circuit_sha256']))
    recovered, _, _ = recover_words_from_circuits(circuits, num_vectors=len(words), num_angles=75,
                                                  shots_per_address=1, seed=1901728)
    assert np.array_equal(recovered, words), 'the circuits must load exactly the submitted angle words'
    digest = submission_sha256(circuits, z, z['tree_edges'])
    assert digest == DIGEST, f'submission digest {digest}, not the one the verifier passed'
    total = sum(r['T'] for r in rows)
    record = dict(submission_sha256=digest, circuits=rows, T_both_passes=2 * total, Q_max=max(r['Q'] for r in rows),
                  seconds=round(time.time() - start, 1),
                  summary=f'{len(rows)} angle circuits, {total:,} Toffolis per pass, at most {max(r["Q"] for r in rows)}'
                          f' qubits; submission digest {digest[:12]}..., the one the verifier passed')
    out.with_suffix('.build.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record), flush=True)


if __name__ == '__main__':
    main(Path(sys.argv[1]))
