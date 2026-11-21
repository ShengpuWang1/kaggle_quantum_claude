# Direct piecewise-quadratic inverse square root

This experiment replaces both the piecewise-linear seed and Newton refinement in
`invsqrt` with a direct piecewise-quadratic approximation. The selected circuit is
`candidates/quadratic_direct_a7_c27_r27/invsqrt.kmb`; the complete candidate also
contains byte-identical DQI and chemistry payloads. Official data, the original
linear generator, the tuned candidate, and existing archives are unchanged.
Nothing has been submitted to Kaggle.

## Paper basis

The arithmetic follows Gu et al.,
[arXiv:2610.22367](https://arxiv.org/abs/2610.22367), supplement III.1,
Eqs. 63–64, using the in-place Horner form

```text
q(d) = c0 - d * (c1 - c2*d).
```

The implementation adapts that idea to `2/sqrt(M)` on the official normalized
domain `M in [1,4)`. This preserves the existing output representation,
denormalization, phase rotations, and reversible cleanup while eliminating all
three Newton multiplications. The precision truncation and exhaustive fixed-point
validation follow the approach discussed by Häner et al.,
[arXiv:1805.12445](https://arxiv.org/abs/1805.12445). The QROM reuses the temporary
logical-AND and measurement-based uncomputation implementation developed for the
linear candidate, based on Gidney, [arXiv:1709.06648](https://arxiv.org/abs/1709.06648).

## Implemented arithmetic

Normalize the positive 22-bit input to `M` in `[1,4)`. The top seven normalized
bits select an interval of width `h=2^-7`. For each interval, three Chebyshev
nodes determine a quadratic interpolant. A dense residual-centering step shifts
its constant coefficient, then all coefficients are rounded to integers.

The circuit loads `[p,c1,c2]` with the XOR QROM. It evaluates the inner Horner
update on `c1`, then the outer update on `p`, using truncated partial products
controlled by the remaining normalized-input bits. The inverse runs in the
opposite order: outer update, inner update, then QROM unload. This ordering is
necessary to restore every coefficient and scratch bit.

The selected precision is:

| Parameter | Value |
| --- | ---: |
| `address_bits` | 7 |
| `delta_bits` | 20 |
| `coef_bits` | 27 |
| `result_bits` | 27 |
| Stored widths `[p,c1,c2]` | `[28,20,14]` |

The coefficient widths exploit the bounds used in the paper: `c1 < h` and
`c2 < 1.5*h^2`. The first constant coefficient is clamped below two so the
one-integer-bit output register cannot overflow at `M=1`.

## Deterministic model and candidate selection

`fixed_point_model` models every truncated integer update exactly and asserts
intermediate positivity and output bounds. `check_domain` exhaustively evaluates
every allowed input `x=1..3,133,452`. The selected model's maximum relative error
is `5.3253367715555555e-08` at `x=2,764,799`, or `0.8934432528913021` of the
`2^-24` tolerance.

The precision sweep in `runs/quadratic_development/precision_sweep.json` compares
actual in-memory circuit resources for 27 configurations. Exact 64-bit phase
margins and official rotation-cost estimates are recorded in
`runs/quadratic_development/exact_score_estimates.json`:

| Candidate | Qubits | Toffoli-like | Worst error / tolerance | Estimated official cost |
| --- | ---: | ---: | ---: | ---: |
| `a7_c27_r27` | 158 | 3,272 | 0.893443 | 556,400.41 |
| `a6_c27_r28` | 164 | 3,180 | 0.844042 | 562,617.77 |
| `a7_c28_r28` | 163 | 3,396 | 0.471206 | 593,586.74 |
| `linear_seed_tuned` | 222 | 6,068 | 0.529480 | 1,401,695.95 (official full) |

The aggressive candidate was selected because its exact rotation-adjusted
estimate is lowest while retaining positive error and rotation-synthesis margins.
Estimates are not simulator certificates.

## Tests and official verification

The six tests in `tests/test_quadratic_invsqrt.py` cover exhaustive default-model
error and coefficient bounds; arbitrary QROM target words, clean workspace, zero
phase, and two measurement seeds; and exact circuit/model phase agreement for
three precision configurations on powers of two, interval boundaries, small
inputs, worst-error points, and random inputs. They also check input restoration
and clean scratch. The complete project suite passes with **26 tests**, and Ruff
passes. Logs are in `runs/quadratic_development/`.

Both leading candidates passed official invsqrt smoke verification:

- `a7_c27_r27`: `runs/20261028T034616787540Z/invsqrt.json`.
- `a6_c27_r28`: `runs/20261028T034600824521Z/invsqrt.json`.

The selected candidate **passed full official-default invsqrt verification** in
`runs/20261028T034655133415Z/`. Its command used two workers and salt
`quadratic-a7-c27-r27-validation-2026-10-28`. The run covered **200,540,928 shots**
and reported:

- Score **556,400.4091072511**, strictly below the tuned score
  **1,401,695.9536623457** by **60.3052%**.
- Toffoli-equivalent cost **3,521.5215766281717**, including rotation synthesis.
- Worst error **0.8934432525547626** of tolerance at `x=2,764,799`.
- Circuit SHA-256
  `0b6d303d29cbc5af95a546a4c268c0d95c8c730b970a1b2838316b90b1da8635`.

The complete candidate is packaged as `submissions/quadratic_direct.zip`, with
ZIP SHA-256 `2f7a9acc093c0e454196b91a17511a4da4ee0b44e6dbaf8655f11200ebedb8af`.
Independent archive validation passed for all 13 members, the certified invsqrt
hash, and every unchanged payload hash; see
`runs/quadratic_development/archive_validation.json`.

## Reproduce

```sh
source env.sh
python scripts/build_quadratic_invsqrt.py candidates/reproduced_quadratic/invsqrt.kmb \
  --address-bits 7 --delta-bits 20 --coef-bits 27 --result-bits 27
cp data/official/sample_submission/dqi.kmb candidates/reproduced_quadratic/
cp -R data/official/sample_submission/dfthcsos candidates/reproduced_quadratic/
python -m pytest -q -p no:cacheprovider tests
python scripts/verify_submission.py \
  --source candidates/reproduced_quadratic --task invsqrt --full --workers 2 \
  --salt quadratic-a7-c27-r27-validation-2026-10-28
python scripts/package_submission.py --source candidates/reproduced_quadratic \
  --output submissions/quadratic_direct_reproduced.zip
```

The builder and packager refuse to overwrite existing outputs. DQI and chemistry
verification records from `runs/linear_seed_tuned_full/` apply only because all
12 corresponding payload files were independently hash-checked as byte-identical.
The native macOS kickmix build's equivalence to Kaggle's Linux binary remains
unproven, and no hosted metric run or Kaggle submission has been performed.
