import asyncio
import time
from contextlib import asynccontextmanager
import numpy as np
import torch
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

host = '0.0.0.0'

assert torch.backends.mps.is_available()
device = 'mps'
DIM = 768
K = 10
BATCH_MAX = 64
FLUSH_MS  = 6
LIMIT = asyncio.Semaphore(3)

corpus = torch.empty((0, DIM), device=device)   # in-GPU store
corpus_ids = []                                 # parallel python list
store_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    asyncio.create_task(q_batcher())
    yield
    # shutdown (optional cleanup code here)


app = FastAPI(lifespan=lifespan)
q_queue = asyncio.Queue()  # (t_submit, fut, vec)


@app.post('/upsert')
async def upsert(item: dict):
    v = torch.tensor(item['vec'], dtype=torch.float32, device=device).flatten()
    assert v.shape[0] == DIM
    async with store_lock:
        global corpus, corpus_ids
        corpus = torch.cat([corpus, v.unsqueeze(0)], dim=0)
        corpus_ids.append(item.get('id', str(len(corpus_ids))))
    return JSONResponse({'count': corpus.shape[0]})


@app.post('/query')
async def query(item: dict):
    v = (torch
        .tensor(
            item['vec'],
            dtype=torch.float32,
            device=device
        )
        .flatten()
    )
    fut = asyncio.get_event_loop().create_future()
    await q_queue.put( (time.perf_counter(), fut, v) )
    res = await fut
    return JSONResponse(res)


async def q_batcher():
    while True:
        t0, fut, v = await q_queue.get()
        items = [(t0,fut,v)]
        try:
            t_start = time.perf_counter()
            while (len(items) < BATCH_MAX and
                    ((time.perf_counter()-t_start)*1000) < FLUSH_MS):
                try:
                    items.append(q_queue.get_nowait())
                except asyncio.QueueEmpty:
                    await asyncio.sleep(FLUSH_MS/4000.0)
            async with LIMIT:
                # [B, D]
                vs = torch.stack([it[2] for it in items]).to(device)
                async with store_lock:
                    base = corpus
                    ids  = list(corpus_ids)
                if base.shape[0] == 0:
                    for (ts, fut, _v) in items:
                        if not fut.done():
                            fut.set_result({
                                'ids': [],
                                'latency_ms':
                                    (time.perf_counter() - ts) * 1000
                            })
                    continue
                # cosine similarity: normalize and matmul
                qn = torch.nn.functional.normalize(vs, dim=1)
                cn = torch.nn.functional.normalize(base, dim=1)
                scores = qn @ cn.T  # [B, N]
                topv, topi = torch.topk(
                    scores,
                    k=min(K, cn.shape[0]),
                    dim=1
                )
                torch.mps.synchronize()
                now = time.perf_counter()
                for row,(ts, fut, _v) in enumerate(items):
                    result = [
                        {
                            'id': ids[int(i)],
                            'score': float(s)
                        }
                        for s,i in zip(
                            topv[row].tolist(),
                            topi[row].tolist()
                        )
                    ]
                    if not fut.done():
                        fut.set_result({
                            'ids': result,
                            'latency_ms': (now - ts) * 1000,
                        })
        finally:
            q_queue.task_done()


if __name__ == '__main__':
    uvicorn.run(app, host=host, port=8080, log_level='warning')
