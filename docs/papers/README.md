# Papers for Verifiable Quantum Circuit Compilation

Selected on 2026-10-27 for this workspace's three competition tasks: `invsqrt`,
`dqi`, and `dfthcsos`. The collection prioritizes direct benchmark references and
reusable circuit constructions. Relevance notes below are reading recommendations,
not claims that a construction will improve the competition score without adaptation.
PDF filenames use arXiv identifiers, matching the existing companion paper.

## Start here

1. **Discovering state-of-the-art quantum circuits with large language models**
   (Gu et al., 2026). [PDF](2610.22367.pdf) · [Source](https://arxiv.org/abs/2610.22367).
   Closest external overlap: evaluator-guided circuit search across arithmetic,
   chemistry, and decoding. Compare its constructions and evaluation assumptions
   with the competition's exact gate set, verification conditions, and cost metric.
2. **Verifiable Quantum Advantage via Optimized DQI Circuits**
   (Khattar et al., 2025). [PDF](2510.10967.pdf) · [Source](https://arxiv.org/abs/2510.10967).
   Direct foundation for `dqi`: reversible Reed-Solomon decoding, extended Euclidean
   arithmetic, implicit Bezout coefficients, and space/gate trade-offs.
3. **Fast quantum simulation of electronic structure by spectrum amplification**
   (Low et al., 2025). [PDF](2502.15882.pdf) · [Source](https://arxiv.org/abs/2502.15882).
   Direct foundation for `dfthcsos`: sum-of-squares Hamiltonians, spectrum
   amplification, and the hybrid double-factorization/tensor-hypercontraction scheme.
4. **Optimizing Quantum Circuits for Arithmetic**
   (Häner, Roetteler, and Svore, 2018). [PDF](1805.12445.pdf) · [Source](https://arxiv.org/abs/1805.12445).
   Especially relevant to `invsqrt`: reversible function evaluation, including
   inverse square roots, and arithmetic approximation/resource trade-offs.

## Arithmetic and uncomputation

- **Halving the cost of quantum addition** (Gidney; preprint 2017, published 2018).
  [PDF](1709.06648.pdf) · [Source](https://arxiv.org/abs/1709.06648).
  Temporary logical ANDs and measurement-assisted uncomputation; useful when
  optimizing adders and cleaning ancillas in kickmix-compatible circuits.
- **Quantum computation of stopping power for inertial fusion target design**
  (Rubin et al.; preprint 2023, published 2024).
  [PDF](2308.12352.pdf) · [Source](https://arxiv.org/abs/2308.12352).
  Application and resource-estimation context for Coulomb interactions and the
  competition's inverse-square-root benchmark.

## Decoding background

- **Optimization by Decoded Quantum Interferometry**
  (Jordan et al.; preprint 2024, published 2025).
  [PDF](2408.08292.pdf) · [Source](https://arxiv.org/abs/2408.08292).
  Explains the reduction from optimization to decoding and why coherent decoder
  behavior matters. Read alongside the more implementation-focused Khattar paper.

## Chemistry and quantum lookup tables

- **Even more efficient quantum computations of chemistry through tensor hypercontraction**
  (Lee et al.; preprint 2020, published 2021).
  [PDF](2011.03494.pdf) · [Source](https://arxiv.org/abs/2011.03494).
  THC block encodings and finite-resource comparisons; background for the chemistry
  benchmark's factorization and rotation costs.
- **Encoding Electronic Spectra in Quantum Circuits with Linear T Complexity**
  (Babbush et al., 2018).
  [PDF](1805.03662.pdf) · [Source](https://arxiv.org/abs/1805.03662).
  Foundational electronic-structure block encodings and efficient selection/lookup
  constructions; useful context for QROM-oriented optimization.
- **Trading T gates for dirty qubits in state preparation and unitary synthesis**
  (Low, Kliuchnikov, and Schaeffer; preprint 2018).
  [PDF](1812.00954.pdf) · [Source](https://arxiv.org/abs/1812.00954).
  Quantum data-lookup constructions with tunable ancilla-versus-gate costs;
  a useful source of ideas for chemistry QROM trade-offs.

## Circuit optimization and tooling

- **Quantum Circuit Optimization with AlphaTensor** (Ruiz et al.; preprint 2024,
  published 2025).
  [PDF](2402.14396.pdf) · [Source](https://arxiv.org/abs/2402.14396).
  Automated non-Clifford optimization and tensor-based circuit discovery.
  Treat this as a method reference: its synthesis objectives are not identical
  to the competition's allowed gates and scoring.
- **Expressing and Analyzing Quantum Algorithms with Qualtran** (Harrigan et al., 2024).
  [PDF](2409.04643.pdf) · [Source](https://arxiv.org/abs/2409.04643).
  Algorithm decomposition, reusable building blocks, and resource accounting in
  the library already vendored in this workspace. The paper predates kickmix;
  consult the pinned local kickmix documentation for the actual API.

## Existing companion paper

- **Leveraging verifiable structure in quantum circuits to find more efficient
  compilations with agentic AI** (Khattar et al., 2026).
  [PDF](2610.23832.pdf) · [Source](https://arxiv.org/abs/2610.23832).
  Already present before this collection was expanded; retained unchanged.
  It defines the three benchmarks and provides the primary reference trail used
  to select most of these additions.

## Download provenance

The 12 added PDFs were fetched from public arXiv PDF endpoints. These are arXiv
manuscripts, not necessarily publisher-formatted versions. See
[download_manifest.json](download_manifest.json) for URLs, download date, PDF
version when present on the first page, page counts, byte sizes, and SHA-256 hashes.
The manifest covers newly added papers only. PDF signatures, parsing, page counts,
and first-page identities were checked after download.
