import numpy as np
from pathlib import Path

# Add the verifier path to sys.path
import sys
sys.path.insert(0, str(Path('data/official/verifiers').resolve()))
from dfthcsos.scoreinfra.dfthc_math import evaluate_dfthc_vectors, symmetric_from_lower
from dfthcsos.scoreinfra.circuits import load_circuits, recover_words_from_circuits
from dfthcsos.scoreinfra.reference import load_reference, load_factorization, load_fixed_shifts

# Load baseline submission data using load_factorization
submission_path = 'candidates/public_busyaprime_v8/dfthcsos/submission.npz'
from dfthcsos.scoreinfra.reference import load_factorization
params = load_factorization(submission_path)
w = params['W']  # lowercase w, shape (10,129,46)
H2_I = params['H2_I']  # shape (10,46)
Hsym_lower = params['Hsym_lower']  # shape (2926,)
H1_I = params['H1_I']  # scalar
tree_edges = params['tree_edges']
brot = params['brot']
angle_words = params['angle_words']

# Reconstruct S from Hsym_lower
num_orbitals = 76
S = symmetric_from_lower(Hsym_lower, num_orbitals)

# Load reference data
from dfthcsos.scoreinfra.reference import check_fcidump
ref = load_reference(check_fcidump())
beta_1 = H1_I - 0.5 * np.trace(S)  # from native_inputs

# Evaluate baseline metrics
print("Baseline evaluation:")
# We need u_all from angle_words, so reconstruct it
from dfthcsos.scoreinfra.dfthc_math import reconstruct_u_vectors
u_all = reconstruct_u_vectors(angle_words / (1 << (brot - 1)), tree_edges)
baseline_metrics = evaluate_dfthc_vectors(u_all, w, H2_I, S, beta_1, ref, energy_upper=-22140.27335)
print(f"error_1: {baseline_metrics['error_1']:.6f}, error_2: {baseline_metrics['error_2']:.6f}")
print(f"Lambda: {baseline_metrics['Lambda']:.6f}, lambda_eff: {baseline_metrics['lambda_eff']:.6f}, E_gap: {baseline_metrics['E_gap']:.6f}")

# Now apply a random orthogonal Q to B dimension (axis1 of w)
n_b = 129
random_matrix = np.random.randn(n_b, n_b)
Q, _ = np.linalg.qr(random_matrix)
w_prime = np.einsum('rbc,bb->rbc', w, Q)  # shape (10,129,46)

# We need to adjust H2_I to maintain W_rho_c + sum(w') = H2_I' — wait original W is H2_I - sum(w), so to keep W same, H2_I' = W + sum(w')
# Original W: params["H2_I"] - sum(params["W"], axis=1) — so load factorization to get W? Wait no, native_inputs does:
# params = load_factorization(submission_path)
# W = params["H2_I"] - sum(params["W"], axis=1)
# But we can compute original W as H2_I - np.sum(w, axis=1)
original_W = H2_I - np.sum(w, axis=1)  # shape (10,46)
# New H2_I should be original_W + np.sum(w_prime, axis=1) to keep W same
H2_I_prime = original_W + np.sum(w_prime, axis=1)  # shape (10,46)

# Now evaluate transformed metrics
print("\nTransformed (Q on B dimension) evaluation:")
# u_all is same (angle words are unchanged)
transformed_metrics = evaluate_dfthc_vectors(u_all, w_prime, H2_I_prime, S, beta_1, ref, energy_upper=-22140.27335)
print(f"error_1: {transformed_metrics['error_1']:.6f}, error_2: {transformed_metrics['error_2']:.6f}")
print(f"Lambda: {transformed_metrics['Lambda']:.6f}, lambda_eff: {transformed_metrics['lambda_eff']:.6f}, E_gap: {transformed_metrics['E_gap']:.6f}")

# Check if errors are within thresholds
print(f"\nError thresholds: error_1 <= 0.02, error_2 <=0.02")
print(f"Baseline errors: {baseline_metrics['error_1']:.6f}, {baseline_metrics['error_2']:.6f}")
print(f"Transformed errors: {transformed_metrics['error_1']:.6f}, {transformed_metrics['error_2']:.6f}")
