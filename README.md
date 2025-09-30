Let’s start at ground zero. “P99” is shorthand for the 99th-percentile latency of a system: if your p99 is 420 ms, then 99% of requests finish faster than 420 ms and the slowest 1% are at least that slow. That tail matters because users are often gated by the slowest calls in a page, and large, fan-out systems multiply small hiccups into visible slowness. Jeff Dean and Luiz André Barroso gave this a name—“the tail at scale”—and showed why rare hiccups dominate real experiences in distributed systems. You don’t fix the tail by admiring averages; you design to tolerate it. ([Google Research][1])

Think of latency percentiles as a portrait of time-to-answer. The median (p50) describes the “typical” request; p95 and p99 expose the long tail; p999 reveals the pathological cases. The opposite mindset is mean-time myopia: celebrating a lovely average while the tail quietly ruins real user flows. In practice you anchor percentiles to reliability goals—SLOs that say something like “90% under 100 ms, 99% under 400 ms”—so you capture both the common case and the tail that users actually feel. ([Google SRE][2])

Measurement is subtle. If your load generator waits for each request to finish before sending the next, it “coordinates” with the system under test and fails to notice time that should have been spent issuing new requests. Gil Tene called this trap coordinated omission, and it can make a sick system look healthy. The antidote is constant-rate load with latency measured from when a request should have been sent, not when it actually left. Tools like wrk2 and Vegeta do exactly this. ([YouTube][3])

That’s the mental frame for P99 CONF itself: a gathering for people who obsess over high-performance, low-latency systems and the tools and ideas around them. This year’s event is virtual on October 22–23, 2025, and the site highlights its focus on p99 thinking end-to-end. If you want a canonical reading pack before you tune in, “The Tail at Scale,” Google’s SRE workbook chapters on SLOs, and Tene’s talk are the spine. ([P99 CONF][4])

You asked for a project with fast, blog-worthy results on your Mac Studio using Python (plus a little Rust). Here’s a compact “Tail-Latency Lab” that you can grow over an afternoon and that yields graphs and insights almost immediately.

Begin with the smallest possible service that produces a deliberate heavy tail. A tiny local HTTP endpoint that returns quickly 99% of the time but stalls for a few hundred milliseconds 1% of the time is enough to make p50 look fine while p99 goes to pieces. Then hit it with a constant-rate load generator, record a high-dynamic-range latency histogram, and narrate what the numbers mean. HDR Histograms give you consistent, mergeable percentiles across many orders of magnitude, which is why they show up in serious latency work. ([hdrhistogram.github.io][5])

Here is a fast Python server that manufactures a tail. It uses FastAPI and asyncio; install with `pip install fastapi uvicorn`.

```python
# server.py
import asyncio, random
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

app = FastAPI()

@app.get("/work", response_class=PlainTextResponse)
async def work():
    r = random.random()
    if r < 0.99:
        await asyncio.sleep(random.uniform(0.001, 0.003))   # ~1–3 ms
    else:
        await asyncio.sleep(random.uniform(0.200, 0.600))   # 200–600 ms tail
    return "ok"
```

Run it with `uvicorn server:app --host 127.0.0.1 --port 8000`.

Now drive it with a constant-rate Python load generator that accounts for coordinated omission. Install `httpx` and `hdrhistogram` with `pip install httpx hdrhistogram`. The generator schedules requests at a fixed cadence and measures each response against its scheduled send time, not the moment the packet left.

```python
# loadgen.py
import asyncio, time
import httpx
from hdrhistogram import HdrHistogram

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
    asyncio.run(attack("http://127.0.0.1:8000/work", rate=200, duration_s=20))
```

With those two files you already have a p50 that looks pristine and a p99 that exposes the engineered mischief. That is your 15-minute story: “the average lies; the tail tells the truth.” If you want to compare with a battle-tested tool, install wrk2 or Vegeta via Homebrew and run a quick constant-rate attack; both are designed to avoid coordinated omission and will report convincing percentiles for your blog screenshots. ([GitHub][6])

At the half-hour mark, enrich the narrative: keep the same server but vary the slow-path probability and magnitude, then show how p95 changes little while p99 and p99.9 explode. Tie this to an SLO example—say, “90% under 100 ms, 99% under 400 ms”—and show which dial violates which promise. Readers love the moment when they see a perfect median sitting next to a failing p99 and finally understand why teams negotiate multi-threshold SLOs. ([Google SRE][2])

Give yourself an hour and swap the server for Rust to flex different tooling and to lean into the P99 vibe. Axum on Tokio makes this tiny and fast. Create a new project with `cargo new tail_lab`, add `axum`, `tokio`, and `rand` to `Cargo.toml`, and use this `main.rs`:

```rust
// src/main.rs
use axum::{routing::get, Router, response::IntoResponse};
use rand::Rng;
use std::time::Duration;
use tokio::time::sleep;

async fn work() -> impl IntoResponse {
    let mut rng = rand::thread_rng();
    let roll: f64 = rng.gen();
    let delay_ms = if roll < 0.99 {
        rng.gen_range(1..=3)
    } else {
        rng.gen_range(200..=600)
    };
    sleep(Duration::from_millis(delay_ms)).await;
    "ok"
}

#[tokio::main]
async fn main() {
    let app = Router::new().route("/work", get(work));
    let listener = tokio::net::TcpListener::bind("127.0.0.1:9000").await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
```

Point your Python load generator at `http://127.0.0.1:9000/work` and repeat the measurements. If you want to store and merge precise histograms across runs or languages, the Rust `hdrhistogram` crate gives you interoperable HdrHistogram snapshots you can serialize for later comparison. It’s a nice segue into “percentiles across stacks” as a blog section. ([GitHub][7])

With two hours you can move from observation to mitigation. Add client-side timeouts and retries with jitter to your Python load generator and show how a naive “retry immediately” can amplify tail latency by piling work onto an already sick server, while a capped, jittered retry can improve perceived p99. Then flip to the server and introduce a concurrency limiter or queue threshold that returns a fast “please try later,” and show how protecting the core improves the tail for everyone still admitted. You’re now telling a SRE-flavored story about shaping load to meet percentile SLOs instead of trying to wish the tail away. ([Google SRE][2])

Give yourself four hours and close with a small, polished artifact. Record histograms to disk on every run, render a simple PNG percentile plot, and publish a write-up that starts with the naïve mean, moves to p99 and p999, demonstrates coordinated omission with a bad generator, fixes it with constant-rate measurement, and ends with a before/after mitigation graph. If you want even cleaner tooling for the plot and the constant-throughput attacks, capture a `wrk2` run at a fixed rate and paste its histogram into the post alongside your HDR results; explain why the two line up and what’s different about the methodology. That’s a complete arc from first principles to practice, and it lands directly in the center of what P99 CONF attendees care about. ([GitHub][6])

If you want a short reading/watchlist to keep open in browser tabs while you build this lab, keep the P99 CONF site for context, Dean and Barroso’s “Tail at Scale” for the core intuitions, Google’s SRE workbook on multi-threshold latency SLOs for the language of reliability, Tene’s “How NOT to Measure Latency” for the measurement traps, and the HdrHistogram docs for exactly what the histograms are doing under the hood. With those in hand, your post will both show and cite the right things. ([P99 CONF][4])

When you’re ready, we can turn this into a single, reproducible repo—one FastAPI server, one Axum server, one Python loadgen, a Makefile with a few one-liners, and a short markdown narrative—so you can ship the blog and be conference-ready.

[1]: https://research.google/pubs/the-tail-at-scale/?utm_source=chatgpt.com "The Tail at Scale"
[2]: https://sre.google/workbook/implementing-slos/?utm_source=chatgpt.com "Chapter 2 - Implementing SLOs"
[3]: https://www.youtube.com/watch?v=lJ8ydIuPFeU&utm_source=chatgpt.com "\"How NOT to Measure Latency\" by Gil Tene"
[4]: https://www.p99conf.io/?utm_source=chatgpt.com "P99 CONF 2025 - The Event on All Things Performance"
[5]: https://hdrhistogram.github.io/HdrHistogram/?utm_source=chatgpt.com "HdrHistogram by giltene"
[6]: https://github.com/giltene/wrk2?utm_source=chatgpt.com "GitHub - giltene/wrk2: A constant throughput, correct ..."
[7]: https://github.com/HdrHistogram/HdrHistogram_rust?utm_source=chatgpt.com "A port of HdrHistogram to Rust - GitHub"
