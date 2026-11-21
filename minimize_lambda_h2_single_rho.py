import numpy as np

# Load baseline data
data = np.load('candidates/public_busyaprime_v8/dfthcsos/submission.npz')
w = data['W']  # shape (10,129,46)
H2_I = data['H2_I']  # shape (10,46)

# Take a single rho, r=0
r = 0
B = H2_I[r:r+1]  # shape (1,46)
w_r = w[r]  # shape (129,46)

print(f"Original for r={r}:")
original_term_per_c = np.abs(B[0]) + np.sum(np.abs(w_r), axis=0)
original_lambda_h2 = 0.25 * np.sum(original_term_per_c **2)
print(f"lambda_h2: {original_lambda_h2:.6f}")

# Now find orthogonal Q to minimize sum over c of ( |B Q[:,c]| + sum_b |w_r,b Q[:,c]| )^2
# This is equivalent to, for each column c of Q, find unit vector u that minimizes ( |B·u| + sum_b |w_r,b·u| )^2
# Then build Q from these u's, then orthogonalize

# Initialize Q as identity
n_c = 46
Q = np.eye(n_c)

# Optimize each column
for col in range(n_c):
    # Current column u = Q[:,col]
    u = Q[:,col]
    # Function to minimize: f(theta) = |B·u_theta| + sum_b |w_r,b·u_theta|, where u_theta is a unit vector in plane of u and random direction
    # Pick a random direction orthogonal to u
    if col ==0:
        v = np.random.randn(n_c)
        v -= v @ u * u
        v /= np.linalg.norm(v)
    else:
        # Use Gram-Schmidt: orthogonal to previous columns
        v = np.random.randn(n_c)
        for prev_col in range(col):
            v -= v @ Q[:,prev_col] * Q[:,prev_col]
        v /= np.linalg.norm(v)
    # Golden section search for theta in [-pi, pi] that minimizes f(theta)
    def f(theta):
        u_theta = np.cos(theta) * u + np.sin(theta) * v
        return np.abs(B @ u_theta)[0] + np.sum(np.abs(w_r @ u_theta))
    # Golden section search
    a, b = -np.pi, np.pi
    gr = (np.sqrt(5)-1)/2
    c = b - gr*(b-a)
    d = a + gr*(b-a)
    while abs(c-d) > 1e-5:
        if f(c) < f(d):
            b = d
        else:
            a = c
        c = b - gr*(b-a)
        d = a + gr*(b-a)
    theta_opt = (a + b)/2
    # Update u
    u_opt = np.cos(theta_opt) * u + np.sin(theta_opt) * v
    Q[:,col] = u_opt

# Now, Q may not be perfectly orthogonal, so orthogonalize
Q, _ = np.linalg.qr(Q)

# Compute transformed values
B_prime = B @ Q
w_r_prime = w_r @ Q
# Compute new lambda_h2
new_term_per_c = np.abs(B_prime[0]) + np.sum(np.abs(w_r_prime), axis=0)
new_lambda_h2 = 0.25 * np.sum(new_term_per_c **2)

print(f"After optimization for single r={r}:")
print(f"New lambda_h2: {new_lambda_h2:.6f}, reduction: {original_lambda_h2 - new_lambda_h2:.6f}")
