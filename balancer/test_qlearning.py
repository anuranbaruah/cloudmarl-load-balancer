"""Unit tests for the Q-learning module.  Run:  cd balancer && python -m pytest"""
import random

from qlearning import QLearner, bucket, encode


def w(inflight, cap=4, up=True):
    return {"inflight": inflight, "cap": cap, "up": up}


def test_buckets():
    assert bucket(w(0)) == 0          # idle
    assert bucket(w(4)) == 1          # all slots busy
    assert bucket(w(12)) == 2         # long queue
    assert bucket(w(0, up=False)) == 2  # down counts as saturated


def test_encode_is_one_bucket_per_worker():
    assert encode([w(0), w(4), w(0, up=False)]) == (0, 1, 2)


def test_update_rule():
    q = QLearner(2, alpha=0.5, gamma=0.0)
    q.update("s", 1, -2.0, "s2")
    assert q.q["s"] == [0.0, -1.0]


def test_learns_fastest_worker():
    random.seed(1)
    latency = [1.0, 0.2, 2.0]          # worker 1 is fastest
    q = QLearner(3, decay=0.98)
    for _ in range(600):
        a = q.choose("s")
        q.update("s", a, -latency[a], "s")
    q.eps = 0
    assert q.choose("s") == 1
