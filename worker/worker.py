"""Worker VM: runs jobs with CAPACITY parallel slots.

Each job takes a random service time (mean JOB_MS). Jobs beyond the free
slots wait in a queue; if the queue is longer than MAX_QUEUE the job is
rejected with 503 (admission control). POST /fail and /recover simulate a
VM crash for the demo.
"""
import asyncio
import os
import random

from fastapi import FastAPI, Response

NAME = os.getenv("NAME", "vm")
CAPACITY = int(os.getenv("CAPACITY", "4"))
JOB_MS = float(os.getenv("JOB_MS", "200"))
MAX_QUEUE = int(os.getenv("MAX_QUEUE", "40"))

app = FastAPI(title=f"Worker {NAME}")
slots = asyncio.Semaphore(CAPACITY)
inflight = 0
up = True


@app.post("/job")
async def job(response: Response):
    global inflight
    if not up or inflight >= CAPACITY + MAX_QUEUE:
        response.status_code = 503
        return {"ok": False, "worker": NAME}
    inflight += 1
    try:
        async with slots:
            await asyncio.sleep(random.expovariate(1000 / JOB_MS))
    finally:
        inflight -= 1
    return {"ok": True, "worker": NAME}


@app.get("/load")
def load():
    return {"name": NAME, "inflight": inflight, "cap": CAPACITY, "up": up}


@app.post("/fail")
def fail():
    global up
    up = False
    return {"name": NAME, "up": up}


@app.post("/recover")
def recover():
    global up
    up = True
    return {"name": NAME, "up": up}
