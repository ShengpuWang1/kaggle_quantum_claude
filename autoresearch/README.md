# Deterministic auto-research

This package automates champion–challenger circuit research while keeping verification and promotion outside the LLMs' control. It supports independent Anthropic-compatible and OpenAI-compatible API configuration for three fresh-context roles:

- **Director:** inspects a published competition notebook or research paper, then proposes one evidence-based experiment. Paper PDFs are downloaded to `docs/papers/` during this design phase.
- **Implementer:** modifies an isolated, task-only workspace through confined file tools.
- **Reviewer:** independently reviews the implementation in a read-only fresh context.

The Python orchestrator alone changes lifecycle state, executes configured build/test commands, invokes official verifiers, compares full costs, and promotes champions. Agents cannot self-certify a result, run the verifier, or submit to Kaggle.

## Setup

From the project root:

```sh
source env.sh
python scripts/orchestrate.py doctor
python scripts/orchestrate.py init
```

`init` imports the official sample artifacts as per-task baseline champions. It checks official provenance, artifact hashes, existing full local `PASS` records, and pinned costs. It does not rerun full verification.

Edit `autoresearch/config.yaml`. This local file is ignored by Git; `config.example.yaml` is the reference copy. Each role has independent settings:

```yaml
agents:
  director:
    provider: anthropic
    base_url: https://your-provider.example
    api_key_env: AUTORESEARCH_DIRECTOR_API_KEY
    model: your-model-name
    effort: high
    max_tokens: 16000
    max_turns: 24
    timeout_seconds: 600
    max_retries: 2
    options: {}
```

Set `provider: openai` for an OpenAI Chat Completions-compatible endpoint, normally with a base URL ending in `/v1`. Anthropic roles use the official Messages SDK, adaptive thinking, optional `output_config.effort`, and streaming by default. OpenAI roles use `reasoning_effort`. Third-party endpoints vary in supported fields; `options` adds provider-specific request fields, but cannot replace the model, messages, tools, system prompt, or API key.

For Volcengine Ark Agent Plan's Anthropic-compatible route, use `provider: anthropic`, `base_url: https://ark.cn-beijing.volces.com/api/plan`, `auth_token_env: YOUR_KEY_VARIABLE`, and `model: ark-code-latest` (or a model enabled by your plan). Do not use the separate `/api/plan/v3` OpenAI Responses route with this orchestrator's Chat Completions adapter.

Prefer environment variables over literal keys. Copy the needed assignments from `autoresearch/.env.example` into `.secrets/autoresearch.env`; `source env.sh` exports that optional file without printing it. A literal `api_key` is also supported in the ignored local YAML. Anthropic-compatible endpoints that require `Authorization: Bearer` can use `auth_token_env` instead of `api_key_env` (or literal `auth_token`); configure only one authentication method per role. Public configuration snapshots redact secret values.

`doctor` is offline: it checks imports, key presence, official files, and champion presence without making provider requests. A `run` or `loop` makes paid API calls once real providers and keys are configured.

## Commands

```sh
# One experiment; exit status 1 means rejected rather than promoted.
python scripts/orchestrate.py run

# A sequential batch of independent experiments.
python scripts/orchestrate.py loop --experiments 5

# Resume an interrupted, nonterminal experiment.
python scripts/orchestrate.py resume EXP-YYYYMMDDTHHMMSSZ-xxxxxx

python scripts/orchestrate.py status
python scripts/orchestrate.py show EXP-YYYYMMDDTHHMMSSZ-xxxxxx

# Verify a current champion, or an explicit task-only source directory.
python scripts/orchestrate.py verify --task invsqrt
python scripts/orchestrate.py verify --task invsqrt --full
python scripts/orchestrate.py verify --task dqi --source /path/to/task-only --workers 1

# Package all three current champions locally; never uploads.
python scripts/orchestrate.py package-portfolio --output submissions/research-portfolio.zip
```

Use an alternate YAML with the global option, for example `python scripts/orchestrate.py --config /path/to/config.yaml doctor`.

## Experiment lifecycle

1. Before making a concrete plan, the director selects and inspects a published notebook from the competition's score-sorted listing or a relevant research paper. Paper-based plans require a PDF downloaded to `docs/papers/`. The structured plan records the source URL, local paper path where applicable, and derived insight; the orchestrator rejects citations that were not fetched or papers that were not downloaded.
2. The orchestrator snapshots the selected task champion into a new workspace and records its parent ID and hashes.
3. The implementer writes source and generator files.
4. The orchestrator runs configured build/test argument arrays without a shell.
5. The official task verifier runs in smoke mode. Chemistry already uses its full defaults; invsqrt and DQI use reduced counts.
6. A fresh reviewer approves or requests revisions.
7. Build, smoke, or review failures can trigger bounded repair cycles. `settings.max_repair_cycles: 2` means the initial attempt plus at most two repairs.
8. An approved candidate receives one terminal full official verification with a private local salt.
9. Only a full `PASS` with finite positive cost strictly below the unchanged parent champion can promote. Candidate bytes are hash-checked again before and after copying.
10. A full failure, stale parent, changed artifact, or unimproved cost rejects the experiment. Full-verifier details are never fed into a same-salt repair loop.

If the process is interrupted during planning, implementation, checks, smoke, or review, `resume` uses persisted checkpoints. Completed role calls are not repeated. An interrupted full verification is deliberately not auto-resumed; inspect its run directory and metadata first. Terminal `promoted`, `rejected`, and `failed` experiments are archival records, not new repair sessions.

## Build contract

The default recipe for every task is:

```yaml
tasks:
  invsqrt:
    build: ["{python}", "source/build.py"]
    tests: []
```

Commands are argument arrays, not shell strings. `{python}` expands to the current project interpreter and `{workspace}` to the isolated workspace. The working directory is that workspace. A build must deterministically produce:

- `invsqrt.kmb` or `invsqrt.kmx` at the workspace root;
- `dqi.kmb` or `dqi.kmx` at the workspace root; or
- `dfthcsos/submission.npz` and contiguous `angle_k_0.*`, `angle_k_1.*`, … circuits.

Tests are a list of argument arrays, for example `tests: [["{python}", "source/test.py"]]`. Execution stops at the first nonzero exit or timeout. Logs and redacted command records are stored with the experiment. Agent-authored build code runs with the local user's permissions, so only run trusted configurations and review generated source as appropriate.

A zero build exit status alone is not a successful candidate. Before smoke verification, the orchestrator validates the required task artifacts with the same exact-path, nonempty-file checks used for promotion. Missing, ambiguous, empty, symlinked, or otherwise invalid outputs enter the bounded repair/rejection path without invoking the official verifier. Ordinary rejected experiments allow `loop` to continue; unexpected exceptions remain fail-fast.

Agents have dedicated list/read/search tools, and only the implementer has write/edit tools. Writes are confined to the experiment workspace; secret, environment, cache, and Git-internal paths are blocked. There is no agent shell tool. The director additionally has public research-search/fetch tools restricted to Kaggle, arXiv and selected paper hosts. Those requests carry no API credentials. Public `/code/<owner>/<slug>` notebook URLs are retrieved through Kaggle's unauthenticated notebook API, and `competitionDataSources` must contain the exact competition slug; app-shell HTML and notebook prose are not accepted as proof of competition membership. After two failed Kaggle source fetches, the director session blocks further Kaggle fetches and requires the arXiv paper workflow. `download_paper` is the only exception to read-only director storage: it validates PDF content and writes a new, non-overwriting file below `docs/papers/`. Downloaded notebooks, HTML, PDFs, and embedded source text are treated as untrusted evidence and are never executed.

Failed tool events include a bounded diagnostic summary with URLs and configured credential values removed. Successful research content and tool arguments are not copied into events.

## State and storage

```text
autoresearch/
├── config.yaml                 # local editable role and recipe configuration
├── research/                   # durable roadmap, decisions, and outcome log
├── experiments/EXP-.../        # small plans, events, metrics, reviews, and verifier logs
├── workspaces/EXP-.../         # mutable task-only candidate and generator source
└── champions/<task>/
    ├── current.json            # atomically replaced champion pointer record
    └── generations/<id>/       # immutable artifacts and reproducible source snapshot
```

Only the selected task is copied into an experiment, so invsqrt/chemistry experiments do not duplicate the roughly 886 MB DQI artifact. Workspaces and champion generation artifacts are Git-ignored. Old experiments are retained as negative or positive evidence; storage cleanup is a manual operation, not part of a running experiment.

## Verification salts and scoring

Orchestrated full verification generates a cryptographically random salt per experiment, stores it with mode `0600` below `.secrets/autoresearch/salts/`, and passes it through an environment variable only to the verifier wrapper. Commands, metadata, agent prompts, events, and research logs do not contain the salt. Run records retain its SHA-256 fingerprint; raw verifier output is redacted if it echoes the salt.

Standalone `scripts/autoresearch_verifier.py` also supports `--salt-env NAME`, `--run-dir`, `--timeout-seconds`, and `--fail-fast`. The manual `orchestrate.py verify --full` command uses official defaults unless `--salt-env` is explicitly supplied.

Task JSON `score` fields are costs, not leaderboard scores. The portfolio estimate is:

```text
(invsqrt_reference / invsqrt_cost
 * dqi_reference / dqi_cost
 * chemistry_reference / chemistry_cost) ** (1/3)
```

Only full costs enter comparison and portfolio estimates. Smoke costs never do. References are pinned local full-verifier results in `reference_costs.json`, not measured hosted results. Kaggle's private salt can change randomized outcomes and costs, especially DQI's certified failure bound and repetition factor. Local macOS kickmix equivalence with Kaggle's Linux binary is also unproven. Treat every local portfolio number as an estimate.

Portfolio packaging reuses `scripts/package_submission.py`, validates required artifact structure and ZIP integrity, and records champion provenance. It never calls Kaggle or uploads anything.

## Offline development checks

```sh
python -m pytest -q tests/test_autoresearch.py tests/test_autoresearch_orchestrator.py tests/test_research_tools.py
python -m ruff check autoresearch/*.py scripts/orchestrate.py scripts/autoresearch_verifier.py
```

Tests use fake scripted providers, mocked SDK responses, tiny temporary artifacts, and fake verifier executables. They require no API keys, network access, paid calls, or full DQI verification. The fake end-to-end test really executes its temporary generator and proves that full—not smoke—cost controls promotion.
