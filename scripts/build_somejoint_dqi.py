"""Build the reviewed SomeJoint DQI source and enforce its published hash."""

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath

import kickmix as km

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SHA256 = "53d8b2edf251e2a0c54c401a97d1396c7ed309e1cbfaab8d54a2c99a11ed6552"


def sha256(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def validate_source_tree(source, manifest_path):
    source = Path(source).resolve()
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = manifest["files"]
    if manifest.get("source_count") != 79 or len(records) != 80:
        raise ValueError("Expected 79 source files plus LICENSE")
    for relative, record in records.items():
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or "\\" in relative:
            raise ValueError(f"Unsafe manifest path: {relative}")
        member = source / relative
        if member.is_symlink() or not member.is_file():
            raise ValueError(f"Missing or non-regular source file: {relative}")
        if member.stat().st_size != record["bytes"] or sha256(member) != record["sha256"]:
            raise ValueError(f"Reviewed source hash mismatch: {relative}")
    actual = {
        path.relative_to(source).as_posix()
        for path in source.rglob("*")
        if path.is_file()
    }
    if actual != set(records):
        raise ValueError(f"Source tree differs from manifest: {sorted(actual ^ set(records))}")
    if any(path.is_symlink() for path in source.rglob("*")):
        raise ValueError("Source tree contains a symlink")
    if "build.py" not in records:
        raise ValueError("Reviewed source is missing build.py")
    return manifest


def build(
    source,
    output,
    manifest_path,
    report_path,
    *,
    expected_sha256=EXPECTED_SHA256,
):
    source = Path(source).resolve()
    output = Path(output).resolve()
    report_path = Path(report_path).resolve()
    manifest_path = Path(manifest_path).resolve()
    validate_source_tree(source, manifest_path)
    build_record = output.with_suffix(".build.json")
    for path in (output, build_record, report_path):
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite {path}")
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-I", str(source / "build.py"), str(output)]
    start = time.monotonic()
    process = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    output_hash = sha256(output) if output.is_file() else None
    report = {
        "command": command,
        "cwd": str(ROOT),
        "returncode": process.returncode,
        "seconds": time.monotonic() - start,
        "stdout": process.stdout,
        "stderr": process.stderr,
        "source": str(source),
        "source_manifest": str(manifest_path),
        "source_manifest_sha256": sha256(manifest_path),
        "output": str(output),
        "output_sha256": output_hash,
        "expected_sha256": expected_sha256,
        "python": sys.version,
        "platform": platform.platform(),
        "kickmix_version": km.__version__,
    }
    with report_path.open("x", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    if process.returncode:
        raise RuntimeError(f"DQI build failed; see {report_path}")
    if output_hash != expected_sha256:
        raise ValueError(
            f"DQI SHA-256 mismatch: expected {expected_sha256}, got {output_hash}; "
            f"see {report_path}"
        )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = build(args.source, args.output, args.manifest, args.report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
