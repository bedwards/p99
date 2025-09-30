import asyncio
import json
import logging
import time
import httpx
from hdrh.histogram import HdrHistogram  # pip install -U hdrhistogram

host = '192.168.1.121'
log_every_n = 10

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

for service in ['httpx', 'httpcore']:  # 'httpcore.http11':
    logging.getLogger(service).setLevel(logging.WARNING)


async def blast(rate=200, seconds=60):
    root_url = f'http://{host}:8080'
    url = f'{root_url}/infer'
    interval = 1.0 / rate
    start = time.perf_counter()
    end   = start + seconds
    hist  = HdrHistogram(1, 60_000_000, 3)  # 1us..60s, 3 sig figs
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            _r = await client.get(root_url, timeout=2.0)
            logging.info(
                f'remote access ok: GET / -> '
                f'{getattr(_r, "status_code", "n/a")}'
            )
        except Exception as e:
            logging.warning(f'remote access check failed: {e}')

        i = 0
        while True:
            scheduled = start + i * interval
            now = time.perf_counter()

            if now >= end:
                break

            if now < scheduled:
                await asyncio.sleep(scheduled - now)

            t0 = time.perf_counter()

            try:
                if i % log_every_n == 0:
                    logging.debug(f'POST /infer scheduled_at={scheduled:.6f}')
                r = await client.post(url, json={'x': 1})
                r.raise_for_status()
                if i % log_every_n == 0:
                    logging.debug(f'/infer -> {r.status_code}')
                t1 = time.perf_counter()
                hist.record_value(int((t1 - scheduled) * 1_000_000))
            except Exception:
                logging.warning('request failed', exc_info=True)

            if i % log_every_n == 0:
                elapsed = time.perf_counter() - start
                approx_sends_per_sec = i / elapsed if elapsed > 0 else 0.0
                if i % log_every_n == 0:
                    logging.info(f'sent={i} elapsed={elapsed:.2f}s approx_qps={approx_sends_per_sec:.1f}')

            i += 1

    def p(q):
        return hist.get_value_at_percentile(q) / 1000.0

    print(f'n={hist.get_total_count()} p50={p(50):.2f}ms p95={p(95):.2f}ms p99={p(99):.2f}ms p99.9={p(99.9):.2f}ms')

    with open('latency.hdr', 'wb') as f:
        f.write(hist.encode())

    logging.info('blast complete, histogram written to latency.hdr')


if __name__ == '__main__':
    asyncio.run(blast())
