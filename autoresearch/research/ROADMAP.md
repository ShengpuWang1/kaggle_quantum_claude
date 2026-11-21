# Auto-research roadmap

## Objective

Discover reproducible circuit constructions that pass the unmodified official verifiers at lower task cost than the current per-task champions. Local full-verifier costs guide promotion; Kaggle's private salt and hosted evaluation remain authoritative.

## Operating principles

1. Test one focused hypothesis per experiment.
2. Preserve reproducible generator source with every promoted artifact.
3. Use smoke checks for correctness only; never compare smoke costs with full costs.
4. Allow bounded build/smoke/review repairs, then exactly one terminal full verification.
5. Promote only byte-identical, fully verified candidates with strictly lower cost and an unchanged parent champion.
6. Never upload or submit automatically.

## Research directions

- **invsqrt:** reduce Toffoli-equivalent phase-gradient and arithmetic overhead while retaining accuracy over the complete input domain.
- **dqi:** reduce syndrome-decoding time and qubit overhead without weakening the certified failure bound under fresh validation randomness.
- **dfthcsos:** improve factorization-driven Givens/ANGLE/QROM constructions while preserving every chemistry verifier invariant.

Directions are prompts for investigation, not claims that a particular optimization is available or correct.
