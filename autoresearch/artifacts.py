"""Content-hashed task artifacts and safe copying."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path

from .config import TASKS


class ArtifactError(ValueError):
    """Raised when candidate artifacts are absent, ambiguous, or changed."""


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def candidate_files(root: Path, task: str) -> list[Path]:
    if task not in TASKS:
        raise ArtifactError(f"Unknown task: {task}")
    if task in {"invsqrt", "dqi"}:
        matches = [root / f"{task}.{extension}" for extension in ("kmb", "kmx")]
        matches = [path for path in matches if path.is_file()]
        if len(matches) != 1:
            raise ArtifactError(f"Expected exactly one {task} circuit below {root}")
        files = matches
    else:
        directory = root / "dfthcsos"
        if not directory.is_dir():
            raise ArtifactError(f"Missing {directory}")
        angles = sorted(directory.glob("angle_k_*"))
        indices = []
        for path in angles:
            match = re.fullmatch(r"angle_k_(\d+)\.(kmb|kmx)", path.name)
            if not match or not path.is_file():
                raise ArtifactError(f"Unexpected ANGLE entry: {path}")
            indices.append(int(match[1]))
        if not indices or sorted(indices) != list(range(len(indices))):
            raise ArtifactError("ANGLE indices must start at zero without gaps")
        factorization = directory / "submission.npz"
        if not factorization.is_file():
            raise ArtifactError(f"Missing {factorization}")
        files = [*angles, factorization]
    for path in files:
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            raise ArtifactError(f"Invalid candidate file: {path}")
        path.resolve().relative_to(root.resolve())
    return sorted(files)


def manifest(root: Path, task: str) -> dict:
    files = []
    for path in candidate_files(root, task):
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    result = {"task": task, "files": files}
    result["digest"] = digest_manifest(result)
    return result


def digest_manifest(value: dict) -> str:
    content = {"task": value["task"], "files": value["files"]}
    serialized = json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(serialized).hexdigest()


def verify_manifest(root: Path, expected: dict) -> None:
    actual = manifest(root, expected["task"])
    if actual["digest"] != expected["digest"]:
        raise ArtifactError(
            f"Candidate manifest changed: expected {expected['digest']}, got {actual['digest']}"
        )


def copy_task(source: Path, task: str, destination: Path) -> None:
    files = candidate_files(source, task)
    for path in files:
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError(f"Refusing to overwrite {target}")
        shutil.copy2(path, target)


def remove_task(root: Path, task: str) -> None:
    for path in candidate_files(root, task):
        path.unlink()
    if task == "dfthcsos":
        directory = root / "dfthcsos"
        if directory.exists() and not any(directory.iterdir()):
            directory.rmdir()


def tree_manifest(root: Path) -> dict:
    files = []
    if not root.exists():
        return {"files": [], "digest": hashlib.sha256(b"[]").hexdigest()}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ArtifactError(f"Source symlinks are not allowed: {path}")
        if path.is_file():
            files.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
    serialized = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return {"files": files, "digest": hashlib.sha256(serialized).hexdigest()}
