import json, requests
from .config import Settings

def verify_or_exit(cfg: Settings):
    if not cfg.AUTH_API_URL:
        print("ℹ️ AUTH_API_URL not set — skipping external auth.")
        return
    if not cfg.USER_ADDR or not cfg.PASSWORD:
        raise SystemExit("Authentication failed: USER_ADDR or PASSWORD missing.")

    payload = {"user": cfg.USER_ADDR, "password": cfg.PASSWORD}
    if cfg.AUTH_API_TOKEN:
        payload["token"] = cfg.AUTH_API_TOKEN

    try:
        r = requests.post(
            cfg.AUTH_API_URL,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=12,
        )
    except Exception as e:
        raise SystemExit(f"Auth API request failed: {repr(e)}")

    try:
        data = r.json()
    except Exception:
        raise SystemExit(f"Auth API invalid response: HTTP {r.status_code} {r.text[:200]}")

    if not data.get("ok"):
        err = data.get("error", "user/password not authorized")
        raise SystemExit(f"Authentication failed: {err}")

    print("✓ Auth OK")