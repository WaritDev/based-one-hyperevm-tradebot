import os, json, time, requests
from decimal import Decimal, ROUND_DOWN, getcontext
from typing import Dict, Tuple, Optional
from dotenv import load_dotenv

from pybotters.helpers import hyperliquid as hlh

load_dotenv()

PRIVATE_KEY = os.getenv("PRIVATE_KEY")
IS_MAINNET  = (os.getenv("IS_MAINNET", "true").lower() == "true")
BASE_URL    = os.getenv("BASE_URL") or ("https://api.hyperliquid.xyz" if IS_MAINNET else "https://api.hyperliquid-testnet.xyz")

SYMBOL = (os.getenv("SYMBOL") or "BTC").upper().replace("-PERP", "")
SIZE   = os.getenv("SIZE") or "0.0012"
TIF    = os.getenv("TIF") or "Gtc"

INCLUDE_BUILDER         = (os.getenv("INCLUDE_BUILDER", "true").lower() == "true")
BUILDER_ADDR            = (os.getenv("BUILDER_ADDR") or "0x1924b8561eef20e70ede628a296175d358be80e5").lower()
BUILDER_FEE_TENTH_BPS   = int(os.getenv("BUILDER_FEE_TENTH_BPS") or 25)
CLIENT_ID               = os.getenv("CLIENT_ID") or "0xba5ed11067f2cc08ba5ed10000ba5ed1"

if not PRIVATE_KEY:
    raise SystemExit("❌ PRIVATE_KEY not set in .env")

INFO_URL     = f"{BASE_URL}/info"
EXCHANGE_URL = f"{BASE_URL}/exchange"

def post_json(url: str, body: Dict, timeout: int = 15) -> Dict:
    r = requests.post(url, headers={"Content-Type": "application/json"}, data=json.dumps(body), timeout=timeout)
    try:
        data = r.json()
    except Exception:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text}")
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {data}")
    return data

# ---------------- Info helpers ----------------
def info_meta() -> Dict:
    return post_json(INFO_URL, {"type": "meta"})

def info_all_mids() -> Dict:
    return post_json(INFO_URL, {"type": "allMids"})

def info_max_builder_fee(user_addr: str, builder_addr: str) -> Optional[int]:
    try:
        res = post_json(INFO_URL, {"type": "maxBuilderFee", "user": user_addr, "builder": builder_addr})
        return int(res)
    except Exception:
        return None

def find_asset_index(symbol: str) -> Tuple[int, int]:
    meta = info_meta()
    for idx, a in enumerate(meta.get("universe", [])):
        if a.get("name", "").upper() == symbol:
            return idx, int(a.get("szDecimals", 4))
    names = ", ".join(a.get("name") for a in meta.get("universe", [])[:30])
    raise ValueError(f"Symbol not found: {symbol}. Available: {names}")

def fmt_size(x: str | float, sz_dec: int) -> str:
    getcontext().prec = 50
    d = Decimal(str(x))
    q = Decimal(1) / (Decimal(10) ** sz_dec)
    s = d.quantize(q, rounding=ROUND_DOWN).normalize()
    return format(s, 'f')

def count_sigfigs(s: str) -> int:
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    t = s.lstrip('0')
    if t.startswith('.'):
        t = t[1:].lstrip('0')
    return sum(c.isdigit() for c in t)

def fmt_price(px: str | float, sz_dec: int) -> str:
    getcontext().prec = 50
    d = Decimal(str(px))
    max_decimals = max(0, 6 - sz_dec)
    if d == d.to_integral_value():
        return format(d.quantize(Decimal(1), rounding=ROUND_DOWN), 'f')
    scale = Decimal(1) / (Decimal(10) ** max_decimals)
    d2 = d.quantize(scale, rounding=ROUND_DOWN)
    s = format(d2.normalize(), 'f')
    if count_sigfigs(s) > 5:
        return format(d.to_integral_value(rounding=ROUND_DOWN), 'f')
    return s

def build_l1_typed(action: Dict, nonce: int):
    variants = [
        dict(action=action, nonce=nonce, is_mainnet=IS_MAINNET, vault_address=None, expires_after=None),
        dict(action=action, nonce=nonce, is_mainnet=IS_MAINNET, vault_address=None),
        dict(action=action, nonce=nonce, is_mainnet=IS_MAINNET),
    ]
    last_err = None
    for kwargs in variants:
        try:
            return hlh.construct_l1_action(**kwargs)
        except TypeError as e:
            last_err = e
            continue
    raise TypeError(f"construct_l1_action signature mismatch: {last_err}")

def now_ms() -> int:
    try:
        return hlh.get_timestamp_ms()
    except Exception:
        return int(time.time() * 1000)

def place_limit_order_l1(symbol: str, is_buy: bool, px, sz, tif="Gtc", with_builder=True):
    aid, sz_dec = find_asset_index(symbol)
    px_wire = fmt_price(px, sz_dec)
    sz_wire = fmt_size(sz, sz_dec)

    order = {
        "a": aid,
        "b": bool(is_buy),
        "p": px_wire,
        "s": sz_wire,
        "r": False,
        "t": {"limit": {"tif": tif}},
    }
    if CLIENT_ID:
        order["c"] = CLIENT_ID

    action: Dict = {
        "type": "order",
        "orders": [order],
        "grouping": "na",
    }
    if with_builder and INCLUDE_BUILDER:
        action["builder"] = {"b": BUILDER_ADDR, "f": BUILDER_FEE_TENTH_BPS}

    print("=== DEBUG action ===")
    print(json.dumps(action, indent=2))

    nonce = now_ms()
    domain, types, message = build_l1_typed(action, nonce)
    signature = hlh.sign_typed_data(PRIVATE_KEY, domain, types, message)
    body = {"action": action, "nonce": nonce, "signature": signature}
    res = post_json(EXCHANGE_URL, body)
    print("=== RESPONSE ===")
    print(json.dumps(res, indent=2))
    return res

if __name__ == "__main__":
    mids = info_all_mids()
    mid = None
    if isinstance(mids, dict):
        mid = float(mids.get(SYMBOL) or mids.get("BTC") or 0.0)
    if not mid or mid <= 0:
        raise SystemExit(f"❌ Failed to get mid for {SYMBOL}. allMids: {mids}")

    _, sz_dec = find_asset_index(SYMBOL)
    test_px = Decimal(str(mid))
    px_wire = fmt_price(test_px, sz_dec)

    max_fee = info_max_builder_fee(os.getenv("ACCOUNT_ADDRESS") or "", BUILDER_ADDR)
    if INCLUDE_BUILDER and max_fee is not None and max_fee < BUILDER_FEE_TENTH_BPS:
        print(f"⚠️  Warning: maxBuilderFee ({max_fee}) < required ({BUILDER_FEE_TENTH_BPS}). ออเดอร์อาจถูกปฏิเสธจนกว่าจะอนุมัติ builder fee.")

    print(f"Mid: {mid} | Test price: {px_wire} | base_url: {BASE_URL}")
    place_limit_order_l1(SYMBOL, is_buy=True, px=px_wire, sz=SIZE, tif=TIF, with_builder=True)