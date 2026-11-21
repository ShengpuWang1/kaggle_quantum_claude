# Implementation plan

1. Create a deterministic dfthcsos candidate from champion IMPORT-kirilltym-v9-365594383, initially copying submission.npz and all 15 angle_k_*.kmb files byte-for-byte. Add a source/build.py entrypoint and preserve or vendor the exact loader_port/staged_b154 source dependencies with hashes so the build does not depend on mutable run outputs.
2. Make a minimal experimental change to the local low4 compiler: expose low-cache capacity as an argument to build_delta/choose_delta, retaining 8 as the compatibility default. Pass that argument to schedule() in both unpartitioned and partitioned paths. In the partitioned path, derive the high-cache threshold jointly with the requested low capacity so the emitted circuit still satisfies num_qubits <= 128; do not change the promised-sign XOR-oracle semantics or public registers.
3. For each batch k=0..14, derive deltas from the champion submission.npz exactly as batch_deltas specifies. Use one fixed seed and one fixed bounded plan-search budget per batch, then reuse the resulting plan across capacities {8,9,10,11}; only scheduling/cache partitioning may vary. This separates the capacity effect from plan-search randomness.
4. For every capacity, run the existing independent-plan/truth checks and emitted resource assertions. Record Toffoli-like count, qubit count, selected capacity, low computations, high-cache count, partition threshold, and hashes. Require the best alternative capacity to use fewer static Toffoli-like gates than the same-plan capacity-8 emission and fewer than the actual champion circuit for that batch; otherwise retain the champion circuit bytes.
5. Serialize only winning replacement circuits, leaving submission.npz and every non-winning angle file untouched. Confirm identical selection/word registers, brot=8 and J=5, no Z_POW instructions, contiguous 15-file artifact layout, and unchanged angle words before handing the candidate to the orchestrator for smoke checks and its single terminal full verification.

## Acceptance criteria

- At least one replacement circuit has strictly lower static num_toffoli_like than both its same-plan capacity-8 emission and the corresponding champion circuit; every non-winning artifact remains byte-identical to the champion.
- All replacement plans pass the existing exact independent/truth checks, all circuits retain the champion register contract with num_qubits <= 128, and submission.npz has SHA-256 85c420b68e0aaf58354954a93aea4d231db33f7aa5be9f82b883a3277bbe760a.
- The unmodified official full dfthcsos verifier returns PASS with num_qubits == 428, lambda_eff equal to the champion within 1e-9, and toffoli_count strictly below 15525.0.
- The byte-identical candidate's official full-verifier score is finite and strictly below 312443243.84047496; otherwise the hypothesis is rejected and no promotion is requested.

## Risks

- A larger low cache can force a lower high-cache partition threshold and increase rather than decrease total Toffolis; same-plan capacity-8 comparison and per-batch rejection limit this risk.
- Template search is time-bounded and may introduce plan variation; reuse one fixed plan across all capacities and record the seed and plan hash.
- Measurement-based del_and cleanup or sign-gauge borrowing could be disturbed by emitter edits; retain the existing assertions and require the unmodified official full verifier to pass.
- The imported champion is not offline-rebuildable from its notebook alone; the candidate must include deterministic generator/build source and exact dependency pins rather than treating the preserved notebook as a rebuild recipe.
