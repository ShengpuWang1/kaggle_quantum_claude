# Agent handoff

Last cleaned and checked: **2026-10-29**. This directory is not a Git repository.

## Start here

- Competition: [Google Verifiable Quantum Circuit Compilation](https://www.kaggle.com/competitions/google-verifiable-quantum-circuit-compilation).
- Best verified artifact: `candidates/busyaprime_v9_somejoint_897q/`, combining
  busyaprime v9 invsqrt/chemistry with a locally rebuilt SomeJoint 897-qubit DQI circuit.
- Current package: `submissions/busyaprime_v9_somejoint_897q.zip`, with exactly 18
  independently hash-validated payload members.
- Best independently built candidate: `candidates/quadratic_direct_a7_c27_r27_complete/`.
- Previous public artifact: `candidates/public_busyaprime_v8/`; its reproduction package
  is `submissions/published_busyaprime_reproduction.zip`.
- Packaged independent archive: `submissions/best_independent_quadratic_direct.zip`
  (byte-identical to `submissions/quadratic_direct.zip`).
- Current portfolio research and evidence: `docs/research/public_v9_somejoint_portfolio.md`.
- Earlier public-baseline research: `docs/research/public_lookup_optimization.md`.
- Independent design and research rationale: `docs/research/quadratic_direct_submission.md`.
- Environment and general commands: `README.md`.

The current official local costs are invsqrt **102,349.2360480486**, DQI
**412,943,252,615.63153**, and chemistry **341,880,855.4426008**. All three improve on
v8 by 0.3068%, 2.2263%, and 2.1351%, respectively. The reference-normalized local
geometric mean is **22.757983370388523**, versus **22.40294717461127** for v8. These
are local cost calculations, not a hosted score.

The previous v8 costs were invsqrt 102,664.23041910287, DQI 422,346,115,188.9339,
and chemistry 349,339,717.3328993. Exact SAT, affine-neighborhood, output-reordering,
and product-sharing searches did not produce a lower-cost v8 lookup. The baseline is
retained for research and comparison.

The independent quadratic candidate uses a direct piecewise-quadratic QROM approximation
for invsqrt, eliminating the linear seed and all three Newton multiplications. It remains
the best independently designed circuit but is no longer the active portfolio.

**Nothing has been submitted to Kaggle. No hosted-metric result is available.**
Local resource costs are not leaderboard scores.

## Working rules

1. Always run `source env.sh` from the workspace root. It selects this folder's
   interpreter explicitly; the copied virtual environment has older launcher paths.
   Prefer `python -m pytest`, `python -m ruff`, and `python -m jupyterlab` over the
   corresponding generated launcher scripts.
2. Keep `data/official/` and `vendor/Qualtran/` unchanged. The generator intentionally
   uses private functions from the pinned official invsqrt reference.
3. Build experiments in new candidate directories. The builder and packager refuse to
   overwrite existing outputs. Copy the required DQI and chemistry payloads into each
   complete candidate.
4. Use official verifiers for circuit certificates. Packaging checks file structure,
   NPZ contents, and ZIP integrity only.
5. DQI needs several GB per worker; default to `--workers 1`. Full verification can
   take tens of minutes. Chemistry uses full defaults even during wrapper smoke runs.
6. Do not submit archives or create Kaggle credentials automatically.

## Current evidence

Current v9 + SomeJoint portfolio certificates:

| Check | Result | Evidence |
| --- | --- | --- |
| Invsqrt, official full defaults | PASS; cost 102,349.2360480486; 200,540,928 shots; 63 qubits | `runs/20261029T032923204702Z/invsqrt.json` |
| DQI, official full defaults | PASS; cost 412,943,252,615.63153; 102,400 shots; zero value/phase errors; 897 qubits | `runs/20261029T033742262025Z/dqi.json` |
| Chemistry, official full defaults | PASS; cost 341,880,855.4426008; 78,080 shots; 430 total qubits | `runs/20261029T032916049207Z/dfthcsos.json` |
| SomeJoint source build | Raw and canonical DQI SHA-256 match the published pin; 897 qubits; 103,536 bits | `runs/public_v9_somejoint_897q/dqi_build.json`, `runs/public_v9_somejoint_897q/dqi_structure.json` |
| Current package | Exact 18-member set; all bytes and hashes independently match materialization/build records | `runs/public_v9_somejoint_897q/archive_validation.json` |
| Complete unit/circuit tests and Ruff | 63 passed; all lint checks passed | Final run on 2026-10-29 |

Current ZIP SHA-256:
`c5b861f296c3090bc193000996545aea03e52938fc6c9d282665cedbaf4d56f5`.
Manifest: `submissions/busyaprime_v9_somejoint_897q.manifest.json`.

Previous public v8 certificates:

| Check | Result | Evidence |
| --- | --- | --- |
| Public invsqrt, official full defaults | PASS; cost 102,664.23041910287; 63 qubits | `runs/20261028T061906591624Z/invsqrt.json` |
| Public DQI, official full defaults | PASS; cost 422,346,115,188.9339; zero value/phase errors | `runs/20261028T060246970070Z/dqi.json` |
| Public chemistry, official full defaults | PASS; cost 349,339,717.3328993 | `runs/20261028T060046123902Z/dfthcsos.json` |
| Public payload materialization | All 18 member hashes match | `runs/public_baseline/materialization.json` |
| Lookup optimization | No qualifying improvement; reproduction packaged separately by user request | `docs/research/public_lookup_optimization.md` |
| Requested archives | Both ZIPs and every member hash independently validated | `submissions/published_busyaprime_reproduction.manifest.json`, `submissions/best_independent_quadratic_direct.manifest.json` |
| Complete unit/circuit tests after lookup research | 47 passed | `tests/test_public_lookup_optimizer.py` and existing suite |

Independent-candidate certificates:

The packaged quadratic invsqrt hash matches its full official certificate. DQI and
chemistry were not rerun for the new directory; all 12 payload files were
independently verified byte-identical to the certified tuned candidate.

| Check | Result | Evidence |
| --- | --- | --- |
| Quadratic invsqrt, official full defaults | PASS; 200,540,928 shots; cost 556,400.41; 158 qubits; 3,272 Toffoli-like gates | `runs/20261028T034655133415Z/invsqrt.json` |
| Tuned invsqrt, official full defaults | PASS; 200,540,928 shots; cost 1,401,695.95; 222 qubits | `runs/linear_seed_tuned_full/invsqrt.json` |
| DQI, official full defaults | PASS; 102,400 shots; zero value/phase errors; unchanged payload | `runs/linear_seed_tuned_full/dqi.json` |
| Chemistry, full defaults | PASS; 254,464 shots; unchanged payload | `runs/linear_seed_tuned_full/dfthcsos.json` |
| Reference invsqrt, official full defaults | PASS; cost 2,076,774.23; 260 qubits | `runs/reference_full/invsqrt.json` |
| Complete unit/circuit tests | 26 passed | `runs/quadratic_development/pytest_all.log` |
| Ruff check | PASS | `runs/quadratic_development/ruff_candidates.log` |
| Leading quadratic smoke tests | Both PASS; 262,144 shots each | `runs/20261028T034616787540Z/`, `runs/20261028T034600824521Z/` |
| Optimized archive integrity and independent hash validation | PASS; 13 payload files; certified invsqrt and unchanged payload hashes match | `runs/quadratic_development/package.log`, `runs/quadratic_development/archive_validation.json` |
| Kaggle submission and hosted metric | Not performed | No submission evidence exists |

The quadratic raw invsqrt task cost is **60.3% below** the tuned linear candidate
and **73.2% below** the reference. With DQI and chemistry unchanged, this is an
optimization of one task, not a measured overall leaderboard improvement.

Package identifiers:

- ZIP SHA-256: `2f7a9acc093c0e454196b91a17511a4da4ee0b44e6dbaf8655f11200ebedb8af`
- invsqrt SHA-256: `0b6d303d29cbc5af95a546a4c268c0d95c8c730b970a1b2838316b90b1da8635`
- Manifest: `submissions/quadratic_direct.manifest.json`
- Previous tuned package: `submissions/linear_seed_tuned.zip`, SHA-256
  `e676230cc9bfd88ed996920f31bad8b600dc334b870b405f2bd67105d329f09e`

Local native kickmix passes its upstream tests (`runs/kickmix-tests.log`, 3,403
passed), but equivalence to Kaggle's Linux binary is unproven. Final hosted validation
is still required.

## Reproduce the current portfolio

From the workspace root, using a new output directory and archive name:

```sh
source env.sh
python -I scripts/materialize_public_v9.py \
  research/public_artifacts/busyaprime_v9_363327369/members/archive.zip \
  candidates/reproduced_v9_somejoint --skip-dqi
python -I scripts/extract_somejoint_dqi_source.py \
  research/public_artifacts/somejoint_363324999/notebook/notebook.ipynb \
  candidates/reproduced_v9_somejoint/source/dqi \
  --manifest candidates/reproduced_v9_somejoint/source/dqi.manifest.json
python -I scripts/build_somejoint_dqi.py \
  candidates/reproduced_v9_somejoint/source/dqi \
  candidates/reproduced_v9_somejoint/dqi.kmb \
  --manifest candidates/reproduced_v9_somejoint/source/dqi.manifest.json \
  --report candidates/reproduced_v9_somejoint/source/dqi.build.json
python -I scripts/inspect_dqi_circuit.py candidates/reproduced_v9_somejoint/dqi.kmb
python scripts/verify_submission.py --source candidates/reproduced_v9_somejoint \
  --task invsqrt --full --workers 2
python scripts/verify_submission.py --source candidates/reproduced_v9_somejoint \
  --task dqi --full --workers 1
python scripts/verify_submission.py --source candidates/reproduced_v9_somejoint \
  --task dfthcsos --full
python scripts/package_submission.py --source candidates/reproduced_v9_somejoint \
  --output submissions/reproduced_v9_somejoint.zip
```

The build launcher is restricted to the reviewed SomeJoint version 363324999 source tree
and its expected output hash. The materializer, extractor, and launcher all refuse to
overwrite existing outputs. The delivered build and verification commands, hashes, and
results are retained in the records listed above.

## Reproduce the best independent candidate

From the workspace root:

```sh
source env.sh
python scripts/build_quadratic_invsqrt.py candidates/reproduced_quadratic/invsqrt.kmb \
  --address-bits 7 --delta-bits 20 --coef-bits 27 --result-bits 27
cp data/official/sample_submission/dqi.kmb candidates/reproduced_quadratic/
cp -R data/official/sample_submission/dfthcsos candidates/reproduced_quadratic/
python -m pytest -q -p no:cacheprovider tests
python scripts/verify_submission.py --source candidates/reproduced_quadratic \
  --task invsqrt --full --workers 2 --salt quadratic-a7-c27-r27-validation-2026-10-28
python scripts/verify_submission.py --source candidates/reproduced_quadratic \
  --task dqi --full --workers 1 --salt submission-validation-2026-10-28
python scripts/verify_submission.py --source candidates/reproduced_quadratic \
  --task dfthcsos --full --salt submission-validation-2026-10-28
python scripts/package_submission.py --source candidates/reproduced_quadratic \
  --output submissions/quadratic_direct_reproduced.zip
```

The delivered quadratic invsqrt command, salt, timing, and result are preserved in
`runs/20261028T034655133415Z/`. Only that task was rerun for the new candidate; the
DQI and chemistry commands above reproduce their earlier checks if desired.
`runs/linear_seed_tuned_full/run.json` preserves the previous candidate's commands,
salts, and hashes. Omitting `--salt` preserves verifier defaults. Do not overwrite
the current candidate or archive during reproduction.

For a faster invsqrt-only workflow check:

```sh
python scripts/verify_submission.py \
  --source candidates/quadratic_direct_a7_c27_r27 --task invsqrt
```

## Artifact map

- **Current best verified artifact:** `candidates/busyaprime_v9_somejoint_897q/`,
  `submissions/busyaprime_v9_somejoint_897q*`, `runs/public_v9_somejoint_897q/`, and
  the three 2026-10-29 verifier directories listed above.
- **Previous public artifact:** `candidates/public_busyaprime_v8/`,
  `runs/public_baseline/`, `runs/public_lookup/`, and the three 2026-10-28 public
  verifier directories listed above.
- **Active independent candidate:** `candidates/quadratic_direct_a7_c27_r27_complete/`,
  `runs/20261028T034655133415Z/`, `submissions/quadratic_direct*`, and
  `scripts/build_quadratic_invsqrt.py`.
- **Previous optimized:** `candidates/linear_seed_tuned/`,
  `runs/linear_seed_tuned_full/`, `submissions/linear_seed_tuned*`, and
  `scripts/build_linear_invsqrt.py`. The original generator remains unchanged.
- **Research experiments:** `runs/quadratic_development/`,
  `runs/linear_v2_development/`, `scripts/sweep_quadratic_invsqrt.py`, and the other
  `candidates/quadratic_direct*` and `candidates/linear_seed_v2_safe/` directories.
  The un-suffixed `quadratic_direct_a7_r28` build retained a documented dirty-scratch
  smoke failure; `_v2` fixed the inverse-operation order. These are not current-best
  artifacts.
- **Reference:** `data/official/`, `runs/reference_full/`, `submissions/baseline*`.
- **Historical experiments:** `candidates/linear_seed/`, `runs/linear_seed_full/`,
  `runs/linear_seed_precision_sweep*.json`, and timestamped run directories not
  identified as active or current evidence above. The precision-sweep generation
  script was not retained; the JSON files are results, not simulator certificates.
- **Historical baseline:** `runs/baseline/`, `notebooks/00_baseline.ipynb`. The retained
  1,024-shot DQI diagnostic failed its confidence bound; the 4,096-shot smoke check
  passed. This was not a circuit correctness failure.
- **Cleanup checks:** `runs/cleanup/` and `runs/20261028T023139627153Z/`.

Some historical manifests and run records contain the former workspace path
`/Users/spwang/Documents/Quant/kaggle_quantum`. These are provenance records; do not
rewrite them. New records created through the repaired environment use the current
workspace path.

## Next research priorities

1. **Invsqrt:** pursue global multi-output XAG synthesis or a complete exact solve
   with a stronger multiplicative-complexity encoding. The bounded searches in
   `docs/research/public_lookup_optimization.md` found no 171-AND replacement;
   conflict-limited `unknown` results are not impossibility proofs.
2. **DQI:** build on the verified SomeJoint 897-qubit circuit by reducing decoder
   workspace, streamed-fusion Toffolis, or replay-erasure cost. Qubit reductions have
   quadratic impact on cost; do not replace the current pinned artifact without a full
   official PASS and a lower measured cost.
3. **Chemistry:** investigate SelectSwap/QROM and joint batching/workspace redesign.
   A straightforward extra 96-bit word bank does not fit the ANGLE qubit limit.
   Random gauge exploration produced no material improvement.
4. **Validation:** after any candidate change, run the focused tests and official
   task verifier, then full verification and packaging before considering submission.

See `docs/papers/README.md` for the research reading list. Do not treat the historical
baseline notebook as the current experiment status.
