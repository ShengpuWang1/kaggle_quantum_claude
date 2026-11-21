"""Test safe, static extraction of SomeJoint's embedded DQI source."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import extract_somejoint_dqi_source as extract


def make_notebook(path, sources):
    hashes = {
        name: hashlib.sha256(content.encode("utf-8")).hexdigest()
        for name, content in sources.items()
    }
    code = f"SOURCES = {sources!r}\nSOURCE_HASHES = {hashes!r}\n"
    path.write_text(
        json.dumps({"cells": [{"cell_type": "code", "source": [code]}]}),
        encoding="utf-8",
    )
    return hashes


def test_extracts_sources_without_executing_payload(tmp_path):
    marker = tmp_path / "executed"
    prefix = extract.SOURCE_PREFIX
    sources = {
        "LICENSE": "test license",
        prefix + "build.py": "# build\n",
        prefix + "payload.py": f"open({str(marker)!r}, 'w').write('bad')\n",
        "notebooks/do-not-extract.py": "raise RuntimeError\n",
    }
    notebook = tmp_path / "notebook.ipynb"
    make_notebook(notebook, sources)
    output = tmp_path / "source"

    report = extract.extract(notebook, output, expected_count=2)

    assert not marker.exists()
    assert (output / "build.py").read_text() == "# build\n"
    assert "open(" in (output / "payload.py").read_text()
    assert not (output / "notebooks").exists()
    assert (output / "LICENSE").read_text() == "test license"
    assert report["source_count"] == 2
    manifest = json.loads(output.with_name("source.manifest.json").read_text())
    assert manifest["files"]["payload.py"]["bytes"] > 0


def test_source_count_and_hash_mismatch_leave_no_output(tmp_path):
    prefix = extract.SOURCE_PREFIX
    notebook = tmp_path / "notebook.ipynb"
    sources = {"LICENSE": "license", prefix + "build.py": "print('safe')"}
    hashes = make_notebook(notebook, sources)
    output = tmp_path / "source"

    with pytest.raises(ValueError, match="Expected 2 DQI sources"):
        extract.extract(notebook, output, expected_count=2)
    assert not output.exists()

    notebook.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "cell_type": "code",
                        "source": [
                            f"SOURCES = {sources!r}\nSOURCE_HASHES = {hashes!r}\n".replace(
                                hashes[prefix + "build.py"], "0" * 64
                            )
                        ],
                    }
                ]
            }
        )
    )
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        extract.extract(notebook, output, expected_count=1)
    assert not output.exists()
    assert not output.with_name("source.manifest.json").exists()


@pytest.mark.parametrize("suffix", ["../escape.py", "bad//name.py", "bad\\name.py"])
def test_unsafe_selected_paths_are_rejected(tmp_path, suffix):
    notebook = tmp_path / "notebook.ipynb"
    make_notebook(
        notebook,
        {"LICENSE": "license", extract.SOURCE_PREFIX + suffix: "pass"},
    )
    with pytest.raises(ValueError, match="Unsafe source path"):
        extract.extract(notebook, tmp_path / "source", expected_count=1)


def test_existing_output_and_manifest_are_not_overwritten(tmp_path):
    notebook = tmp_path / "notebook.ipynb"
    make_notebook(
        notebook,
        {"LICENSE": "license", extract.SOURCE_PREFIX + "build.py": "pass"},
    )
    output = tmp_path / "source"
    output.mkdir()
    sentinel = output / "keep"
    sentinel.write_text("keep")
    with pytest.raises(FileExistsError):
        extract.extract(notebook, output, expected_count=1)
    assert sentinel.read_text() == "keep"

    sentinel.unlink()
    output.rmdir()
    manifest = output.with_name("source.manifest.json")
    manifest.write_text("keep manifest")
    with pytest.raises(FileExistsError):
        extract.extract(notebook, output, expected_count=1)
    assert not output.exists()
    assert manifest.read_text() == "keep manifest"
