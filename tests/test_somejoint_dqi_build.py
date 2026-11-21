"""Test the reviewed-source DQI build launcher with a small fixture."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_somejoint_dqi as builder


def make_source(root, build_text):
    root.mkdir()
    files = {"build.py": build_text, "LICENSE": "fixture license"}
    files.update({f"module_{i}.py": f"# {i}\n" for i in range(78)})
    records = {}
    for name, text in files.items():
        path = root / name
        path.write_text(text)
        data = path.read_bytes()
        records[name] = {
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    manifest = root.parent / "source.manifest.json"
    manifest.write_text(json.dumps({"source_count": 79, "files": records}))
    return manifest


def test_build_runs_isolated_and_checks_output_hash(tmp_path):
    source = tmp_path / "source"
    manifest = make_source(
        source,
        "import pathlib,sys\npathlib.Path(sys.argv[1]).write_bytes(b'circuit')\n",
    )
    output = tmp_path / "dqi.kmb"
    expected = hashlib.sha256(b"circuit").hexdigest()

    report = builder.build(
        source,
        output,
        manifest,
        tmp_path / "build.json",
        expected_sha256=expected,
    )

    assert output.read_bytes() == b"circuit"
    assert report["command"][1] == "-I"
    assert report["returncode"] == 0
    assert report["output_sha256"] == expected


def test_hash_mismatch_is_reported(tmp_path):
    source = tmp_path / "source"
    manifest = make_source(
        source,
        "import pathlib,sys\npathlib.Path(sys.argv[1]).write_bytes(b'wrong')\n",
    )
    report_path = tmp_path / "build.json"
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        builder.build(
            source,
            tmp_path / "dqi.kmb",
            manifest,
            report_path,
            expected_sha256="0" * 64,
        )
    assert json.loads(report_path.read_text())["returncode"] == 0


def test_modified_source_is_rejected_before_execution(tmp_path):
    marker = tmp_path / "executed"
    source = tmp_path / "source"
    manifest = make_source(
        source,
        f"import pathlib\npathlib.Path({str(marker)!r}).write_text('bad')\n",
    )
    (source / "module_0.py").write_text("modified")
    with pytest.raises(ValueError, match="source hash mismatch"):
        builder.build(
            source,
            tmp_path / "dqi.kmb",
            manifest,
            tmp_path / "build.json",
            expected_sha256="0" * 64,
        )
    assert not marker.exists()
