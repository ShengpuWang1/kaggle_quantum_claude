# Trade three ANGLE cache slots for fewer low-monomial recomputations

**Task:** `dfthcsos`

## Hypothesis

For at least one of the 15 existing five-word ANGLE loaders, raising the low4 low-monomial cache capacity from 8 to 9, 10, or 11—while recomputing the partition threshold to respect the 128-qubit cap—will retain more low monomials and reduce total static Toffoli-like gates despite any additional high-cache partitioning. Because selection and word registers are unchanged and ANGLE temporary workspace remains below the 303-qubit inner-state-preparation workspace, any such reduction should lower T_total without changing Q_total or lambda_eff. This is falsified if no alternative capacity beats both its same-plan capacity-8 emission and the corresponding champion circuit.

## Expected resource effect

Each eliminated unconditional low-cache recomputation saves one static CCX in one ANGLE circuit and therefore two executed Toffoli-like gates per verifier shot across the forward and reverse passes. The expected gain is modest and batch-dependent, possibly offset by a less favorable high-cache partition. Valid replacements keep the same factorization and words, so lambda_eff should remain 47.02142216209536; with unchanged public registers and the 128-qubit ANGLE cap, Q_total should remain 428 because inner_state_prep's 303 temporary qubits still dominate. No improvement is assumed: only measured full-verifier T_total below 15525 and score below the champion qualify.

## Research evidence

- **Trading T gates for dirty qubits in state preparation and unitary synthesis** (paper): https://arxiv.org/abs/1812.00954
  - Low, Kliuchnikov, and Schaeffer explicitly expose a tunable space/non-Clifford-gate tradeoff for classical-data oracles: additional workspace can reduce expensive gate work. The experiment adapts only this resource-allocation principle, not the paper's asymptotic state-preparation construction. The local low4 ANGLE emitter already makes the analogous tradeoff explicit: schedule capacity controls live low-monomial cache slots, and every avoided low computation removes one CCX; its build path currently fixes that capacity at 8.
  - Local PDF: `docs/papers/1812.00954_dirty_qubit_state_preparation.pdf`
