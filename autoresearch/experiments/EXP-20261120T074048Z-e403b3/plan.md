# Implementation plan

1. Create a deterministic source/build.py that loads the supplied workspace champion invsqrt.kmb, snapshots it as source/parent_invsqrt.kmb for repeatable rebuilds, and requires SHA-256 0104d1b44d7394906c9ef1d445efbd8ca0bed8d2df833ce164e1802335f6c137 before every scan. Use the official kickmix reader/serializer and do not depend on the imported notebook's unavailable Kaggle inputs.
2. Scan only unconditional, phase-free X/CX/CCX regions. Match exactly two CCX instructions with the same two controls a,b and target t, requiring conservative clean-target provenance from a dominating R/reset with no intervening t write. Between the pair, forbid every write to a, b, or t and every measurement, reset, allocation/free, classical-condition change, Z_POW, or non-X/CX/CCX operation; t may only be read as a control. Bound candidates to at most 256 instructions and 16 active boundary wires.
3. For one deterministically selected eligible pair (earliest second-CCX instruction index), retain the first CCX and replace only the second with HMR t b_new followed by CZ a b if b_new. Choose b_new as a previously unused classical-bit identifier and use it nowhere else. Preserve the surrounding instruction order and all existing measurement bits.
4. Certify the selected rewrite by exhaustive boundary simulation for every basis assignment of all other active wires, t=0 at entry, and both HMR outcomes. Require original and replacement windows to agree on every output wire and tracked phase; equality on every basis value and phase proves the same linear operation on arbitrary superpositions. Run a negative control with the conditional CZ omitted and require a detected phase mismatch. If no pair passes, emit a negative report and stop without copying the champion as a candidate.
5. Serialize exactly one rewritten circuit to invsqrt.kmb. Assert 62 qubits, the unchanged sole 22-qubit little-endian x register, identical instructions outside the one-gate replacement site, an unchanged Z_POW stream, no new quantum wires, and a static Toffoli-like count of 1536 versus the champion's 1537. Save the selected indices, pair and replacement instructions, clean-target proof, exhaustive-equivalence report, negative-control result, resource counts, and input/output hashes.
6. Let the orchestrator run the configured build checks and official invsqrt smoke verification for correctness only, then its single terminal full verification. Do not alter rotations, precision, approximation tables, other circuit regions, salts, or other tasks.

## Acceptance criteria

- Two deterministic builds consume the pinned champion hash and produce byte-identical invsqrt.kmb plus the same proof/resource reports; no external notebook inputs are needed.
- Exactly one second-CCX site is replaced, its target is certified clean before the first CCX, controls and target are not written between the pair, and exhaustive entry-basis/two-outcome simulation proves identical values and phases while the no-CZ negative control fails.
- The candidate has 62 qubits, the original x-only 22-qubit register schema, unchanged non-site instructions and Z_POW rotations, one fresh classical measurement bit, and exactly 1536 static Toffoli-like operations versus 1537 in the parent.
- The configured official invsqrt smoke check passes, including restored x and clean scratch; smoke cost is not used for promotion.
- The unmodified official full invsqrt verifier returns PASS with finite positive cost strictly below 97921.60740959947, and the verified candidate bytes are unchanged for promotion.

## Risks

- The champion may have no remaining pair satisfying the clean-target and unchanged-control conditions, especially because much of its arithmetic already uses measurement uncomputation; that is a bounded negative result, not a reason to broaden the rewrite.
- Replacing an arbitrary toggling CCX rather than a true clean-AND erasure would be incorrect, so target provenance and control/target write exclusion must remain conservative.
- HMR correctness depends on the phase correction and classical-bit scoping; the exhaustive two-outcome proof and negative control are required before any official run.
- Changing circuit bytes changes hash-seeded measurement randomness. The local proof covers both outcomes for the new site, but smoke success alone is insufficient and the terminal full verifier remains authoritative.
- The added measurement can increase reaction depth and operational overhead even though the official cost decreases; no claim is made about wall-clock runtime or hosted score.
