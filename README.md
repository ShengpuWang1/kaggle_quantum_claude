# Verifiable Quantum Circuit Compilation research workspace

Competition: https://www.kaggle.com/competitions/google-verifiable-quantum-circuit-compilation

## Current best

**Start with [`HANDOFF.md`](HANDOFF.md)** for current status, verification evidence,
reproduction commands, and next research priorities.

The active candidate is **`candidates/busyaprime_v9_somejoint_897q/`**, packaged locally
as **`submissions/busyaprime_v9_somejoint_897q.zip`**. It combines busyaprime v9's
pinned invsqrt and chemistry artifacts with a locally rebuilt SomeJoint 897-qubit DQI
circuit. All three tasks passed full official-default verification and improved on the
previous public v8 portfolio:

| Task | v8 cost | Current verified cost | Reduction |
| --- | ---: | ---: | ---: |
| invsqrt | 102,664.23041910287 | **102,349.2360480486** | 0.3068% |
| DQI | 422,346,115,188.9339 | **412,943,252,615.63153** | 2.2263% |
| Chemistry | 349,339,717.3328993 | **341,880,855.4426008** | 2.1351% |

The local reference-normalized geometric mean is **22.75798**, versus **22.40295** for
v8. These are raw task costs and a local cost-ratio calculation, not a measured
leaderboard score. The exact 18-member ZIP and all member hashes were independently
validated against the source materialization and build records.

No archive has been submitted to Kaggle, and the hosted metric has not been run. The
experiment and its evidence are documented in
[`docs/research/public_v9_somejoint_portfolio.md`](docs/research/public_v9_somejoint_portfolio.md).
The previous public v8 and independent quadratic candidates and packages remain intact.

### Historical baseline

`submissions/baseline.zip` is the unmodified official reference submission. Keep it
for comparison; it is not the optimized candidate. The official data page says this
reference scores **1.0**, which is an expected baseline rather than a result measured
from this workspace. `notebooks/00_baseline.ipynb` and `runs/baseline/` are also
historical baseline records.

## Environment

From this folder, in zsh or bash:

```sh
source env.sh
python --version
python -c 'import kickmix; print(kickmix.__version__)'
python -m jupyterlab
```

Python 3.12.15 and a dedicated `.venv` live inside this directory. Installed tools
include NumPy, SciPy, pandas, Matplotlib, SymPy, NetworkX, JupyterLab, IPython,
Kaggle CLI, pytest and Ruff. `env.sh` directs common caches, Jupyter state,
temporary files and optional Kaggle configuration into this folder. No global
Python environment or shell startup file was changed. Always source `env.sh` after
opening a new shell; it explicitly selects this workspace's interpreter even though
the copied virtual environment contains older launcher paths. Prefer `python -m ...`
for pytest, Ruff, and Jupyter entry points.

kickmix is built natively for macOS arm64 from Google's Qualtran commit
`638777fac4379bc62e2a1e4a52cf1a1753895d48`. The competition-provided `kickmix.so`
is a Linux binary; do not add `data/official/kickmix` to the local Python path.
The source build passes all **3,403 upstream Python tests**. Its exact equivalence
to Kaggle's supplied binary has not been established.

Resolved package versions are in `requirements.lock.txt`; direct dependencies are
listed in `requirements.in`. With the downloaded source retained, reinstall using:

```sh
source env.sh
uv pip install --python .venv/bin/python -r requirements.lock.txt
```

The lock is a snapshot for this Mac, not a cross-platform lock. Building kickmix
requires a C++20 compiler (the installed Apple command-line toolchain was used).

## Files

| Path | Purpose |
| --- | --- |
| `data/raw/` | Original Kaggle ZIP |
| `data/official/` | All 34 official files, including circuits, verifiers, FCIDUMP and paper |
| `candidates/busyaprime_v9_somejoint_897q/` | Current complete, locally verified candidate |
| `candidates/public_busyaprime_v8/` | Previous best public portfolio |
| `candidates/quadratic_direct_a7_c27_r27_complete/` | Best independently built candidate |
| `docs/competition/` | Saved overview/data page text and source provenance |
| `docs/papers/2610.23832.pdf` | Companion research paper downloaded from arXiv |
| `vendor/Qualtran/kickmix/` | Pinned native simulator source |
| `vendor/Qualtran/docs/kickmix/` | Python API, gates, conventions and binary/text format documentation |
| `scripts/` | Circuit generation, packaging, and verification commands |
| `notebooks/` | Historical baseline notebook |
| `runs/` | Verifier outputs and checks |
| `submissions/` | Upload ZIPs and per-file SHA-256 manifests |

Keep `data/official/` unchanged. Create experimental candidates separately, copying
the required baseline files into a candidate directory before modifying circuits.
Large datasets, environments, vendor source and ZIPs are excluded by `.gitignore`.
An original browser download also remains in Downloads; it was copied here and
the external copy was left untouched.

## Verify and package experiments

```sh
source env.sh
python scripts/verify_submission.py
python scripts/verify_submission.py --full
python scripts/verify_submission.py --source candidates/linear_seed --task invsqrt
python scripts/verify_submission.py --task dqi --full --workers 1 --salt my-validation-seed
python scripts/package_submission.py --source candidates/my-experiment --output submissions/my-experiment.zip
```

The default verification is a smoke check: invsqrt uses inputs 1–4,096 with 64
shots each, DQI uses 4,096 shots, and chemistry uses the full official defaults.
`--full` keeps the official input/shot counts for all three tasks. Full scoring can
take tens of minutes. DQI uses several GB of RAM per worker; one worker is the
local default. All verifier scripts are unmodified originals. Task-selective runs
require only the selected task's files. `--salt` is forwarded to the selected official
verifier(s). Run records preserve the command, time, exit status, JSON output and
stderr in a new `runs/` directory.

Packaging checks required files, consecutive ANGLE numbering, required NPZ keys,
finite numeric values and ZIP integrity. It verifies every archived member's bytes
against the source. These checks do **not** replace circuit verification or the
Kaggle metric's preflight checks. A manifest beside each ZIP records SHA-256 hashes.
Existing ZIPs are not overwritten.

Initial local validation, in `runs/baseline/`:

- invsqrt: PASS, 262,144 shots over inputs 1–4,096 (partial domain).
- DQI: PASS, 4,096 shots, zero value or phase errors (reduced shot count).
- dfthcsos: PASS, 254,464 verified shots with full default settings.
- A preliminary DQI run with 1,024 shots found zero errors but failed its confidence
  bound; that diagnostic is retained as `dqi-smoke.json`. The corrected check is
  `dqi-smoke-4096.json`.

The task JSON `score` values are resource costs, **not** the final leaderboard
score. Kaggle combines baseline-to-candidate cost ratios by a geometric mean.
Reduced-shot DQI changes its confidence bound and cost, so do not use the smoke
result to estimate a leaderboard score. Local seeds use the verifier defaults;
Kaggle uses its own salt. Full official-default verification of all three current
portfolio tasks is recorded in `runs/20261029T032923204702Z/`,
`runs/20261029T033742262025Z/`, and `runs/20261029T032916049207Z/`. See `HANDOFF.md`
for earlier candidates and the complete evidence map. An end-to-end Kaggle metric run
has not been performed.

## Official references

- [Evaluation and submission contract](https://www.kaggle.com/competitions/google-verifiable-quantum-circuit-compilation/overview/evaluation)
- [Data and authoritative verifiers](https://www.kaggle.com/competitions/google-verifiable-quantum-circuit-compilation/data)
- [Full Kaggle metric, version 10 observed](https://www.kaggle.com/code/metric/google-quantum-ai-metric)
- [Optional chemistry training starter kit](https://www.kaggle.com/datasets/sohier/verifiable-circuit-compilation-starter-kit)
- [Companion paper](https://arxiv.org/abs/2610.23832)
- [Official kickmix source](https://github.com/quantumlib/Qualtran/tree/638777fac4379bc62e2a1e4a52cf1a1753895d48/kickmix)

The separate chemistry training starter kit and full metric notebook are linked
but not downloaded; all competition data and all three standalone verifiers are
available locally. No Kaggle API credentials were created or stored. Browser login
was used to obtain the competition archive after enrollment was already complete.
