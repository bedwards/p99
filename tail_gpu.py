import time, random, numpy as np, torch
assert torch.backends.mps.is_available(), 'MPS (Metal) not available'
device = 'mps'

def gpu_op():
    a = torch.randn(1024, 1024, device=device)
    b = torch.randn(1024, 1024, device=device)
    _ = a @ b
    if random.random() < 0.01:                           # 1% slow path
        waste = torch.randn(4096, 4096, device=device)   # extra compute
        _ = waste @ waste
    torch.mps.synchronize()   # important: measure end-to-end

def run(n=500):
    ts = []
    for _ in range(n):
        t0 = time.perf_counter()
        gpu_op()
        ts.append((time.perf_counter() - t0) * 1000)
    arr = np.array(ts)
    p = lambda q: np.percentile(arr, q)
    print(f'count={len(arr)}  p50={p(50):.2f}ms  p95={p(95):.2f}ms  p99={p(99):.2f}ms  max={arr.max():.2f}ms')

if __name__ == '__main__':
    torch.manual_seed(0); np.random.seed(0); random.seed(0)
    run()
