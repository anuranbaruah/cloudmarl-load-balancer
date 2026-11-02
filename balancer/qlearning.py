"""Tabular Q-learning for one regional load balancer (one MARL agent).

Each region runs its own copy. Agents never share Q-tables or talk to each
other; they only see the load of the workers and their own rewards. That is
what makes this *independent* multi-agent RL: the other agents are part of
each agent's (changing) environment.

    state  : load bucket of every worker   (0 idle, 1 busy, 2 saturated/down)
    action : index of the worker that gets the job
    reward : -(job latency in seconds), or -DROP_PENALTY_S if the job failed

    Q(s,a) <- Q(s,a) + alpha * [ r + gamma * max_a' Q(s',a') - Q(s,a) ]
"""
import random
from collections import defaultdict


def bucket(load: dict) -> int:
    if not load["up"]:
        return 2
    ratio = load["inflight"] / load["cap"]
    return 0 if ratio < 0.75 else 1 if ratio < 1.5 else 2


def encode(loads: list) -> tuple:
    return tuple(bucket(l) for l in loads)


class QLearner:
    def __init__(self, n_actions, alpha=0.1, gamma=0.3,
                 eps=1.0, eps_min=0.02, decay=0.995):
        self.n = n_actions
        self.alpha, self.gamma = alpha, gamma
        self.eps, self.eps_min, self.decay = eps, eps_min, decay
        # all-zero start is optimistic (rewards are negative), so untried
        # actions get tried even when exploration is low
        self.q = defaultdict(lambda: [0.0] * n_actions)

    def choose(self, s) -> int:
        if random.random() < self.eps:
            a = random.randrange(self.n)
        else:
            row = self.q[s]
            a = max(range(self.n), key=row.__getitem__)
        self.eps = max(self.eps_min, self.eps * self.decay)
        return a

    def update(self, s, a, reward, s2):
        row = self.q[s]
        row[a] += self.alpha * (reward + self.gamma * max(self.q[s2]) - row[a])
