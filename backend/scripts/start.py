"""Container entry point: migrate (retrying until the database is ready), seed, serve.

Written in Python rather than shell so it also works if the files were edited on
Windows (CRLF line endings break shell scripts inside Linux containers).
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(cmd):
    return subprocess.call(cmd, cwd=HERE)


for attempt in range(1, 31):
    if run([sys.executable, "-m", "alembic", "upgrade", "head"]) == 0:
        break
    print(f"Database not ready (attempt {attempt}/30) - retrying in 2 s", flush=True)
    time.sleep(2)
else:
    sys.exit("Could not run database migrations - is the database reachable?")

if run([sys.executable, "scripts/seed.py"]) != 0:
    sys.exit("Seeding failed")

# One worker on purpose: facility downloads run as in-process background tasks.
os.chdir(HERE)
port = os.environ.get("PORT", "8000")
os.execv(sys.executable, [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", port,
                          "--proxy-headers", "--forwarded-allow-ips", "*"])
