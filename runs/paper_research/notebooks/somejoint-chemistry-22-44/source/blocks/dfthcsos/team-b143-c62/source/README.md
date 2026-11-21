# Our team's chemistry submission, B143 C62: build source

`build.py OUTPUT` writes the 15 angle circuits `OUTPUT/angle_k_K.kmb` and copies `OUTPUT/submission.npz` in about two seconds, with Kickmix importable and the official verifier's `dfthcsos` package beside it (`data/comp/verifiers`).

- `exp/loader_port/{compiler,emitter,loader,low3,partition,partition3,planning}.py` and `playbook/exp/staged_b154/{beam,coded_helpers,emitter,paired_anf,retention,rm_code,scheduler,template_snapshot,validation_helpers}.py`: the research team's loader compiler and circuit emitter, unchanged from its snapshot `50f3328` of 28 October 2026, 03:47 UTC (folder `/home/jo/research/qcc/dfthcsos-1027`), in the same layout. These sixteen files are every module the build imports from the team's code; a replay with the team's folder hidden builds every circuit byte for byte.
- `data/BUILD.json`: the team's frozen build record `submission/BUILD.json` (the same file as `exp/b143_tangent/BUILD.json`): each circuit's plan, schedule, Toffolis, qubits and SHA-256.
- `data/submission.npz`: the team's `submission/submission.npz` (SHA-256 `f80b6561…`) without its `batch` record (5, int64), which the verifier does not read and its digest does not cover; the metric is known to accept integer arrays only under a few names (`tree_edges`, `angle_words`, `brot`, `kept_indices`), and `batch` is not one of them. Every other array is unchanged, written with a fixed timestamp. Not in Git: it is in the dataset below.
- `build.py`: written by Claude (Opus 5.5) after the team's `exp/full_build/build.py --replay`. Every circuit must have its recorded SHA-256, the circuits must load exactly the submitted words, and the submission must have its digest `377c0080…`.

`data/submission.npz` and `data/BUILD.json` are also published, byte for byte, as the Kaggle dataset `somejoint/qcc-our-chemistry-b143-c62`. Kaggle refuses a notebook source of 1 MB or more, so the notebook takes these two files from that dataset by SHA-256 instead of embedding them.

`source_sha256.json` pins every file but this README.
