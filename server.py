import asyncio, random
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

app = FastAPI()

@app.get("/work", response_class=PlainTextResponse)
async def work():
    r = random.random()
    if r < 0.99:
        await asyncio.sleep(random.uniform(0.001, 0.003))  # ~1–3 ms
    else:
        await asyncio.sleep(random.uniform(0.200, 0.600))  # 200–600 ms tail
    return "ok"
