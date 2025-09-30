import asyncio
import random
import time
from contextlib import asynccontextmanager
import numpy as np
import torch
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

assert torch.backends.mps.is_available()
device = 'mps'
host = '0.0.0.0'


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    asyncio.create_task(batcher())
    yield
    # shutdown (optional cleanup code here)


app = FastAPI(lifespan=lifespan)

# request queue items are (t_submit, future, payload)
queue = asyncio.Queue()
BATCH_MAX = 64
FLUSH_MS  = 8   # flush cadence; change to see tail tradeoffs
SLOW_PATH_PROB = 0.01


@app.post('/infer')
async def infer(payload: dict):
    fut = asyncio.get_event_loop().create_future()
    await queue.put( (time.perf_counter(), fut, payload) )
    result = await fut
    return JSONResponse(result)


async def batcher():
    while True:
        items = [await queue.get()]
        t_start = time.perf_counter()
        try:
            # accept more while within cadence window
            while len(items) < BATCH_MAX and ((time.perf_counter() - t_start)*1000) < FLUSH_MS:
                try:
                    items.append(queue.get_nowait())
                except asyncio.QueueEmpty:
                    await asyncio.sleep(FLUSH_MS/4000.0)
            # build batch
            xs = []
            metas = []
            for (t0, fut, payload) in items:
                # stand-in features
                x = torch.randn(1024, 1024, device=device)  
                xs.append(x); metas.append((t0, fut))
            # simulate model compute
            a = torch.stack(xs)      # [B,1024,1024]
            b = torch.randn(1024, 1024, device=device)
            y = torch.matmul(a, b)   # one big batched GEMM
            if random.random() < SLOW_PATH_PROB:
                _ = (
                    torch.randn(4096, 4096, device=device) @
                    torch.randn(4096, 4096, device=device)
                )
            torch.mps.synchronize()
            # respond with per-request latency including queuing
            now = time.perf_counter()
            for (t0, fut), _out in zip(metas, y):
                if not fut.done():
                    fut.set_result({'latency_ms': (now - t0)*1000})
        finally:
            for _ in items: queue.task_done()


if __name__ == '__main__':
    uvicorn.run(app, host=host, port=8080, log_level='warning')
