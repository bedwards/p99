import asyncio, time
import httpx
from hdrh import HdrHistogram

host = "192.168.1.121"


async def attack(url: str, rate: float, duration_s: float, timeout_s: float = 5.0):
    interval = 1.0 / rate
    start = time.perf_counter()
    end   = start + duration_s
    hist  = HdrHistogram(1, 60_000_000, 3)  # 1 usec .. 60 sec, 3 sig figs

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        i = 0
        while True:
            scheduled = start + i * interval
            now = time.perf_counter()
            if now < scheduled:
                await asyncio.sleep(scheduled - now)
            if now >= end:
                break
            try:
                t0 = time.perf_counter()
                r = await client.get(url)
                r.raise_for_status()
                t1 = time.perf_counter()
                # measure from scheduled time to completion to avoid CO
                latency_us = int((t1 - scheduled) * 1_000_000)
                hist.record_value(latency_us)
            except Exception:
                pass
            i += 1

    def p(x): return hist.get_value_at_percentile(x) / 1000.0  # ms
    print(f"count={hist.get_total_count()} p50={p(50):.2f} ms  p95={p(95):.2f} ms  "
          f"p99={p(99):.2f} ms  p99.9={p(99.9):.2f} ms  max={p(100):.2f} ms")

if __name__ == "__main__":
    asyncio.run(attack(f"http://{host}:8000/work", rate=200, duration_s=20))
