# Public v9 + SomeJoint DQI portfolio

Date: 2026-10-29

## Goal and sources

This experiment applies newly published techniques to the previous best verified
artifact, `candidates/public_busyaprime_v8/`. The new candidate is
`candidates/busyaprime_v9_somejoint_897q/`; existing candidates and submissions are
unchanged.

- **busyaprime**, notebook version **363327369**, [LB 22.72431](https://www.kaggle.com/code/busyaprime/lb-22-33981-22x-cheaper-than-google-s-circuits).
  Raw notebook SHA-256: `fe44313f959c6a8c44d9993df3e8ac3e4bb284f081d8b101e4e900f1234907a2`.
  The selected files come directly from the public
  [`busyaprime/33-qcc-v8-members`](https://www.kaggle.com/datasets/busyaprime/33-qcc-v8-members)
  archive, SHA-256 `f25f2792a1b100228ca7786094e2d01f4aab95c42ed16b8ffe2d16414314b0b0`.
  All 17 non-DQI payload hashes match the notebook's pins. The archive's Apache-2.0
  license and NOTICE are retained in the candidate.
- **SomeJoint**, notebook version **363324999**, [22.75 Local GM: 897-Qubit DQI](https://www.kaggle.com/code/somejoint/quantum-circuits-22-75-local-gm-897-qubit-dqi).
  Raw notebook SHA-256: `a76a5693ab5a2d5379bfc2b6933dda2b95980ee592dac28282502fc6df436d9f`.
  The statically extracted 79 DQI source files and Apache-2.0 LICENSE match the
  notebook's `SOURCE_HASHES`. The expected rebuilt DQI SHA-256 is
  `53d8b2edf251e2a0c54c401a97d1396c7ed309e1cbfaab8d54a2c99a11ed6552`.

## Published techniques being applied

The v9 invsqrt rebuild reduces window S1 from 30 to 25 AND operations, following
its earlier main-lookup reduction. Its chemistry members use 4,188 angle-loader
Toffolis per pass and refitted factorization weights.

SomeJoint's DQI generator implements four measured optimizations:

1. aligned conversion with last-two-word pivots and virtual shifted products;
2. streamed full-head fusion with monic-root alias correction;
3. exact small truncated products (2×2 and 3×2);
4. replay erasure while both operands remain live.

The intended portfolio keeps v9 invsqrt/chemistry and rebuilds SomeJoint's 897-qubit,
lower-Toffoli DQI circuit from the reviewed source. No complete prebuilt replacement
portfolio is substituted.

## Safety and reproducibility tooling

- `scripts/materialize_public_v9.py`: outer/member hash gates, fixed member mapping,
  safe regular-file extraction, duplicate rejection, atomic no-overwrite output.
- `scripts/extract_somejoint_dqi_source.py`: JSON/AST literal parsing only, 79-file
  source-set enforcement, notebook hash verification, safe paths, atomic extraction.
- `scripts/build_somejoint_dqi.py`: reviewed-tree hash validation, isolated `python -I`
  build, no-overwrite outputs, build receipt, mandatory published DQI hash.
- `scripts/inspect_dqi_circuit.py`: raw/canonical hashes, registers, qubits/bits,
  operation statistics, and interface validation.

The complete test suite passes: **63 tests**. Ruff passes on all new scripts/tests.
The source audit found no network, subprocess, or unexpected dynamic-loading behavior;
the documented build/import mechanism is the only dynamic loader.

## Build, verification, and packaging results

The user explicitly authorized execution of SomeJoint notebook version 363324999's
reviewed `build.py`; that authorization was not extended to other downloaded code.
The isolated build completed in 34.234 seconds. Its output and a canonical Kickmix
round trip both have SHA-256
`53d8b2edf251e2a0c54c401a97d1396c7ed309e1cbfaab8d54a2c99a11ed6552`.
Structural inspection confirms 897 qubits, 103,536 classical bits, 4,165 registers,
59,852,041 operations, and 444,667 static Toffoli-like gates. Evidence:
`runs/public_v9_somejoint_897q/dqi_build.json` and
`runs/public_v9_somejoint_897q/dqi_structure.json`.

All three tasks passed their full official verifiers with default settings:

| Task | v8 cost | New verified cost | Reduction | Evidence |
| --- | ---: | ---: | ---: | --- |
| invsqrt | 102,664.23041910287 | **102,349.2360480486** | **0.3068%** | `runs/20261029T032923204702Z/invsqrt.json` |
| DQI | 422,346,115,188.9339 | **412,943,252,615.63153** | **2.2263%** | `runs/20261029T033742262025Z/dqi.json` |
| Chemistry | 349,339,717.3328993 | **341,880,855.4426008** | **2.1351%** | `runs/20261029T032916049207Z/dfthcsos.json` |

The invsqrt run used 200,540,928 verified shots; its circuit has 63 qubits and a mean
Toffoli count of 1,329.5002244928278. DQI used 102,400 shots with zero value and phase
errors, 897 qubits, and mean Toffolis 430,822.879765625. Chemistry used 78,080 shots,
430 total qubits, 16,306 Toffolis, and `lambda_eff` 48.759460127760185.

Using the official reference costs, the local three-task geometric-mean projection is
**22.757983370388523**, versus **22.40294717461127** for v8: a **1.5848%**
improvement. These are local cost-ratio calculations, not a hosted Kaggle score.

Final quality checks passed: **63 tests** and Ruff. The candidate was packaged as
`submissions/busyaprime_v9_somejoint_897q.zip` with exactly 18 payload members.
Independent archive validation passed against the v9 materialization and SomeJoint
build records; the ZIP SHA-256 is
`c5b861f296c3090bc193000996545aea03e52938fc6c9d282665cedbaf4d56f5`.
Evidence: `submissions/busyaprime_v9_somejoint_897q.manifest.json` and
`runs/public_v9_somejoint_897q/archive_validation.json`. Nothing has been submitted
to Kaggle.
