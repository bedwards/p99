import asyncio, time, httpx

host = '192.168.1.121'

async def one_request(client, delay, payload):
    if delay: await asyncio.sleep(delay)
    return await client.post(
        f'http://{host}:8080/infer',
        json=payload
    )

async def hedged_call(client, hedge_ms=30):
    t0 = time.perf_counter()
    task1 = asyncio.create_task(one_request(
        client,
        0,
        {'x': 1},
    ))
    task2 = asyncio.create_task(one_request(
        client,
        hedge_ms / 1000.0,
        {'x': 1},
    ))
    done, pending = await asyncio.wait(
        {task1, task2},
        return_when=asyncio.FIRST_COMPLETED
    )
    winner = done.pop()
    for p in pending:
        p.cancel()
    t1 = time.perf_counter()
    return (t1 - t0) * 1000.0, (await winner).json()

async def demo(n=200, hedge_ms=30):
    async with httpx.AsyncClient(timeout=5.0) as client:
        ls = []
        for _ in range(n):
            l,_ = await hedged_call(client, hedge_ms)
            ls.append(l)
        import numpy as np
        arr = np.array(ls)
        for q in [50,95,99]: print(q, np.percentile(arr,q))

if __name__ == '__main__':
    asyncio.run(demo())
