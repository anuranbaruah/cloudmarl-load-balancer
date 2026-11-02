"""Compare random vs round-robin vs MARL runs.

Reads results from the cloud API (no extra Python packages needed), prints a
results table, saves experiments/results.csv, and, if matplotlib is
installed, experiments/results.png for your report.

Usage:  python experiments/analyze.py [warmup_seconds]
The first warmup_seconds (default 60) of every run are skipped, so the
MARL agents are measured after they have learned, and the baselines are
measured over the same window.
"""
import csv
import json
import os
import sys
import urllib.request

API = os.getenv("CLOUD_API", "http://localhost:8000")
HERE = os.path.dirname(os.path.abspath(__file__))
NAMES = {"random": "Random", "rr": "Round-robin", "marl": "MARL (Q-learning)"}


def r1(x):
    return round(x, 1) if isinstance(x, (int, float)) else "-"


def main():
    warmup = sys.argv[1] if len(sys.argv) > 1 else "60"
    try:
        with urllib.request.urlopen(f"{API}/summary?warmup_s={warmup}", timeout=10) as resp:
            data = json.load(resp)
    except OSError as e:
        sys.exit(f"Could not reach the cloud API at {API} ({e}). "
                 "Is `docker compose up` running?")

    modes = [m for m in ("random", "rr", "marl") if m in data["modes"]]
    if not modes:
        sys.exit("No data yet. Run the experiment first.")

    rows = []
    for m in modes:
        s = data["modes"][m]
        rows.append({
            "Policy": NAMES[m],
            "Jobs": s["jobs"],
            "Avg latency (ms)": r1(s["avg_latency_ms"]),
            "Median (ms)": r1(s["median_latency_ms"]),
            "P95 (ms)": r1(s["p95_latency_ms"]),
            "Dropped (%)": round(100 * s["drop_rate"], 2),
        })

    cols = list(rows[0])
    widths = [max(len(c), *(len(str(r[c])) for r in rows)) for c in cols]
    print(" | ".join(c.ljust(w) for c, w in zip(cols, widths)))
    print("-+-".join("-" * w for w in widths))
    for r in rows:
        print(" | ".join(str(r[c]).ljust(w) for c, w in zip(cols, widths)))

    with open(os.path.join(HERE, "results.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"\nTable saved to {os.path.join(HERE, 'results.csv')}")

    routing = data["marl_routing_last_60s"]
    if routing:
        workers = sorted({wk for r in routing.values() for wk in r})
        print("\nWhat the MARL agents learned (share of each region's jobs, last 60 s):")
        print("region".ljust(11) + "".join(wk.rjust(8) for wk in workers))
        for region, counts in routing.items():
            total = sum(counts.values())
            print(region.ljust(11) + "".join(
                f"{100 * counts.get(wk, 0) / total:7.0f}%" for wk in workers))

    by = {r["Policy"]: r for r in rows}
    marl = by.get(NAMES["marl"])
    base = [r for r in rows if r is not marl and isinstance(r["Avg latency (ms)"], float)]
    if marl and base and isinstance(marl["Avg latency (ms)"], float):
        best = min(base, key=lambda r: r["Avg latency (ms)"])
        print(f"\nMARL average latency vs best baseline ({best['Policy']}): "
              f"{100 * (1 - marl['Avg latency (ms)'] / best['Avg latency (ms)']):.1f}% lower")

    if len(rows) < 2:
        print("\nOnly one policy has data. Run the experiment script to compare all three.")
        return
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("(Install matplotlib, `pip install matplotlib`, to also get results.png)")
        return
    names = [r["Policy"] for r in rows]
    colors = {"Random": "#999999", "Round-robin": "#d4900f", "MARL (Q-learning)": "#2453d1"}
    c = [colors[n] for n in names]
    fig, ax = plt.subplots(1, 3, figsize=(12, 3.5))
    for i, (col, title) in enumerate([("Avg latency (ms)", "Average latency (ms)"),
                                      ("P95 (ms)", "P95 latency (ms)"),
                                      ("Dropped (%)", "Dropped jobs (%)")]):
        ax[i].bar(names, [r[col] if r[col] != "-" else 0 for r in rows], color=c)
        ax[i].set_title(title)
        ax[i].tick_params(axis="x", labelsize=8)
    fig.tight_layout()
    out = os.path.join(HERE, "results.png")
    fig.savefig(out, dpi=150)
    print(f"Chart saved to {out}")


if __name__ == "__main__":
    main()
