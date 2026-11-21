# Implementation cycle 1

Implemented a deterministic Kickmix-based invsqrt generator that scans bounded phase-free windows for shared-target CCX pairs with equal shared-control ANFs and nonzero affine difference controls. It can use an existing affine wire or a restored X/CX realization, proves the complete original/replacement boundary maps equal on arbitrary dirty inputs, requires a negative-control mismatch, changes exactly one selected window, and checks the 62-qubit x-only schema, non-window instructions, and 1537-to-1536 static Toffoli-like reduction. Added reproducible proof/resource reporting and first-build parent snapshotting for repeatable regeneration.

## Changed files

- `source/build.py`
- `source/anf_merge.py`
- `source/README_ANF_MERGE.md`

## Build notes

Run `python source/build.py` from the workspace root. The first run asserts and snapshots the supplied parent as `source/parent_invsqrt.kmb`; subsequent runs use that pinned snapshot. A successful run writes `invsqrt.kmb` and `source/anf_merge_report.json`. Small deterministic ANF positive/negative self-tests run inside the build. I did not execute the build or official verification, per the orchestrator division of responsibilities.

## Known limitations

The actual champion scan has not been executed here, so discovery of an eligible site and all orchestrator checks remain unconfirmed. The search is intentionally restricted to the next same-target CCX with no intervening target dependency, at most 120 original operations and 26 active wires; if no certified pair exists, the build writes a negative report and stops rather than emitting a copied champion. Smoke/full correctness and measured cost are for the orchestrator to determine.
