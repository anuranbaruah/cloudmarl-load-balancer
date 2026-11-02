"""Run the whole CloudMARL stack on Windows without Docker.

    python run_local.py

The first run downloads Python 3.12 (via uv), the Python packages, a portable
PostgreSQL (pgserver) and a portable Grafana into .local/ (about 400 MB, a few
minutes). After that it starts in seconds.

It starts Postgres, the cloud API, 5 worker VMs, 4 MARL load balancers and
Grafana, opens the dashboard, and prints each agent's progress every 10 s.
Ctrl+C stops everything. Set MODE (marl | rr | random) or RATE in the
environment to change the policy or the load, e.g.  $env:MODE="rr"
"""
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOCAL = ROOT / ".local"
LOGS = LOCAL / "logs"
BIN = "Scripts/python.exe" if os.name == "nt" else "bin/python"
VENV_PY = LOCAL / "venv" / BIN
GRAFANA_VER = "11.2.0"
GRAFANA_DIR = LOCAL / f"grafana-v{GRAFANA_VER}"
PACKAGES = ["fastapi==0.115.0", "uvicorn==0.30.6", "httpx==0.27.2",
            "psycopg[binary]==3.2.3", "pgserver==0.1.4", "matplotlib"]

# same VMs and regions as docker-compose.yml
WORKERS = [("vm-xl", 7), ("vm-l", 5), ("vm-m", 4), ("vm-s1", 2), ("vm-s2", 2)]
REGIONS = {"mumbai": "30,50,120,20,150", "singapore": "40,30,100,80,140",
           "frankfurt": "100,120,30,110,50", "virginia": "140,150,60,160,20"}


def setup():
    ready = LOCAL / "venv-ready"
    if not ready.exists():
        print("First run: installing Python 3.12 and packages into .local/ ...")
        boot = LOCAL / "bootstrap"
        subprocess.check_call([sys.executable, "-m", "venv", boot])
        uv = [boot / BIN, "-m", "uv"]
        subprocess.check_call([boot / BIN, "-m", "pip", "install", "-q", "uv"])
        subprocess.check_call(uv + ["venv", "-q", "--allow-existing", "--python", "3.12", LOCAL / "venv"])
        subprocess.check_call(uv + ["pip", "install", "-q", "--python", VENV_PY, *PACKAGES])
        ready.touch()
    if os.name == "nt" and not GRAFANA_DIR.exists():
        print(f"Downloading Grafana {GRAFANA_VER} (~150 MB) ...")
        zip_path = LOCAL / "grafana.zip"
        urllib.request.urlretrieve(
            f"https://dl.grafana.com/oss/release/grafana-{GRAFANA_VER}.windows-amd64.zip", zip_path)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(LOCAL)
        zip_path.unlink()


def wait_for(url, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except OSError:
            time.sleep(1)
    raise RuntimeError(f"{url} did not start; check the logs in {LOGS}")


def write_grafana_provisioning(db_port):
    prov = LOCAL / "grafana-provisioning"
    (prov / "datasources").mkdir(parents=True, exist_ok=True)
    (prov / "dashboards").mkdir(exist_ok=True)
    (prov / "datasources" / "local.yml").write_text(f"""apiVersion: 1
datasources:
  - name: CloudMARLDB
    uid: cloudmarl-db
    type: grafana-postgresql-datasource
    access: proxy
    url: 127.0.0.1:{db_port}
    user: postgres
    isDefault: true
    secureJsonData: {{ password: local }}
    jsonData: {{ database: postgres, sslmode: disable, postgresVersion: 1600 }}
""")
    (prov / "dashboards" / "local.yml").write_text(f"""apiVersion: 1
providers:
  - name: CloudMARL
    folder: CloudMARL
    type: file
    options: {{ path: "{(ROOT / 'grafana' / 'dashboards').as_posix()}" }}
""")
    return prov


def run():
    import pgserver   # only installed in .local/venv

    LOGS.mkdir(parents=True, exist_ok=True)
    procs = []

    def start(name, args, cwd=ROOT, **env):
        log = open(LOGS / f"{name}.log", "w")
        procs.append(subprocess.Popen(args, cwd=cwd, env={**os.environ, **env},
                                      stdout=log, stderr=subprocess.STDOUT))

    print("Starting PostgreSQL ...")
    pg = pgserver.get_server(LOCAL / "pgdata", cleanup_mode="stop")   # stops when we exit
    pg.psql((ROOT / "db" / "init.sql").read_text())
    db_url = pg.get_uri()
    try:
        print("Starting cloud API and worker VMs ...")
        start("cloud", [sys.executable, "-m", "uvicorn", "app:app", "--app-dir", "cloud",
                        "--host", "127.0.0.1", "--port", "8000"], DATABASE_URL=db_url)
        for i, (name, cap) in enumerate(WORKERS):
            start(name, [sys.executable, "-m", "uvicorn", "worker:app", "--app-dir", "worker",
                         "--host", "127.0.0.1", "--port", str(8101 + i)],
                  NAME=name, CAPACITY=str(cap))
        wait_for("http://127.0.0.1:8000/health")
        for i in range(len(WORKERS)):
            wait_for(f"http://127.0.0.1:{8101 + i}/load")

        mode = os.getenv("MODE", "marl")
        print(f"Starting 4 load balancers (MODE={mode}) ...")
        workers = ",".join(f"http://127.0.0.1:{8101 + i}" for i in range(len(WORKERS)))
        for region, net in REGIONS.items():
            start(f"lb-{region}", [sys.executable, "-u", "balancer/balancer.py"],
                  REGION=region, NET_MS=net, WORKERS=workers, MODE=mode,
                  RATE=os.getenv("RATE", "17"), CLOUD_URL="http://127.0.0.1:8000")

        dashboard = "http://localhost:3000/d/cloudmarl-main"
        if GRAFANA_DIR.exists():
            print("Starting Grafana ...")
            prov = write_grafana_provisioning(db_url.rsplit(":", 1)[1].split("/")[0])
            gdata = LOCAL / "grafana-data"
            gdata.mkdir(exist_ok=True)   # Grafana won't create it on Windows
            start("grafana", [GRAFANA_DIR / "bin" / "grafana-server.exe", "--homepath", GRAFANA_DIR],
                  cwd=GRAFANA_DIR,
                  GF_PATHS_PROVISIONING=str(prov), GF_PATHS_DATA=str(gdata),
                  GF_PATHS_LOGS=str(gdata / "log"), GF_SERVER_HTTP_ADDR="127.0.0.1", GF_SERVER_HTTP_PORT="3000",
                  GF_AUTH_ANONYMOUS_ENABLED="true", GF_AUTH_ANONYMOUS_ORG_ROLE="Viewer",
                  GF_SECURITY_ADMIN_PASSWORD="admin",
                  GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH=str(ROOT / "grafana" / "dashboards" / "cloudmarl.json"))
            wait_for("http://127.0.0.1:3000/api/health")
            webbrowser.open(dashboard)

        print(f"""
CloudMARL is running.
  Dashboard   : {dashboard}   (admin / admin to edit)
  Cloud API   : http://localhost:8000/docs
  Crash a VM  : curl.exe -X POST localhost:8105/fail    (/recover to undo)
  Logs        : {LOGS}
Press Ctrl+C to stop everything.
""")
        while True:
            time.sleep(10)
            for region in REGIONS:
                lines = [l for l in (LOGS / f"lb-{region}.log").read_text().splitlines()
                         if l.startswith("[")]
                if lines:
                    print(lines[-1])
            print()
    except KeyboardInterrupt:
        print("Stopping ...")
    finally:
        for p in procs:
            p.terminate()


if __name__ == "__main__":
    if "--run" in sys.argv:
        run()
    else:
        LOCAL.mkdir(exist_ok=True)
        setup()
        child = subprocess.Popen([VENV_PY, __file__, "--run"])
        while True:
            try:
                sys.exit(child.wait())
            except KeyboardInterrupt:
                pass   # the child also gets Ctrl+C and shuts everything down cleanly
