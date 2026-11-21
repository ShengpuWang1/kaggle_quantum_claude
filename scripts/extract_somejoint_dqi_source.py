"""Statically extract SomeJoint's hash-checked DQI source without executing it."""

import argparse
import ast
import hashlib
import json
import shutil
import tempfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PREFIX = "blocks/dqi/team-1028-stream/source/"
EXPECTED_SOURCE_COUNT = 79
MAX_FILE_BYTES = 200_000
MAX_TOTAL_BYTES = 2_000_000


def sha256(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def notebook_literals(notebook_path):
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    values = {}
    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        tree = ast.parse("".join(cell.get("source", [])))
        for node in tree.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if not isinstance(target, ast.Name) or target.id not in {
                "SOURCES",
                "SOURCE_HASHES",
            }:
                continue
            if target.id in values:
                raise ValueError(f"Duplicate notebook assignment: {target.id}")
            values[target.id] = ast.literal_eval(node.value)
    if set(values) != {"SOURCES", "SOURCE_HASHES"}:
        raise ValueError("Notebook must contain literal SOURCES and SOURCE_HASHES")
    if not isinstance(values["SOURCES"], dict) or not isinstance(
        values["SOURCE_HASHES"], dict
    ):
        raise TypeError("SOURCES and SOURCE_HASHES must be dictionaries")
    return values["SOURCES"], values["SOURCE_HASHES"]


def output_name(source_name):
    if "\\" in source_name or not source_name.startswith(SOURCE_PREFIX):
        raise ValueError(f"Unsafe source path: {source_name!r}")
    relative = source_name[len(SOURCE_PREFIX) :]
    parts = relative.split("/")
    if not relative or any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"Unsafe source path: {source_name!r}")
    path = PurePosixPath(relative)
    if path.is_absolute():
        raise ValueError(f"Unsafe source path: {source_name!r}")
    return relative


def select_sources(sources, source_hashes, expected_count=EXPECTED_SOURCE_COUNT):
    selected = {
        name: content for name, content in sources.items() if name.startswith(SOURCE_PREFIX)
    }
    if len(selected) != expected_count:
        raise ValueError(f"Expected {expected_count} DQI sources, found {len(selected)}")
    if "LICENSE" not in sources:
        raise ValueError("Notebook is missing LICENSE")
    selected["LICENSE"] = sources["LICENSE"]
    records = {}
    total_bytes = 0
    for name, content in selected.items():
        relative = "LICENSE" if name == "LICENSE" else output_name(name)
        if relative in records:
            raise ValueError(f"Duplicate output path: {relative}")
        if not isinstance(content, str) or not isinstance(source_hashes.get(name), str):
            raise TypeError(f"Source and hash must be strings: {name}")
        data = content.encode("utf-8")
        digest = hashlib.sha256(data).hexdigest()
        if digest != source_hashes[name]:
            raise ValueError(f"Source SHA-256 mismatch for {name}")
        size = len(data)
        if size > MAX_FILE_BYTES:
            raise ValueError(f"Source exceeds per-file size limit: {name}")
        total_bytes += size
        records[relative] = {"bytes": size, "sha256": digest, "text": content}
    if total_bytes > MAX_TOTAL_BYTES:
        raise ValueError("Selected sources exceed total size limit")
    return records


def extract(notebook_path, output, manifest_path=None, expected_count=EXPECTED_SOURCE_COUNT):
    notebook_path = Path(notebook_path).resolve()
    output = Path(output).resolve()
    manifest_path = (
        Path(manifest_path).resolve()
        if manifest_path
        else output.with_name(output.name + ".manifest.json")
    )
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    if manifest_path.exists():
        raise FileExistsError(f"Refusing to overwrite {manifest_path}")
    if manifest_path == output or output in manifest_path.parents:
        raise ValueError("Manifest must be outside the output directory")
    sources, source_hashes = notebook_literals(notebook_path)
    records = select_sources(sources, source_hashes, expected_count)
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=output.parent))
    completed = False
    try:
        for relative, record in records.items():
            destination = temporary / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("x", encoding="utf-8", newline="") as f:
                f.write(record["text"])
        files = {
            name: {"bytes": record["bytes"], "sha256": record["sha256"]}
            for name, record in sorted(records.items())
        }
        report = {
            "notebook": str(notebook_path),
            "notebook_sha256": sha256(notebook_path),
            "source_prefix": SOURCE_PREFIX,
            "source_count": len(files) - 1,
            "files": files,
        }
        temporary.rename(output)
        with manifest_path.open("x", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
            f.write("\n")
        completed = True
        return report
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
        if not completed and output.exists():
            shutil.rmtree(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("notebook", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    report = extract(args.notebook, args.output, args.manifest)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
