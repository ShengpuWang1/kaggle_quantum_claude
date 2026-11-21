# Measurement-erased uncomputation of one certified invsqrt AND pair

**Task:** `invsqrt`

## Hypothesis

The champion still contains a clean compute/use/uncompute sequence of the form CCX(a,b,t), operations that only read t and do not write a, b, or t, then CCX(a,b,t), with t proven zero before the first CCX. Applying the paper's temporary-AND erasure to only the second CCX should remove one unconditionally executed Toffoli-like gate without changing the inverse-square-root approximation, rotations, qubit count, or scratch cleanliness. This is materially different from the rejected shared-affine-quadratic merge: the prior scan found no affine-sharing match, whereas this experiment tests measurement-based erasure of an existing matched compute/uncompute pair.

## Expected resource effect

One eligible unconditional pair changes two executed CCX gates in the compute/uncompute lifecycle to one CCX plus a zero-Toffoli HMR/conditional-CZ erasure. With Q and the rotation/T stream fixed, each removed executed CCX should reduce invsqrt cost by approximately 62 cost units; the experiment deliberately rewrites only one pair. It adds one measurement/correction site and may increase reaction depth, but adds no qubits or synthesized rotations.

## Research evidence

- **Halving the cost of quantum addition** (paper): https://arxiv.org/abs/1709.06648
  - Gidney's temporary logical-AND stores an AND with four T gates and later erases it with zero T gates by measurement plus a conditional CZ phase correction. The relevant mechanism is not a generic adder rewrite: when a clean ancilla holding a·b is later cleared by a second CCX with unchanged controls, that uncomputing CCX can be replaced by HMR on the ancilla and CZ on the original controls conditioned on the fresh measurement bit. This removes one Toffoli-like operation while preserving the complete values-and-phase map.
  - Local PDF: `docs/papers/gidney_2018_halving_quantum_addition.pdf`
