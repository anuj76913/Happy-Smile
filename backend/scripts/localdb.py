"""Run a private Postgres cluster for local development and tests.

Uses the Postgres binaries on PATH (initdb, pg_ctl). Data lives in backend/.localdb
(git-ignored) and the server listens on 127.0.0.1:54329 with local trust auth, so it
never touches any other Postgres on the machine.

Usage:
    python scripts/localdb.py init     # create the cluster and the happysmile database
    python scripts/localdb.py start
    python scripts/localdb.py stop
    python scripts/localdb.py status

Then: DATABASE_URL=postgresql://postgres@127.0.0.1:54329/happysmile
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / ".localdb" / "data"
LOG = ROOT / ".localdb" / "postgres.log"
PORT = 54329


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(list(args), check=check, capture_output=True, text=True)


def need(binary: str) -> str:
    path = shutil.which(binary)
    if not path:
        sys.exit(f"{binary} not found on PATH. Install PostgreSQL 15+ or use Docker (see README).")
    return path


def status() -> bool:
    if not DATA.exists():
        return False
    return run(need("pg_ctl"), "status", "-D", str(DATA), check=False).returncode == 0


def start() -> None:
    if status():
        print(f"Already running on port {PORT}.")
        return
    # Don't capture output: on Windows the server inherits pg_ctl's pipes and the
    # call would wait for them to close, i.e. forever.
    subprocess.run([need("pg_ctl"), "start", "-D", str(DATA), "-l", str(LOG), "-w",
                    "-o", f"-p {PORT} -c listen_addresses=127.0.0.1"],
                   check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"Started Postgres on 127.0.0.1:{PORT}.")


def init() -> None:
    if DATA.exists():
        print("Cluster already exists.")
    else:
        DATA.parent.mkdir(parents=True, exist_ok=True)
        run(need("initdb"), "-D", str(DATA), "-U", "postgres", "--auth=trust", "-E", "UTF8", "--locale=C")
        print("Initialised cluster.")
    start()
    for _ in range(20):
        r = run(need("psql"), "-h", "127.0.0.1", "-p", str(PORT), "-U", "postgres", "-tAc",
                "SELECT 1 FROM pg_database WHERE datname='happysmile'", check=False)
        if r.returncode == 0:
            break
        time.sleep(0.5)
    if r.stdout.strip() != "1":
        run(need("psql"), "-h", "127.0.0.1", "-p", str(PORT), "-U", "postgres", "-c", "CREATE DATABASE happysmile")
        print("Created database happysmile.")
    print(f"DATABASE_URL=postgresql://postgres@127.0.0.1:{PORT}/happysmile")


def stop() -> None:
    if status():
        run(need("pg_ctl"), "stop", "-D", str(DATA), "-m", "fast")
        print("Stopped.")
    else:
        print("Not running.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    {"init": init, "start": start, "stop": stop,
     "status": lambda: print("running" if status() else "stopped")}.get(cmd, lambda: sys.exit(__doc__))()
