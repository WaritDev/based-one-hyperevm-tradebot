import os
import threading
import signal
import time
from fastapi import FastAPI
import uvicorn

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
    backoff = 5
    while not _shutdown.is_set():
        try:
            run_bot()
        except SystemExit as e:
            print(f"[bot] SystemExit: {e}. Will restart in {backoff}s", flush=True)
            time.sleep(backoff)
        except Exception as e:
            print(f"[bot] crashed: {e}. Will restart in {backoff}s", flush=True)
            time.sleep(backoff)
        else:
            print(f"[bot] exited cleanly. Restarting in {backoff}s", flush=True)
            time.sleep(backoff)
    print("[bot] shutdown flag set, exiting bot loop", flush=True)

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