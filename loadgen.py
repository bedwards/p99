import asyncio, time, json
import httpx
from hdrhistogram import HdrHistogram

host = '192.168.1.121'


async def blast(rate=200, seconds=60):
    url = f'http://{host}:8080/infer'
    interval = 1.0 / rate
    start = time.perf_counter()
    end   = start + seconds
    hist  = HdrHistogram(1, 60_000_000, 3)  # 1us..60s, 3 sig figs
    async with httpx.AsyncClient(timeout=5.0) as client:
        i = 0
        while True:
            scheduled = start + i*interval
            now = time.perf_counter()
            if now >= end: break
            if now < scheduled: await asyncio.sleep(scheduled - now)
            t0 = time.perf_counter()
            try:
                r = await client.post(url, json={'x': 1})
                r.raise_for_status()
                t1 = time.perf_counter()
                hist.record_value(int((t1 - scheduled) * 1_000_000))
            except Exception:
                pass
            i += 1
    def p(q): return hist.get_value_at_percentile(q)/1000.0
    print(f'n={hist.get_total_count()} p50={p(50):.2f}ms p95={p(95):.2f}ms p99={p(99):.2f}ms p99.9={p(99.9):.2f}ms')
    with open('latency.hdr', 'w') as f:
        f.write(hist.encode())


if __name__ == '__main__':
    asyncio.run(blast())
