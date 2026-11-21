import numpy as np

# Load data
data = np.load('candidates/public_busyaprime_v8/dfthcsos/submission.npz')
w = data['W']  # shape (10,129,46)
H2_I = data['H2_I']  # shape (10,46)

original = np.sum( (np.sum(np.abs(w), axis=1) + np.abs(H2_I))**2 )
print(f"Original sum_sq: {original:.2f}, lambda_h2: {0.25*original:.4f}")

n_c = 46
for i in range(5):
    random_matrix = np.random.randn(n_c, n_c)
    Q, _ = np.linalg.qr(random_matrix)
    w_prime = w @ Q
    H2_I_prime = H2_I @ Q
    sum_sq = np.sum( (np.sum(np.abs(w_prime), axis=1) + np.abs(H2_I_prime))**2 )
    change = sum_sq - original
    print(f"Trial {i+1}: sum_sq={sum_sq:.2f}, change={change:.2f}, lambda_h2 change={change*0.25:.2f}")
