"""Search fresh ANGLE loaders for the current C60 angle-word batches."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import kickmix as km
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "candidates/busyaprime_v9_somejoint_897q/dfthcsos"
LOADER_SOURCE = ROOT / "runs/paper_research/notebooks/somejoint-chemistry-22-44/source/blocks/dfthcsos/team-b143-c62/source/exp/loader_port"


def sha256(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=int)
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--seed", type=int, default=772601)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 0 <= args.batch < 15:
        parser.error("batch must be in 0..14")
    if args.output.exists():
        parser.error(f"Refusing to overwrite {args.output}")
    args.output.mkdir(parents=True)

    with np.load(CURRENT / "submission.npz", allow_pickle=False) as z:
        words = np.asarray(z["angle_words"], np.int64)
        brot = int(z["brot"])
    batches = words.reshape(len(words), 15, 5)
    deltas = batches.copy()
    deltas[:, 1:] ^= batches[:, :-1]
    incumbent_path = CURRENT / f"angle_k_{args.batch}.kmb"
    incumbent = km.Circuit.from_file(incumbent_path, format="kmb")
    old_t = int(incumbent.operation_statistics().num_toffoli_like)
    old_q = int(incumbent.num_qubits)

    import sys
    sys.path.insert(0, str(ROOT / "data/official/verifiers"))
    sys.path.insert(0, str(LOADER_SOURCE))
    import loader

    start = time.monotonic()
    circuit, metadata, plan, schedule = loader.choose_delta(
        deltas[:, args.batch], seconds=args.seconds, seed=args.seed, brot=brot
    )
    new_t = int(circuit.operation_statistics().num_toffoli_like)
    new_q = int(circuit.num_qubits)
    winner = new_t < old_t and new_q <= 128
    circuit_path = args.output / f"angle_k_{args.batch}.kmb"
    if winner:
        circuit.to_file(circuit_path, format="kmb")
    report = {
        "batch": args.batch,
        "seconds_requested": args.seconds,
        "seconds_actual": time.monotonic() - start,
        "seed": args.seed,
        "incumbent": {"T": old_t, "Q": old_q, "sha256": sha256(incumbent_path)},
        "candidate": {"T": new_t, "Q": new_q, "metadata": metadata},
        "winner": winner,
        "circuit": str(circuit_path) if winner else None,
        "circuit_sha256": sha256(circuit_path) if winner else None,
    }
    (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
