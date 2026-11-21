# Implementation plan

1. Create a deterministic `source/build.py` that snapshots the supplied champion for offline rebuilds and requires parent SHA-256 `0104d1b44d7394906c9ef1d445efbd8ca0bed8d2df833ce164e1802335f6c137`. Load and serialize only through the official Kickmix API; preserve the sole x register and do not depend on the imported notebook's unavailable Kaggle inputs.
2. Scan unconditional HMR instructions and their following bounded windows. Restrict a window to at most 256 instructions and 16 arbitrary active boundary quantum wires besides the measured wire and independent outcome bit. Stop at any allocation/free, reset, further measurement, classical-bit write, condition push/pop, existing conditional instruction, Z_POW/other phase operation, or any instruction other than X/CX/CCX. Consider only currently unconditional CCX candidates.
3. For each candidate, initialize the HMR target to zero, the outcome bit b as an independent Boolean variable, and every other active boundary wire to an independent variable. Use bit-parallel exhaustive truth tables over all `2^(w+1)` assignments (w <= 16), propagate the X/CX/CCX window, and certify both that the CCX fire function implies b and that original versus b-guarded behavior has identical complete boundary output values for every assignment. Require at least one b=1 firing witness so the proof is not vacuous. As a negative control, require the proof harness to detect a mismatch for the opposite, skip-on-b=1 behavior at such a witness.
4. Among certified sites only, use a fixed deterministic correctness-neutral profiling sample to estimate how many parent CCX executions would be skipped with b=0. Select exactly one site with positive estimated skipped executions, maximizing estimated skips and breaking ties by HMR and CCX instruction indices. Sampling may rank proved rewrites but must never certify implication; if there is no proved non-vacuous site with positive estimated benefit, emit a negative report and stop without copying the champion as a candidate.
5. Append ` if b<id>` to only the selected CCX instruction, using the bit from its anchoring HMR, and serialize `invsqrt.kmb`. Assert 62 qubits, the unchanged 22-qubit little-endian x-only register schema, unchanged instructions everywhere else, unchanged Z_POW stream, and static Toffoli-like count 1537 equal to the parent. Save the selected indices/instructions, exhaustive-proof dimensions and witnesses, negative-control result, profiling estimate, resource counts, and input/output hashes. Confirm a second deterministic build is byte-identical.
6. Let the orchestrator run the configured bounded checks and official invsqrt smoke verification for correctness only, followed by exactly one terminal full verification. Do not alter rotations, precision, approximation tables, other gates, salts, measurement outcomes, or other tasks.

## Acceptance criteria

- Two deterministic builds consume the exact pinned champion and produce byte-identical invsqrt.kmb and identical proof/resource reports without external notebook inputs.
- Exactly one CCX gains a classical guard; its anchoring HMR and complete bounded window pass exhaustive equivalence over every arbitrary dirty boundary assignment and both outcome values, the fire-implies-bit certificate holds, and the opposite-guard negative control is rejected.
- The selected site has positive estimated skipped executions on the fixed profiling sample, while sampling is excluded from the correctness proof.
- The candidate retains 62 qubits, the original x-only 22-qubit register schema, all non-site instructions and Z_POW rotations unchanged, and exactly 1537 static Toffoli-like operations.
- The configured official invsqrt smoke check passes with restored x and clean scratch; smoke cost is not compared with full cost.
- The unmodified official full invsqrt verifier returns PASS with unchanged qubit/rotation resources, mean Toffoli count strictly below 1281.6639428436274, and finite positive score strictly below 97921.60740959947; the verified candidate bytes remain unchanged for promotion.

## Risks

- No HMR-anchored window may satisfy the implication within the conservative instruction and active-wire bounds; that is a bounded negative result and must not trigger a broader scan or rewrite.
- Exhaustive truth tables grow exponentially, so the 16-boundary-wire cap and 256-instruction cap are hard resource limits rather than suggestions.
- A sampled guard candidate is not necessarily valid on all inputs or branch histories; only the exhaustive arbitrary-boundary/two-outcome proof may authorize an edit.
- The HMR bit must remain live and unmodified until the selected gate, and crossing classical-condition or measurement semantics could invalidate the local proof, so those operations are hard barriers.
- Changing circuit bytes changes hash-seeded measurement randomness. The semantic proof covers both outcomes, but smoke success is not sufficient and the terminal full verifier remains authoritative.
- The expected mean reduction is small and could be obscured by finite-shot operation-count variation; promotion still requires strictly lower measured full cost.
