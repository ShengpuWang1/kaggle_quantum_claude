# Public baseline reproduction and exact lookup optimization

Date: 2026-10-28

## Result

The strongest published artifact identified in this research was reproduced and
verified locally, but **no candidate strictly better than that artifact was found**.
No improved submission archive was produced. At the user's subsequent request, the
exact reproduction was packaged as `submissions/published_busyaprime_reproduction.zip`;
that archive is not an improvement. Nothing was submitted to Kaggle.

Source and attribution:

- busyaprime, [LB 22.33981 — 22x cheaper than Google's circuits](https://www.kaggle.com/code/busyaprime/lb-22-33981-22x-cheaper-than-google-s-circuits), Apache-2.0.
- The notebook credits mrmeows for the surrounding 63-qubit invsqrt circuit,
  SomeJoint for DQI, and heliosli for chemistry.
- The exact public ZIP is retained in `research/public_artifacts/busyaprime_v8/`.
  `scripts/materialize_public_baseline.py` extracted only the 18 required payload
  members, checked every SHA-256, and refused to execute notebook code.

The materialized directory is `candidates/public_busyaprime_v8/`. Its complete
hash record is `runs/public_baseline/materialization.json`.

## Reproduced official costs

All three tasks passed the official verifiers at full defaults:

| Task | Official raw cost (lower is better) | Evidence |
| --- | ---: | --- |
| invsqrt | **102,664.23041910287** | `runs/20261028T061906591624Z/invsqrt.json` |
| DQI | **422,346,115,188.9339** | `runs/20261028T060246970070Z/dqi.json` |
| chemistry | **349,339,717.3328993** | `runs/20261028T060046123902Z/dfthcsos.json` |

The invsqrt run used 200,540,928 shots, 63 qubits, and salt
`public-baseline-validation-2026-10-28`. Its worst error/tolerance ratio was
0.9993237694056958 at `x=161`. The circuit SHA-256 is
`07314803a0925970cf45007ebbdb8a146378c242e3991c70d6f7509af3d583da`.
DQI and chemistry certificates apply only to the unchanged, hash-checked public
members. The reported 22.33981 leaderboard result is not a locally reproduced
hosted score.

## Exact lookup model

`scripts/analyze_public_invsqrt.py` decodes the KMB through Kickmix and simulates
every Boolean wire over all 256 addresses using 256-bit integers. The main lookup
is KMX interval `262:16681`, with address wires `q14:q21` and a 40-wire pool.
It contains 172 AND operations in 67 stages:

- 32 one-AND stages constructing shared nonlinear functions;
- 35 four-AND output stages.

The recovered boundaries, targets, and affine-basis dimensions are in
`runs/public_lookup/structure.json`. A late output stage has a 48-dimensional
affine basis including the constant function. Measurement/reset (`HMR`) is modeled
as resetting the measured wire, not as an assertion that its prior value was zero.

`scripts/optimize_public_invsqrt_lookup.py` asks for an exact representation

```text
y = a1*b1 XOR a2*b2 XOR a3*b3 XOR linear_form
```

for a four-product stage. Affine control constants are normalized into the free
linear remainder. The CNF encoder includes control-swap and product-permutation
symmetry breaking. A separate nondegenerate mode excludes constant/repeated
controls and controls shared between products, since any such case reduces to
fewer products. Known four-product decompositions were used as assumption-based
sanity checks and returned SAT with zero conflicts.

## Searches and negative results

A result of `unknown` below means the conflict budget was exhausted. It is not an
UNSAT proof and is not evidence that no representation exists.

| Search | Coverage/result | Evidence |
| --- | --- | --- |
| Affine-only replacement | No stage among all 67 is affine in its incoming wire basis | Exact basis reduction |
| Individual-wire products, three-product meet-in-the-middle | No replacement in any of 35 output stages | `runs/public_lookup/simple_all_blocks.log` |
| Control forms of weight up to two | No replacement in any output stage; 55.48 s | `runs/public_lookup/weight_two_all_blocks.log` |
| One-bit affine neighborhoods of existing products | No replacement in any output stage; 39.23 s | `runs/public_lookup/neighborhood_all_blocks.log` |
| Exact SAT, multiple backends and encodings | Blocks 32, 33, 65, and 66 remained `unknown` at conflict budgets up to five million | `runs/public_lookup/block*_3and*.json` |
| Last-computed output basis | No low-weight replacement for any output when all other outputs were made available; block 32 exact SAT remained `unknown` | `runs/public_lookup/last_basis_weight_two_all.log`, `block32_last_basis_sat.json` |
| Direct product sharing | All 140 existing output products were distinct | Exact 256-address product hashes |
| Cross-output shared-product residual search | No low-weight decomposition among 2,380 ordered earlier-product/later-stage cases | `runs/public_lookup/shared_product_simple.log` |
| Alternate split-ANF/rank-pairing construction | Table-exact plan counts were 289 ANDs without sharing and 284 with sharing, worse than 172 | `runs/public_lookup/anf_current_basis*.json`; `scripts/search_public_invsqrt_anf.py` |

The split-ANF experiment independently follows the construction published in
SomeJoint's Apache-2.0 chemistry notebook. Every generated plan was checked on all
256 addresses. It is related to, but not equivalent to, busyaprime's more general
affine-control network.

A chemistry subsearch tried random orthogonal gauges and coordinate variants but
produced no valid material improvement. This was exploratory, not an optimality
proof. The earlier identity-start gauge improvement of about 8.1 cost units out of
349 million remains too small to justify a submission and was not packaged.

## Checks and next route

The new focused tests cover materialization hashes and cleanup, affine-basis
operations, CNF symmetry constraints, product normalization, and a planted truth-
table defect. The complete suite passes: **47 tests**. Ruff passes on all new
research scripts and tests.

A genuine improvement still requires fewer than 172 lookup ANDs (or another exact
cost reduction), exhaustive region equivalence, and an official invsqrt cost below
102,664.23041910287. The most defensible next route is global multi-output XAG
synthesis or a complete (not conflict-limited) exact solve with a stronger
multiplicative-complexity encoding. Until one succeeds,
`candidates/public_busyaprime_v8/` is the best verified artifact, not a new
submission that beats the public notebooks.
