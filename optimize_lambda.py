import numpy as np

# Load baseline data
data = np.load('candidates/public_busyaprime_v8/dfthcsos/submission.npz')
w = data['W']  # shape (10, 129, 46)
H2_I = data['H2_I']  # shape (10, 46)

# Compute baseline lambda_h2
sum_b_w = np.sum(np.abs(w), axis=1)  # (10,46)
term = sum_b_w + np.abs(H2_I)  # (10,46)
lambda_h2_baseline = 0.25 * np.sum(term ** 2)
print(f"Baseline lambda_h2: {lambda_h2_baseline:.6f}")

# Initialize Q as identity matrix
n_c = 46
Q = np.eye(n_c)

# Coordinate descent: iterate over pairs of columns, optimize Givens rotations
max_iter = 1000
tolerance = 1e-8
prev_lambda_h2 = lambda_h2_baseline

for iteration in range(max_iter):
    # Randomly shuffle column pairs
    cols = np.random.permutation(n_c)
    for i in range(0, n_c, 2):
        if i + 1 >= n_c:
            break
        c1 = cols[i]
        c2 = cols[i+1]

        # Extract columns c1 and c2 from w and H2_I
        w_col1 = w[:, :, c1]  # (10,129)
        w_col2 = w[:, :, c2]
        B_col1 = H2_I[:, c1]  # (10,)
        B_col2 = H2_I[:, c2]

        # Define function to compute lambda_h2 for a rotation angle theta
        def lambda_h2_for_theta(theta):
            c = np.cos(theta)
            s = np.sin(theta)
            # Rotate columns: new w columns are c*w_col1 + s*w_col2, -s*w_col1 + c*w_col2? Wait no, Givens rotation in 2D:
            # For a vector (a, b), rotation is (c*a - s*b, s*a + c*b)
            # Wait wait: to apply rotation to columns, the matrix is [[c, -s], [s, c]]
            # So new columns are [c1, c2] @ rotation matrix, so:
            new_w_col1 = c * w_col1 + s * w_col2
            new_w_col2 = -s * w_col1 + c * w_col2
            new_B_col1 = c * B_col1 + s * B_col2
            new_B_col2 = -s * B_col1 + c * B_col2
            # Compute sum_b |w| for each new column
            sum_b_new1 = np.sum(np.abs(new_w_col1), axis=1)
            sum_b_new2 = np.sum(np.abs(new_w_col2), axis=1)
            # Compute terms for each (rho, c)
            term1 = sum_b_new1 + np.abs(new_B_col1)
            term2 = sum_b_new2 + np.abs(new_B_col2)
            total = 0.25 * (np.sum(term1 ** 2) + np.sum(term2 ** 2))
            return total

        # Find theta that minimizes lambda_h2_for_theta using golden-section search
        # We'll search between -pi and pi
        def golden_section_search(f, a, b, tol=1e-5):
            gr = (np.sqrt(5) - 1) / 2
            c = b - gr * (b - a)
            d = a + gr * (b - a)
            while abs(c - d) > tol:
                if f(c) < f(d):
                    b = d
                else:
                    a = c
                c = b - gr * (b - a)
                d = a + gr * (b - a)
            return (a + b) / 2

        theta_opt = golden_section_search(lambda_h2_for_theta, -np.pi, np.pi, tol=1e-6)

        # Update Q with this rotation
        c = np.cos(theta_opt)
        s = np.sin(theta_opt)
        # Create Givens rotation matrix for columns c1, c2
        G = np.eye(n_c)
        G[c1, c1] = c
        G[c1, c2] = -s
        G[c2, c1] = s
        G[c2, c2] = c
        # Apply to Q: Q = G @ Q (since we're rotating columns of A, which is equivalent to multiplying by G on left? Wait no: A' = A @ G, so Q should be Q @ G
        Q = Q @ G

    # Compute current lambda_h2
    w_prime = w @ Q
    H2_I_prime = H2_I @ Q
    sum_b_w_prime = np.sum(np.abs(w_prime), axis=1)
    term_prime = sum_b_w_prime + np.abs(H2_I_prime)
    lambda_h2_current = 0.25 * np.sum(term_prime ** 2)

    if iteration % 10 == 0:
        print(f"Iteration {iteration}, lambda_h2: {lambda_h2_current:.6f}, change: {lambda_h2_current - prev_lambda_h2:.6f}")

    # Check convergence
    if abs(lambda_h2_current - prev_lambda_h2) < tolerance:
        break
    prev_lambda_h2 = lambda_h2_current

# Final lambda_h2 and change
print(f"\nFinal lambda_h2: {lambda_h2_current:.6f}, reduction: {lambda_h2_baseline - lambda_h2_current:.6f}")

# Also compute lambda_eff
lambda_h1 = ( (47.49402243356817 **2) / 3.91490781465 + 3.91490781465 ) / 2 - lambda_h2_baseline
Lambda_current = lambda_h1 + lambda_h2_current
lambda_eff_current = np.sqrt(3.91490781465 * (2 * Lambda_current - 3.91490781465))
lambda_eff_baseline = 47.49402243356817
print(f"lambda_eff baseline: {lambda_eff_baseline:.6f}, current: {lambda_eff_current:.6f}, change: {lambda_eff_current - lambda_eff_baseline:.6f}")

# Verify invariants: check if h1' and errors are preserved — but we need to reconstruct u vectors, which we don't have here
# But wait, the user said to keep circuits byte-identical, so angle words are same, so u vectors are same. We need to check that X is preserved up to rotation? Wait X' = X @ Q, so sum over c of X_rc would be... no, wait sum_c X_rc ⊗ X_rc would change unless Q is identity. But user said that's preserved. So maybe this approach is wrong.
