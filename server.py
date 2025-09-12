import os
import threading
import signal
import time
from fastapi import FastAPI
import uvicorn

from based_tradebot_v2 import run_bot

app = FastAPI(title="Based Tradebot", version="1.0.0")

_shutdown = threading.Event()
_bot_started = threading.Event()

@app.get("/health")
def health():
    return {"status": "ok", "bot_started": _bot_started.is_set()}

@app.get("/")
def root():
    return {"service": "based-tradebot", "message": "running", "ts": int(time.time())}

def _bot_wrapper():
    _bot_started.set()
    try:
        run_bot()
    except Exception as e:
        print(f"[bot] crashed: {e}", flush=True)
        raise
    finally:
        print("[bot] exited", flush=True)

def _handle_sigterm(*_args):
    _shutdown.set()
    time.sleep(0.5)

if __name__ == "__main__":
    t = threading.Thread(target=_bot_wrapper, daemon=True)
    t.start()

    signal.signal(signal.SIGTERM, _handle_sigterm)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        log_level="info",
    )