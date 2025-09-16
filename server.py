import os
import threading
import signal
import time
from fastapi import FastAPI
import uvicorn
import random

from mm_bot.main import run_bot

app = FastAPI(title="Based Tradebot", version="1.0.0")

_shutdown = threading.Event()
_bot_started = threading.Event()
_last_crash = None

@app.get("/health")
def health():
    return {"status": "ok", "bot_started": _bot_started.is_set(), "shutdown": _shutdown.is_set()}

@app.get("/")
def root():
    return {"service": "based-tradebot", "message": "running", "ts": int(time.time())}


def _bot_wrapper():
    _bot_started.set()
    base = 5
    cap = 60
    while not _shutdown.is_set():
        try:
            run_bot()
        except SystemExit as e:
            backoff = min(cap, base) + random.uniform(0, 1.5)
            print(f"[bot] SystemExit: {e}. restart in {backoff:.1f}s", flush=True)
            time.sleep(backoff)
        except Exception as e:
            backoff = min(cap, base) + random.uniform(0, 1.5)
            print(f"[bot] crashed: {e}. restart in {backoff:.1f}s", flush=True)
            time.sleep(backoff)
        else:
            backoff = min(cap, base) + random.uniform(0, 1.5)
            print(f"[bot] exited cleanly. restarting in {backoff:.1f}s", flush=True)
            time.sleep(backoff)
        base = min(cap, base * 2)

def _handle_sigterm(*_args):
    print("[server] SIGTERM received -> shutting down", flush=True)
    _shutdown.set()

if __name__ == "__main__":
    t = threading.Thread(target=_bot_wrapper, daemon=True)
    t.start()

    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        log_level="info",
    )
    _shutdown.set()
    time.sleep(0.5)