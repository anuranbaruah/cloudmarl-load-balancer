"""Regional load balancer = one MARL agent.

Every region (Mumbai, Singapore, Frankfurt, Virginia) runs one container of
this service. It receives Poisson user traffic and must pick a worker VM for
each job.

MODE=marl   : independent Q-learning agent (qlearning.py), the proposed method
MODE=rr     : round-robin baseline (capacity-blind, no health checks)
MODE=random : random baseline

Every 100 ms the balancer polls each worker's /load. That snapshot is the
agent's state. NET_MS emulates the network delay from this region to each
worker so the whole experiment runs on one laptop.
"""
import asyncio
import os
import random
import time
from collections import deque

import httpx

from qlearning import QLearner, encode

REGION = os.getenv("REGION", "mumbai")
MODE = os.getenv("MODE", "marl").lower()
WORKERS = os.getenv("WORKERS", ",".join(
    f"http://localhost:{p}" for p in range(8101, 8106))).split(",")
NET_MS = [float(x) for x in os.getenv("NET_MS", "30,50,120,20,150").split(",")]
RATE = float(os.getenv("RATE", "17"))            # jobs per second into this region
CLOUD_URL = os.getenv("CLOUD_URL", "http://localhost:8000")
DROP_PENALTY_S = 5.0
REPORT_EVERY_S = 2

agent = QLearner(len(WORKERS))
loads = [{"name": f"w{i}", "inflight": 0, "cap": 1, "up": True} for i in range(len(WORKERS))]
records = []                       # job results waiting to be sent to the cloud
recent = deque(maxlen=300)         # last ~20 s of (latency_ms, ok, worker) for the log line
rr_next = 0
tasks = set()                      # keeps running job tasks referenced


def choose(state) -> int:
    global rr_next
    if MODE == "random":
        return random.randrange(len(WORKERS))
    if MODE == "rr":
        rr_next = (rr_next + 1) % len(WORKERS)
        return rr_next
    return agent.choose(state)


# ---------------------------------------------------------------- state
async def probe(http):
    async def one(i, url):
        try:
            r = await http.get(f"{url}/load", timeout=1)
            new = r.json()
        except (httpx.HTTPError, ValueError):
            new = {**loads[i], "up": False}
        if MODE == "marl" and new["up"] != loads[i]["up"]:
            agent.eps = max(agent.eps, 0.3)   # health change -> re-explore
        loads[i] = new

    while True:
        await asyncio.gather(*(one(i, u) for i, u in enumerate(WORKERS)))
        await asyncio.sleep(0.1)


# ---------------------------------------------------------------- jobs
async def handle(http):
    s = encode(loads)
    a = choose(s)
    loads[a]["inflight"] += 1          # count our own job until the next probe
    t0 = time.perf_counter()
    try:
        await asyncio.sleep(NET_MS[a] / 1000)        # emulated network delay
        r = await http.post(f"{WORKERS[a]}/job", timeout=5)
        ok = r.status_code == 200
    except httpx.HTTPError:
        ok = False
    latency = (time.perf_counter() - t0) * 1000
    if MODE == "marl":
        reward = -(latency / 1000) if ok else -DROP_PENALTY_S
        agent.update(s, a, reward, encode(loads))
    worker = loads[a]["name"]
    recent.append((latency, ok, worker))
    records.append({"ts": time.time(), "mode": MODE, "region": REGION,
                    "worker": worker, "latency_ms": round(latency, 1), "ok": ok,
                    "epsilon": round(agent.eps, 3) if MODE == "marl" else None})


async def traffic(http):
    while True:
        await asyncio.sleep(random.expovariate(RATE))
        t = asyncio.create_task(handle(http))
        tasks.add(t)
        t.add_done_callback(tasks.discard)


# ---------------------------------------------------------------- reporting
async def report(http):
    n = 0
    while True:
        await asyncio.sleep(REPORT_EVERY_S)
        batch, records[:] = records[:], []
        if batch:
            try:
                await http.post(f"{CLOUD_URL}/records", json=batch, timeout=5)
            except httpx.HTTPError as e:
                print("cloud unreachable:", type(e).__name__)
        n += 1
        if n % 5 == 0 and recent:
            good = [l for l, ok, _ in recent if ok]
            avg = sum(good) / len(good) if good else 0
            drops = 1 - len(good) / len(recent)
            share = {}
            for _, _, wk in recent:
                share[wk] = share.get(wk, 0) + 1
            mix = " ".join(f"{k}:{100 * v // len(recent)}%" for k, v in sorted(share.items()))
            print(f"[{REGION}] mode={MODE} eps={agent.eps:.2f} avg={avg:.0f}ms "
                  f"drops={drops:.1%} routing {mix}", flush=True)


async def main():
    print(f"Balancer {REGION}: MODE={MODE} RATE={RATE}/s NET_MS={NET_MS}", flush=True)
    limits = httpx.Limits(max_connections=1000, max_keepalive_connections=100)
    async with httpx.AsyncClient(limits=limits) as http:
        await asyncio.gather(probe(http), traffic(http), report(http))


if __name__ == "__main__":
    asyncio.run(main())
