import numpy as np
from pathlib import Path
import shutil

# Paths
baseline_dir = Path('candidates/public_busyaprime_v8/dfthcsos')
new_candidate_dir = Path('runs/chemistry_gauge_search/transformed_basis_test')
new_submission_npz = new_candidate_dir / 'submission.npz'

# Create directory
new_candidate_dir.mkdir(parents=True, exist_ok=True)
# Copy all files from baseline (circuits, etc.)
for file in baseline_dir.glob('*'):
    if file.is_file() and file.name != 'submission.npz':
        shutil.copy(file, new_candidate_dir)

# Load baseline submission data
data = np.load(baseline_dir / 'submission.npz')
w = data['W']  # shape (10,129,46)
H2_I = data['H2_I']  # shape (10,46)
U = data['U']
Hsym_lower = data['Hsym_lower']
H1_I = data['H1_I']
tree_edges = data['tree_edges']
brot = data['brot']
angle_words = data['angle_words']
offset_W = data['offset_W']

# Apply random orthogonal Q to B dimension (axis 1 of w)
n_b = 129
random_matrix = np.random.randn(n_b, n_b)
Q, _ = np.linalg.qr(random_matrix)
w_prime = np.einsum('rbc,bb->rbc', w, Q)  # shape (10,129,46)

# Maintain offset relation: W = H2_I - sum(w), so to keep W same, H2_I' = W + sum(w')
W_original = H2_I - np.sum(w, axis=1)
H2_I_prime = W_original + np.sum(w_prime, axis=1)

# Save new submission npz
np.savez(new_submission_npz,
         U=U,
         W=w_prime,
         H2_I=H2_I_prime,
         Hsym_lower=Hsym_lower,
         H1_I=H1_I,
         tree_edges=tree_edges,
         brot=brot,
         angle_words=angle_words,
         offset_W=offset_W)

print(f"Created transformed candidate at {new_candidate_dir}")
print(f"Original lambda_h2: {0.25 * np.sum((np.sum(np.abs(w), axis=1) + np.abs(H2_I))**2):.4f}")
print(f"New lambda_h2: {0.25 * np.sum((np.sum(np.abs(w_prime), axis=1) + np.abs(H2_I_prime))**2):.4f}")
