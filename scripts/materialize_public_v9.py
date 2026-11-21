"""Materialize busyaprime's hash-pinned v9 payload without executing it."""

import argparse
import hashlib
import json
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

ARCHIVE_SHA256 = "f25f2792a1b100228ca7786094e2d01f4aab95c42ed16b8ffe2d16414314b0b0"
EXPECTED = {
    "invsqrt.kmb": "9a8627c812833a6feca6eb82239f38d1a9a5e1eee299a9a7af9abd85e36339be",
    "dqi.kmb": "4ee7a17b4cbca4053a19bc951e7f2ef91fabdbb036006c9d658adcff4fe76da4",
    "dfthcsos/submission.npz": "f984ba30bfd9922bf941a5cece9360ad1302b9b01aa34877376abdd1fa39aabe",
    "dfthcsos/angle_k_0.kmb": "114a2acb164b6538af6fac7784d97ce4bca52cd59878b9ae597889f230888f71",
    "dfthcsos/angle_k_1.kmb": "a01248289fe2a488a39491455089b16bd41b8bff1e86b6dce6be5e85c5019385",
    "dfthcsos/angle_k_2.kmb": "b88a234ab24b00c657c4b3b5e8f3f680ac1e41208a64abad08ef4bf87f0d475e",
    "dfthcsos/angle_k_3.kmb": "abf0069e563e4797ed7e3b74d65f932aec131974009f80cb323ae5f5d754fb56",
    "dfthcsos/angle_k_4.kmb": "017d5072da349301a8c0ca5243ffd058528c38531e88728f6735b29f48a65eab",
    "dfthcsos/angle_k_5.kmb": "b4d36019132b43661850f984cf8eb723482cfb0af7eeb4cadb0964b6cc103e2a",
    "dfthcsos/angle_k_6.kmb": "d30c71fb6a288e946f688829f56b6c7026418337441e87a0a2bb5c7bb4fab794",
    "dfthcsos/angle_k_7.kmb": "dead802918d2183ecb2d3c96d6ea1df5ba7e5240d3a20cf63dbfc8fa146bb05f",
    "dfthcsos/angle_k_8.kmb": "ea2d9ab05bd9c61d8e4f2a21ba20c188e08b0db614c222aafa1af0d948f93f18",
    "dfthcsos/angle_k_9.kmb": "663497ad211daa8803a60e1cfff5d4e760499f971054c2908fe3a59489aa597c",
    "dfthcsos/angle_k_10.kmb": "708409dc540b0726438b94854f959a2b6641de6b1aa9b0840beaffe3862f6ba2",
    "dfthcsos/angle_k_11.kmb": "78c041703bbc43f795ae4ab9224a15e2a6dc97d60c76cf9927226de6c959a466",
    "dfthcsos/angle_k_12.kmb": "8375a66c80b83e4a4ac697112769fbba126d6f58fc58e7591aba01fb864bd269",
    "dfthcsos/angle_k_13.kmb": "fbdac0002c7cd3e66487f966ccac1edf2ac40f628fb7d22af048c1ce66f60219",
    "dfthcsos/angle_k_14.kmb": "be4bd2e0e6f63e5c37a232aec0b2a30fd693b4e928605f1d4ade6f4263ffa39c",
}
PROVENANCE = ("LICENSE", "NOTICE.md")


def sha256(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def archive_name(submission_name):
    path = PurePosixPath(submission_name)
    if len(path.parts) == 1:
        return submission_name
    if path.parts[0] == "dfthcsos" and len(path.parts) == 2:
        return f"dfthcsos__{path.parts[1]}"
    raise ValueError(f"Unexpected payload path: {submission_name}")


def validate_member(info):
    path = PurePosixPath(info.filename)
    if path.is_absolute() or ".." in path.parts or "\\" in info.filename:
        raise ValueError(f"Unsafe archive member: {info.filename}")
    if info.flag_bits & 1:
        raise ValueError(f"Encrypted archive member: {info.filename}")
    mode = info.external_attr >> 16
    file_type = stat.S_IFMT(mode)
    if info.is_dir() or file_type not in {0, stat.S_IFREG}:
        raise ValueError(f"Non-regular archive member: {info.filename}")


def materialize(
    archive,
    output,
    *,
    skip_dqi=False,
    expected=None,
    expected_archive_sha256=ARCHIVE_SHA256,
):
    archive = Path(archive).resolve()
    output = Path(output).resolve()
    expected = EXPECTED if expected is None else expected
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    actual_archive_sha256 = sha256(archive)
    if actual_archive_sha256 != expected_archive_sha256:
        raise ValueError(
            f"Archive SHA-256 mismatch: expected {expected_archive_sha256}, "
            f"got {actual_archive_sha256}"
        )
    selected = {
        name: digest
        for name, digest in expected.items()
        if not (skip_dqi and name == "dqi.kmb")
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=output.parent))
    records = {}
    try:
        with zipfile.ZipFile(archive) as source:
            infos = source.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise ValueError("Archive contains duplicate members")
            by_name = {info.filename: info for info in infos}
            for info in infos:
                validate_member(info)
            for name in (*selected, *PROVENANCE):
                member = name if name in PROVENANCE else archive_name(name)
                if member not in by_name:
                    if name in PROVENANCE:
                        continue
                    raise KeyError(f"Missing archive member: {member}")
                info = by_name[member]
                destination = temporary / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                size = 0
                with source.open(info) as src, destination.open("xb") as dst:
                    while chunk := src.read(1024 * 1024):
                        digest.update(chunk)
                        size += len(chunk)
                        dst.write(chunk)
                actual = digest.hexdigest()
                if name in selected and actual != selected[name]:
                    raise ValueError(f"SHA-256 mismatch for {member}: {actual}")
                records[name] = {"bytes": size, "sha256": actual}
                if name in PROVENANCE:
                    records[name]["provenance"] = True
        temporary.rename(output)
    except BaseException:
        shutil.rmtree(temporary)
        raise
    return {
        "archive": str(archive),
        "archive_sha256": actual_archive_sha256,
        "output": str(output),
        "files": records,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--skip-dqi", action="store_true")
    args = parser.parse_args()
    report = materialize(args.archive, args.output, skip_dqi=args.skip_dqi)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
