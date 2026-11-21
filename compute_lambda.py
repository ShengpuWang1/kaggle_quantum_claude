import numpy as np

# Load the baseline submission data
data = np.load('candidates/public_busyaprime_v8/dfthcsos/submission.npz')
w = data['W']  # shape (10, 129, 46)
H2_I = data['H2_I']  # shape (10, 46)
U = data['U']  # shape (10, 129, 76)

print("Baseline data shapes:")
print(f"w: {w.shape}, H2_I: {H2_I.shape}, U: {U.shape}")

# Compute lambda_h2: 0.25 * sum over r,c of ( sum_b |w[r,b,c]| + |H2_I[r,c]| )^2
sum_b_w = np.sum(np.abs(w), axis=1)  # shape (10, 46): sum over b of |w|
term = sum_b_w + np.abs(H2_I)  # shape (10,46)
lambda_h2 = 0.25 * np.sum(term ** 2)
print(f"lambda_h2: {lambda_h2}")

# Now, to compute lambda_h1, we need to get h1_prime eigenvalues, which requires reconstructing u vectors and X, h1_prime.
# But we can approximate, or wait: the baseline has lambda_eff=47.494, E_gap=3.9149, so lambda_eff = sqrt(E_gap * (2 Lambda - E_gap))
# So Lambda = ( (lambda_eff **2) / E_gap + E_gap ) / 2
lambda_eff_baseline = 47.49402243356817
E_gap_baseline = 3.91490781465
Lambda_baseline = ( (lambda_eff_baseline **2) / E_gap_baseline + E_gap_baseline ) / 2
print(f"Lambda from lambda_eff: {Lambda_baseline}")
lambda_h1 = Lambda_baseline - lambda_h2
print(f"lambda_h1: {lambda_h1}")

print(f"\nBaseline: lambda_h1={lambda_h1}, lambda_h2={lambda_h2}, Lambda={Lambda_baseline}, lambda_eff={lambda_eff_baseline}")

# Now test 10 random orthogonal matrices Q (46x46)
n_c = 46
for trial in range(5):
    # Generate random orthogonal matrix using QR decomposition
    random_matrix = np.random.randn(n_c, n_c)
    Q, _ = np.linalg.qr(random_matrix)

    # Transform w and H2_I: w' = w @ Q, H2_I' = H2_I @ Q
    w_prime = w @ Q  # shape (10,129,46)
    H2_I_prime = H2_I @ Q  # shape (10,46)

    # Compute new lambda_h2
    sum_b_w_prime = np.sum(np.abs(w_prime), axis=1)  # (10,46)
    term_prime = sum_b_w_prime + np.abs(H2_I_prime)  # (10,46)
    lambda_h2_prime = 0.25 * np.sum(term_prime ** 2)
    Lambda_prime = lambda_h1 + lambda_h2_prime
    lambda_eff_prime = np.sqrt(E_gap_baseline * (2 * Lambda_prime - E_gap_baseline))

    print(f"\nTrial {trial+1}:")
    print(f"lambda_h2' = {lambda_h2_prime}, change: {lambda_h2_prime - lambda_h2}")
    print(f"Lambda' = {Lambda_prime}, change: {Lambda_prime - Lambda_baseline}")
    print(f"lambda_eff' = {lambda_eff_prime}, change: {lambda_eff_prime - lambda_eff_baseline}")
