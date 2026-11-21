"""Test hash-pinned v9 materialization with small synthetic archives."""

import hashlib
import stat
import sys
import warnings
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import materialize_public_v9 as materializer


def make_archive(tmp_path, *, duplicate=False, symlink=False, unsafe=False):
    archive = tmp_path / "archive.zip"
    contents = {
        name: f"payload:{name}".encode() for name in materializer.EXPECTED
    }
    expected = {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(archive, "w") as z:
            for name, data in contents.items():
                member = materializer.archive_name(name)
                if symlink and name == "invsqrt.kmb":
                    info = zipfile.ZipInfo(member)
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    z.writestr(info, data)
                else:
                    z.writestr(member, data)
                if duplicate and name == "invsqrt.kmb":
                    z.writestr(member, data)
            z.writestr("LICENSE", "license")
            z.writestr("NOTICE.md", "notice")
            if unsafe:
                z.writestr("../escape", "do not write")
    return archive, expected


def run(archive, output, expected, **kwargs):
    return materializer.materialize(
        archive,
        output,
        expected=expected,
        expected_archive_sha256=materializer.sha256(archive),
        **kwargs,
    )


def test_materialize_all_and_skip_dqi(tmp_path):
    archive, expected = make_archive(tmp_path)
    full = run(archive, tmp_path / "full", expected)
    assert len(full["files"]) == 20
    assert (tmp_path / "full/dqi.kmb").is_file()
    assert (tmp_path / "full/dfthcsos/submission.npz").is_file()
    assert full["files"]["LICENSE"]["provenance"]

    partial = run(archive, tmp_path / "partial", expected, skip_dqi=True)
    assert len(partial["files"]) == 19
    assert not (tmp_path / "partial/dqi.kmb").exists()
    assert (tmp_path / "partial/invsqrt.kmb").read_bytes() == b"payload:invsqrt.kmb"


def test_outer_and_member_hash_mismatch_clean_up(tmp_path):
    archive, expected = make_archive(tmp_path)
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="Archive SHA-256 mismatch"):
        materializer.materialize(
            archive, output, expected=expected, expected_archive_sha256="0" * 64
        )
    assert not output.exists()

    expected["invsqrt.kmb"] = "0" * 64
    with pytest.raises(ValueError, match="SHA-256 mismatch for invsqrt.kmb"):
        run(archive, output, expected)
    assert not output.exists()
    assert not list(tmp_path.glob(".output.tmp-*"))


def test_duplicate_symlink_and_traversal_members_are_rejected(tmp_path):
    for index, options in enumerate(
        ({"duplicate": True}, {"symlink": True}, {"unsafe": True})
    ):
        directory = tmp_path / str(index)
        directory.mkdir()
        archive, expected = make_archive(directory, **options)
        with pytest.raises(ValueError):
            run(archive, directory / "output", expected)
        assert not (directory / "output").exists()
    assert not (tmp_path / "escape").exists()


def test_existing_output_is_never_overwritten(tmp_path):
    archive, expected = make_archive(tmp_path)
    output = tmp_path / "output"
    output.mkdir()
    sentinel = output / "keep"
    sentinel.write_text("unchanged")
    with pytest.raises(FileExistsError):
        run(archive, output, expected)
    assert sentinel.read_text() == "unchanged"
