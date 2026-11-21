"""Package a candidate directory, checking its file contract and recording hashes."""

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def package(source, output):
    files = []
    for task in ("invsqrt", "dqi"):
        matches = [source / f"{task}.{ext}" for ext in ("kmb", "kmx")]
        matches = [p for p in matches if p.is_file()]
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one circuit for {task}")
        files.extend(matches)
    angles = sorted((source / "dfthcsos").glob("angle_k_*"))
    indices = []
    for p in angles:
        match = re.fullmatch(r"angle_k_(\d+)\.(kmb|kmx)", p.name)
        if not match or not p.is_file():
            raise ValueError(f"Unexpected angle entry: {p}")
        indices.append(int(match[1]))
    if not indices or sorted(indices) != list(range(len(indices))):
        raise ValueError("Angle indices must start at zero without gaps or duplicates")
    files.extend(angles)
    factorization = source / "dfthcsos/submission.npz"
    with np.load(factorization, allow_pickle=False) as arrays:
        required = {"U", "W", "H2_I", "H1_I", "Hsym_lower", "tree_edges"}
        if not required.issubset(arrays.files):
            raise ValueError(f"Missing arrays: {required - set(arrays.files)}")
        for key in required:
            if not np.isfinite(arrays[key]).all():
                raise ValueError(f"Nonfinite data in {key}")
    files.append(factorization)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    manifest = {}
    with zipfile.ZipFile(
        output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as z:
        for p in sorted(files):
            if p.stat().st_size == 0:
                raise ValueError(f"Empty file: {p}")
            name = p.relative_to(source).as_posix()
            z.write(p, name)
            manifest[name] = {"bytes": p.stat().st_size, "sha256": sha256(p)}
    with zipfile.ZipFile(output) as z:
        assert z.testzip() is None
        for name, record in manifest.items():
            with z.open(name) as f:
                assert hashlib.file_digest(f, "sha256").hexdigest() == record["sha256"]
    report = {
        "source": str(source),
        "zip_sha256": sha256(output),
        "files": manifest,
        "validation": "Structure, NPZ keys and ZIP byte integrity only; run official verifiers separately.",
    }
    output.with_suffix(".manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"{output}: {len(files)} files, {output.stat().st_size:,} bytes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=ROOT / "data/official/sample_submission"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "submissions/baseline.zip"
    )
    args = parser.parse_args()
    package(args.source.resolve(), args.output.resolve())
