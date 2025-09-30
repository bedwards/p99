At the outset, what interested me wasn’t speed for its own sake but the way systems reveal themselves under strain. Averages are polite, orderly, misleading. What matters are the stutters and hesitations, the invisible delays that reshape the entire experience. By nudging small programs into situations where they occasionally faltered, I could watch those hidden contours come into view—how efficiency can buckle, how waiting accumulates in places we don’t expect.

I began with the most stripped-down experiment possible: a single GPU operation that almost always returns instantly but sometimes drags its feet. The averages looked fine, of course, but when I plotted the distribution the shape was different. A fattened tail, a kind of shadow in the numbers, gave away what the mean could never confess.

See `tail_gpu.py`.

```
count=500  p50=0.41ms  p95=0.48ms  p99=6.78ms  max=50.91ms
```

From there, I tried to dress the thing up like a service. Requests go into a queue, the GPU works on them in batches, and the whole rhythm starts to look familiar. Throughput soars, but latency grows teeth. The system isn’t lying exactly, but it is revealing how easily efficiency can become waiting.

Numbers mean nothing if you don’t measure them honestly. So I built a generator that sends requests at a steady cadence and records the true delay from when each request should have started. No shortcuts, no wishful thinking. The curves came back sharper, less forgiving, but also more real.

See `batch_service_orig.py` and `loadgen.py`.

```
loadgen -> batch_service_orig
n=2780 p50=23003.13ms p95=43909.12ms p99=45678.59ms p99.9=46071.81ms
```

That gave me the excuse to push the batching service further. I added limits, guardrails, and the ability to say “no” when the queue was already choking. Sometimes refusal is mercy. The results told a story of restraint: fewer requests overall, but a healthier distribution for the ones that got through.

See `batch_service_patched.py`.

```
loadgen -> batch_service_patched
n=2746 p50=23805.95ms p95=43876.35ms p99=45809.66ms p99.9=46268.42ms
```

Of course, not every request has to wait patiently. I added a little trick—send a backup if the first call takes too long, cancel whichever one loses the race. The results were uncanny: the worst-case scenarios softened, the system felt quicker, even though nothing fundamental had changed. A reminder that sometimes perception is architecture.

See `hedged_client.py`.

```
hedged_client -> batch_service_orig
p50=20.13ms p95=22.09ms p99=29.55ms p99.9=205.83ms

hedged_client -> batch_service_patched
p50=20.45ms p95=23.81ms p99=107.93ms p99.9=219.49ms
```

Finally I built something closer to what I actually use day to day: a lightweight vector search, running entirely on the GPU, able to accept inserts and queries in real time. It isn’t a product, but it’s enough to feel the tension between batching for speed and protecting each request from being swallowed by the crowd. And in that tension lies the whole game.

See `vecserve.py`.

```
hedged_client -> vecserve
p50=7.25ms p95=8.95ms p99=10.57ms p99.9=53.92ms
```

In the end, I was left with a series of sketches rather than a finished machine: fragments of code and traces of output that capture the difference between what looks smooth and what actually feels rough. Each step opened a small window onto the mechanics of modern computation, the tradeoffs we inherit when we chase performance. The lesson wasn’t about any single technique but about noticing what the numbers try to hide, and how much is revealed once you refuse to look away.