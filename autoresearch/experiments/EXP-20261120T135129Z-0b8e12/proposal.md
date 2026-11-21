# Measurement-implication guard for one invsqrt CCX

**Task:** `invsqrt`

## Hypothesis

The 62-qubit champion contains at least one unconditional CCX in a bounded phase-free window following an unconditional `HMR t b`, such that exhaustive Boolean evaluation proves `control_a AND control_b => b` for every arbitrary assignment of the other active boundary wires, with t initialized to zero and b independent. Adding `if b` to exactly that CCX preserves all values and phases on both measurement branches but skips executions when b=0. Because the official metric charges executed rather than static Toffoli-like gates, this should reduce mean Toffoli count without changing qubit count, rotations, or the inverse-square-root approximation. The hypothesis is falsified if no certified, non-vacuous site is found or if the full measured cost does not strictly decrease.

## Expected resource effect

The static gate count remains 1537, but every skipped parent execution of the selected CCX reduces mean `toffoli_count` by its frequency per shot. With Q fixed at 62 and the T/rotation stream unchanged, a measured reduction of d executed CCX per shot lowers score by approximately 62*d. An HMR outcome is expected to make some unconditional executions eligible for skipping, but no numerical improvement is assumed; full-verifier measurement decides the result.

## Research evidence

- **Relaxed Peephole Optimization: A Novel Compiler Optimization for Quantum Circuits** (paper): https://arxiv.org/abs/2012.07711
  - Liu, Bello, and Zhou's relaxed peephole optimization uses statically determined qubit-state information for strength reduction, replacing operations with cheaper equivalents even when the optimization is not an unrestricted-unitary identity. The adapted mechanism is to use a known post-HMR wire state and its classical outcome to prove that a later CCX cannot fire on one measurement branch; Kickmix can then skip that no-op with a classical guard. This targets executed Toffoli count, unlike the previously rejected static affine-merge and temporary-AND-erasure hypotheses.
  - Local PDF: `docs/papers/2012.07711_relaxed_peephole_optimization.pdf`
