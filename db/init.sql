-- One row per job routed by a regional load balancer
CREATE TABLE IF NOT EXISTS jobs (
    id          BIGSERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL,
    mode        TEXT NOT NULL,              -- 'marl' | 'rr' | 'random'
    region      TEXT NOT NULL,              -- which balancer (agent) routed it
    worker      TEXT NOT NULL,              -- which VM ran it
    latency_ms  DOUBLE PRECISION NOT NULL,  -- balancer -> worker -> done
    ok          BOOLEAN NOT NULL,           -- false = rejected / worker down
    epsilon     DOUBLE PRECISION            -- agent's exploration rate (marl only)
);
CREATE INDEX IF NOT EXISTS idx_jobs_ts ON jobs (ts);
CREATE INDEX IF NOT EXISTS idx_jobs_mode ON jobs (mode, ts);
