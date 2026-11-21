# ANF-certified shared-quadratic CCX merge in the champion invsqrt circuit

**Task:** `invsqrt`

## Hypothesis

The 62-qubit champion may still contain a phase-free window in which two same-target CCX gates have one control related by an intervening CX-only affine transformation. Propagating square-free Boolean polynomials can expose the shared quadratic term: toggling with controls A·B and (A⊕C)·B leaves only C·B, so the pair can be resynthesized with one CCX while retaining the affine updates. Applying the paper's share/cancel-quadratic-terms mechanism to one such exactly proved window should reduce executed Toffoli-like count without changing the inverse-square-root approximation, phase rotations, or qubit count. This is a new, deterministic scan of the actual champion rather than another rebuild of the much larger reference/linear-seed generator.

## Expected resource effect

Each successful shared-target merge removes one CCX from every execution of a deterministic phase-free window; a mirrored compute/uncompute opportunity could remove two. Since invsqrt cost is Q*(mean Toffoli-like + T/4), keeping Q=62 and the rotation stream unchanged should reduce cost by approximately 62 cost units per mean executed CCX removed, with no anticipated qubit or rotation-synthesis overhead.

## Research evidence

- **Optimizing Quantum Circuits for Arithmetic** (paper): https://arxiv.org/abs/1805.12445
  - Häner, Roetteler, and Svore reduce reversible arithmetic by exploiting its algebraic structure: their fixed-point squaring construction uses diagonal terms and each symmetric cross product only once, rather than synthesizing a generic multiplication. The useful mechanism here is to expose and cancel/share quadratic Boolean terms instead of treating a compiled gate sequence as immutable. The paper also distinguishes this structured arithmetic optimization from simply increasing approximation precision.
  - Local PDF: `docs/papers/1805.12445_optimizing_quantum_circuits_for_arithmetic.pdf`
