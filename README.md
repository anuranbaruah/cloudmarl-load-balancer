# CloudMARL

Multi-agent reinforcement learning for cloud load balancing
(Cloud Computing project).

```
                ┌─ lb-mumbai    (Q-learning agent) ─┐        ┌─ vm-xl  (7 slots)
user traffic ──▶├─ lb-singapore (Q-learning agent) ─┤──HTTP─▶├─ vm-l   (5 slots)
 (Poisson)      ├─ lb-frankfurt (Q-learning agent) ─┤        ├─ vm-m   (4 slots)
                └─ lb-virginia  (Q-learning agent) ─┘        ├─ vm-s1  (2 slots)
                         │ job results                        └─ vm-s2  (2 slots)
                         ▼
                 Cloud API (FastAPI) ──▶ PostgreSQL ──▶ Grafana
```

Four regional load balancers share one pool of five worker VMs of different
sizes. Each balancer is an **independent Q-learning agent**. The agents don't
share Q-tables and don't send each other messages. Each one learns from its own
rewards which VM to send a job to, even though the other three agents keep
changing the load it sees.

## What each folder is

| Folder | What it does |
|---|---|
| `balancer/` | Regional load balancer: generates user traffic, routes jobs, learns. **MARL module: `qlearning.py`** |
| `worker/` | Worker VM: runs jobs with N parallel slots, queues the rest, rejects when the queue is full. Can be crashed and recovered for the demo |
| `cloud/` | FastAPI cloud API: stores every job result, computes the experiment summary |
| `db/` | PostgreSQL schema |
| `grafana/` | Pre-built dashboard (loads automatically) |
| `experiments/` | Script that runs random vs round-robin vs MARL and makes the results table and chart |
| `demo/` | Browser-only simulation of the same idea. Open `demo/index.html`; it needs no Docker. Good for the classroom |

## 1. Run it (one command)

Needs Docker Desktop (Windows/Mac) or Docker Engine (Linux).

```bash
cp .env.example .env
docker compose up -d --build
```

Then open:
- **Grafana dashboard:** http://localhost:3000 → Dashboards → CloudMARL (login `admin` / `admin`)
- **Cloud API docs:** http://localhost:8000/docs
- **Agents learning live:** `docker compose logs -f lb-mumbai lb-virginia`
  (every 10 s each agent prints its ε, average latency, drop rate and where it sends traffic)

Stop everything: `docker compose down` (add `-v` to also wipe the database).

### No Docker? (Windows)

```powershell
python run_local.py
```

The first run downloads Python 3.12, the packages, a portable PostgreSQL and a
portable Grafana into `.local/` (about 400 MB, a few minutes). Later runs start
in seconds. It starts every service, opens the Grafana dashboard and prints each
agent's progress every 10 s. Press **Ctrl+C** to stop everything.
Switch policy with `$env:MODE="rr"` (or `random`) before running.

## 2. The MARL module (the core contribution)

| | Design |
|---|---|
| Agents | 4 load balancers, one per region, each with its own Q-table |
| State | load bucket of each of the 5 VMs: idle / busy / saturated-or-down → 3⁵ = 243 states |
| Action | which VM gets the job (5 actions) |
| Reward | −(job latency in seconds); a rejected or failed job gives −5 |
| Learning | `Q(s,a) ← Q(s,a) + α[r + γ·max Q(s′,a′) − Q(s,a)]`, α = 0.1, γ = 0.3 |
| Exploration | ε-greedy, ε decays 1.0 → 0.02. If a VM goes down or comes back, ε jumps to 0.3 so agents re-explore |

The baselines are what a naive cloud setup does. **Round-robin** and **random**
both ignore VM size and don't run health checks.

Why it is *multi-agent*: the best VM for Mumbai depends on what Singapore,
Frankfurt and Virginia send there at the same moment. From each agent's point
of view the environment is non-stationary. The agents still settle on a
split of the pool without coordinating.

Unit tests: `cd balancer && python -m pytest`

## 3. Live demo in class

1. `docker compose up -d --build`, open Grafana. Watch ε fall and the MARL latency line drop.
2. Show the routing table panel: regions send more traffic to the big VMs and less to the 2-slot VMs.
3. Crash a VM: `curl -X POST localhost:8105/fail` (vm-s2; on Windows PowerShell use `curl.exe`).
   Agents notice through their health probes and route around it. Bring it back with `/recover`.
4. Compare with round-robin: set `MODE=rr` in `.env`, then
   `docker compose up -d --force-recreate lb-mumbai lb-singapore lb-frankfurt lb-virginia`.

Worker ports: vm-xl 8101, vm-l 8102, vm-m 8103, vm-s1 8104, vm-s2 8105.

No Docker available? Open `demo/index.html` in a browser. It runs the same
algorithm as a simulation, with buttons for failures and traffic spikes.

## 4. Run the experiment (for your results section)

```bash
./experiments/run_experiment.sh 180 17     # 180 s per policy, 17 jobs/s per region
```

This runs random, round-robin and MARL one after another, then prints a
table, the routing the MARL agents learned, and `experiments/results.png`.
The first 60 s of every run is skipped (`python experiments/analyze.py 60`) so
MARL is measured after it has learned.

Results from one full run (150 s per policy, 68% load, first 60 s skipped;
services run natively on one Windows laptop with the same code):

| Policy | Jobs | Avg latency | Median | P95 | Dropped |
|---|---|---|---|---|---|
| Random | 5975 | 1422.7 ms | 390.1 ms | 4547.8 ms | 12.69% |
| Round-robin | 5957 | 1469.5 ms | 362.2 ms | 4547.6 ms | 11.25% |
| MARL (Q-learning) | 5896 | 591.8 ms | 326.1 ms | 2633.5 ms | 1.53% |

MARL cut average latency by 58% and dropped jobs from ~12% to 1.5%.
Run it again on your setup and report your own numbers.

Good experiments to add to the report:
1. **Load sweep:** `RATE` = 10, 14, 17, 20 → latency and drops for each policy.
2. **Failure recovery:** crash vm-l mid-run → time until MARL latency recovers.
3. **Learning speed:** change `decay` in `qlearning.py` → time to converge vs final latency.
4. **Scale:** add a fifth region (one more `lb-*` service) → does learning still converge?

> Note: `NET_MS` *emulates* the network delay from each region to each VM so
> the whole system runs on one laptop. Say this clearly in the report. For a
> stronger setup, run workers on separate cloud VMs (AWS EC2 / OpenStack),
> set `NET_MS` to zeros and point `WORKERS` at their addresses.
>
> Crashing vm-l (a quarter of the pool) at `RATE=17` leaves the pool ~91% busy,
> so latency rises for every policy. Use vm-s1 or vm-s2 for a clean demo, or
> lower `RATE`.

## 5. Deploy to the cloud (public live dashboard)

### Option A: GitHub Codespaces (free, no credit card)

1. On the repo page: **Code → Codespaces → Create codespace on main**.
2. Wait 3–5 minutes. The stack builds and starts by itself (`.devcontainer/`).
3. Open the **Ports** tab, right-click port **3000 → Port Visibility → Public**, and copy its URL.
   Anyone with that link can view the live dashboard.
4. Grafana admin password: `grep GRAFANA_ADMIN_PASSWORD .env` in the codespace terminal.

A codespace stops after 30 minutes without activity in the editor. Before a demo, raise this in
GitHub **Settings → Codespaces → Default idle timeout** (max 240 min). Free accounts get about
60 hours a month on a 2-core machine.

### Option B: any Ubuntu VM

The full stack runs on any Ubuntu VM with one command.

1. Create an **Ubuntu 24.04** VM with at least 2 vCPU / 2–4 GB RAM.
   Examples: Azure `Standard_B2s` (Azure for Students gives free credit),
   AWS EC2 `t3.small`, Google Cloud `e2-medium`.
2. In the VM's firewall / security group, allow inbound **TCP 22** (SSH) and **TCP 3000** (dashboard).
   Don't open any other port.
3. SSH in and run:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/anuranbaruah/cloudmarl-load-balancer/main/deploy/setup-vm.sh | bash
   ```
4. It prints the public dashboard URL `http://<VM-IP>:3000` and a random Grafana admin password.

Visitors get the dashboard read-only. The cloud API, workers and database
are bound to the VM's localhost, so nobody outside can reset data or crash
VMs. To run the failure demo, SSH in and use `curl -X POST localhost:8105/fail`.

Stop (deallocate) the VM after your demo so it doesn't use up your credit.

## 6. Optional extensions (if time permits)

- **Kubernetes:** `kompose convert`, deploy on minikube / k3s, scale workers with `kubectl scale`.
- **Shared reward:** give every agent the average latency of all regions (cooperative MARL) and compare with independent learners.
- **Deep RL:** replace the Q-table with a small neural network (DQN) to handle more VMs.
