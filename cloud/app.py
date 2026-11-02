"""Cloud API (FastAPI + PostgreSQL): collects job results from all balancers.

Endpoints
  GET  /health              liveness check
  POST /records             batch of finished jobs from one balancer
  GET  /summary?warmup_s=60 experiment results per mode (skips warm-up)
  POST /reset               clear the table (between experiment runs)
"""
import os
import threading
import time
from datetime import datetime, timezone

import psycopg
from fastapi import FastAPI

DB_URL = os.getenv("DATABASE_URL",
                   "postgresql://cloudmarl:cloudmarl@localhost:5432/cloudmarl")

app = FastAPI(title="CloudMARL Cloud API")
_conn = None
_lock = threading.Lock()


def db():
    global _conn
    if _conn is None or _conn.closed:
        for _ in range(30):
            try:
                _conn = psycopg.connect(DB_URL, autocommit=True)
                break
            except psycopg.OperationalError:
                time.sleep(1)
    return _conn


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/records")
def records(batch: list[dict]):
    rows = [(datetime.fromtimestamp(r["ts"], tz=timezone.utc), r["mode"], r["region"],
             r["worker"], r["latency_ms"], r["ok"], r.get("epsilon")) for r in batch]
    with _lock, db().cursor() as cur:
        cur.executemany("""INSERT INTO jobs (ts, mode, region, worker, latency_ms, ok, epsilon)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)""", rows)
    return {"ok": True, "stored": len(rows)}


@app.get("/summary")
def summary(warmup_s: float = 60):
    with _lock:
        cur = db().execute("""
            WITH start AS (SELECT mode, min(ts) AS t0 FROM jobs GROUP BY mode),
                 j AS (SELECT jobs.* FROM jobs JOIN start USING (mode)
                       WHERE jobs.ts >= start.t0 + make_interval(secs => %s))
            SELECT mode, count(*),
                   avg(latency_ms) FILTER (WHERE ok),
                   percentile_cont(0.5)  WITHIN GROUP (ORDER BY latency_ms) FILTER (WHERE ok),
                   percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) FILTER (WHERE ok),
                   avg(CASE WHEN ok THEN 0 ELSE 1 END)
            FROM j GROUP BY mode""", (warmup_s,))
        modes = {r[0]: {"jobs": r[1], "avg_latency_ms": r[2], "median_latency_ms": r[3],
                        "p95_latency_ms": r[4], "drop_rate": float(r[5])}
                 for r in cur.fetchall()}
        cur = db().execute("""
            SELECT region, worker, count(*) FROM jobs
            WHERE mode = 'marl' AND ts >= (SELECT max(ts) FROM jobs WHERE mode = 'marl') - interval '60 seconds'
            GROUP BY region, worker ORDER BY region, worker""")
        routing = {}
        for region, worker, n in cur.fetchall():
            routing.setdefault(region, {})[worker] = n
    return {"modes": modes, "marl_routing_last_60s": routing}


@app.post("/reset")
def reset():
    with _lock:
        db().execute("TRUNCATE jobs RESTART IDENTITY")
    return {"ok": True}
