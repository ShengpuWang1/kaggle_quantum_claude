# Piecewise-linear seed submission

This experiment replaces the cubic seed of `invsqrt` with a QROM-selected line,
then retains the official Newton-Raphson refinement, phase application, and
reversible cleanup. The candidate directory is `candidates/linear_seed_tuned/`.
All work is confined to this project. Official data, reference generators, and
verifiers are unchanged. The DQI and chemistry payloads are byte-for-byte copies
of the reference submission.

## Techniques identified in the papers

| Technique | Source | Project use and decision |
| --- | --- | --- |
| More table entries, lower polynomial degree | Gu et al., [arXiv:2610.22367](https://arxiv.org/abs/2610.22367), supplement III.2, printed pp. 18-19 | Implemented for `invsqrt`. The paper uses a finer table of lines for Coulomb evaluation. Its absolute-error target differs from this competition; our adaptation retains a Newton step for 24-bit relative accuracy. |
| Precision tailored to the actual fixed-point computation | Häner et al., [arXiv:1805.12445](https://arxiv.org/abs/1805.12445), and Gu et al., supplement III | Implemented via exhaustive integer-model evaluation and a bounded precision sweep. Every omitted partial product is represented explicitly in the model. |
| Temporary logical AND and measurement-based uncomputation | Gidney, [arXiv:1709.06648](https://arxiv.org/abs/1709.06648) | Used in the new QROM's unary iteration through kickmix `init_and`/`del_and`. The existing arithmetic already uses this technique; the new contribution is the seed architecture. |
| Berlekamp-Massey instead of synchronized Euclidean decoding; compute the phase directly | Gu et al., supplement I.1; benchmark background in [arXiv:2510.10967](https://arxiv.org/abs/2510.10967) | Promising larger follow-up for `dqi`. It requires a new reversible finite-field decoder, history cleanup, and phase construction. Not part of this submission. |
| SelectSwap data lookup with a gate/workspace trade-off | Low et al., [arXiv:1812.00954](https://arxiv.org/abs/1812.00954), section 2 | Relevant to chemistry QROM, but a straightforward extra 96-bit word bank does not fit alongside the baseline's registers under the 128-qubit ANGLE limit. It needs joint batching/workspace redesign. Not implemented here. |

## Implemented arithmetic

Normalize the positive 22-bit input to `M = x * 2^(2s) / 2^20` in `[1,4)`.
The top seven normalized bits select one of 128 table slots, 96 of which cover
the valid interval. Each valid interval has width `1/32`.

For interval `[a,a+h]`, fit the secant to `1/sqrt(M)` and shift its intercept
down by half the maximum secant error. Store the intercept and positive slope
as 17-bit fixed-point words. Evaluate the line by subtracting truncated
slope partial products controlled by local-coordinate bits 6 through 13.
The first interval has an additional small downward intercept bias: this
prevents the finite-precision Newton result at `M=1` from rounding above 2
and overflowing its one-integer-bit register.

The refinement computes `p = y0 * (3 - M*y0^2)` using the reference truncated
multiplication routines. The square and `M*y0^2` have 28 fractional bits; `p`
has 28 fractional bits. Denormalization and per-bit rotations then apply the
required inverse-square-root phase. Arithmetic is reversed, coefficients are
XOR-unloaded, and the input and all workspace are restored. Each temporary AND
measurement has its corresponding phase correction.

The XOR lookup is a total oracle, including its unused zero-filled addresses,
and works on arbitrary incoming output-register values. It is not specialized
to the verifier's target states or measurement outcomes. No seed grinding,
test-set exclusions, verifier changes, or relaxed tolerances are used.

## Deterministic model and focused tests

The exact integer model checks every allowed input `x=1..3,133,452`, including
intermediate overflow assertions. The selected configuration has maximum
relative error `3.155946537436449e-8` at `x=2,686,945`, or
`0.529479967430234` of the `2^-24` tolerance. The model itself is not a quantum
circuit verification; official simulator results are recorded separately.

The six tests in `tests/test_linear_invsqrt.py` cover:

- All 256 addresses of the larger QROM configuration, arbitrary target words,
  two measurement seeds, clean workspace, zero phase, and applying the oracle
  twice to restore the original targets.
- Exact agreement of the integer model and circuit phase for four configurations,
  including the selected one, on powers of two, table boundaries, small inputs,
  and random inputs. Input restoration and clean scratch are checked as well.

`ruff check` passes for the generator and tests. Precision-search results are
saved in `runs/linear_seed_precision_sweep.json` and
`runs/linear_seed_precision_sweep_refined.json`. These files retain accepted
configurations from the exploratory sweeps; they are not simulator certificates.

## Reproduce

```sh
source env.sh
python scripts/build_linear_invsqrt.py candidates/reproduced/invsqrt.kmb \
  --address-bits 5 --delta-bits 13 --result-bits 28
cp data/official/sample_submission/dqi.kmb candidates/reproduced/
cp -R data/official/sample_submission/dfthcsos candidates/reproduced/
python -m pytest -q tests/test_linear_invsqrt.py
python scripts/verify_submission.py --source candidates/reproduced --full --workers 1
python scripts/package_submission.py --source candidates/reproduced \
  --output submissions/linear_seed_reproduced.zip
```

The builder refuses to overwrite an existing circuit. Full verification can
take several minutes or longer; DQI uses substantial memory per worker.
`runs/linear_seed_tuned_full/run.json` records the exact commands and salts used
for the delivered candidate. `HANDOFF.md` gives equivalent per-task wrapper commands
using those salts. The runs use all official default input/shot counts.

## Scope of the results

The native kickmix build is pinned to the local Qualtran source described in the
project README. Local verification does not establish identical behavior to
Kaggle's Linux binary or replace the hosted metric. The candidate is packaged as
`submissions/linear_seed_tuned.zip` but has not been submitted. See `HANDOFF.md` for
current verification and archive evidence.
