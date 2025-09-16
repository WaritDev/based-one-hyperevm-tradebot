import os, json, re, time, requests
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, getcontext
from typing import Dict, Optional, Tuple

from dotenv import load_dotenv
from pybotters.helpers import hyperliquid as hlh

load_dotenv()
getcontext().prec = 50

INFO_URL     = None 
EXCHANGE_URL = None

COMMON_TICKS = [
    Decimal("0.000001"), Decimal("0.000005"), Decimal("0.00001"),
    Decimal("0.00005"),  Decimal("0.0001"),   Decimal("0.001")
]

@dataclass
class Config:
    private_key: str
    is_mainnet: bool
    base_url: str
    symbol: str 
    size: Decimal
    price_env: Optional[Decimal]
    tif: str
    side_buy: bool
    post_only: bool
    retries: int
    include_builder: bool
    builder_addr: str
    builder_fee_tenth_bps: int
    px_dec_fallback: int
    sz_dec_fallback: int
    tick_fallback: Decimal
    lotsz_fallback: Decimal
    client_id: Optional[str]

@dataclass
class AssetInfo:
    asset_id: int
    px_dec: int
    sz_dec: int
    index: Optional[int]
    name: str
    tick_sz: Decimal
    lot_sz: Decimal

def post_json(url: str, body: Dict, timeout: int = 15) -> Dict:
    r = requests.post(url, headers={"Content-Type": "application/json"}, data=json.dumps(body), timeout=timeout)
    try:
        data = r.json()
    except Exception:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text}")
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {data}")
    return data

def info_spot_meta() -> Dict:
    return post_json(INFO_URL, {"type": "spotMeta"})

def info_all_mids() -> Dict:
    return post_json(INFO_URL, {"type": "allMids"})

def load_config() -> Config:
    global INFO_URL, EXCHANGE_URL
    private_key = os.getenv("PRIVATE_KEY")
    if not private_key:
        raise SystemExit("❌ PRIVATE_KEY not set in .env")

    is_mainnet = (os.getenv("IS_MAINNET", "true").lower() == "true")
    base_url = os.getenv("BASE_URL") or ("https://api.hyperliquid.xyz" if is_mainnet else "https://api.hyperliquid-testnet.xyz")
    INFO_URL, EXCHANGE_URL = f"{base_url}/info", f"{base_url}/exchange"

    symbol      = (os.getenv("SPOT_SYMBOL") or os.getenv("SYMBOL") or "@223").upper()
    size_str    = os.getenv("SIZE") or "30"
    price_env   = os.getenv("PRICE")
    tif         = os.getenv("TIF") or "Gtc"
    side_buy    = (os.getenv("SIDE") or "buy").lower() == "buy"
    post_only   = (os.getenv("POST_ONLY", "true").lower() == "true")
    retries     = int(os.getenv("RETRIES") or 5)
    include_b   = (os.getenv("INCLUDE_BUILDER", "true").lower() == "true")
    builder_addr= (os.getenv("BUILDER_ADDR") or "0x1924b8561eef20e70ede628a296175d358be80e5").lower()
    builder_fee = int(os.getenv("BUILDER_FEE_TENTH_BPS") or 100)
    client_id   = os.getenv("CLIENT_ID")

    px_fallback = int(os.getenv("PX_DEC", "6"))
    sz_fallback = int(os.getenv("SZ_DEC", "0"))
    tick_fb     = Decimal(os.getenv("TICK_FALLBACK", "0.000001"))
    lotsz_fb    = Decimal(os.getenv("LOTSZ_FALLBACK", "1"))

    try:
        size = Decimal(str(size_str))
    except Exception:
        raise SystemExit("❌ Bad SIZE")

    price = Decimal(str(price_env)) if price_env else None

    return Config(
        private_key=private_key,
        is_mainnet=is_mainnet,
        base_url=base_url,
        symbol=symbol,
        size=size,
        price_env=price,
        tif=tif,
        side_buy=side_buy,
        post_only=post_only,
        retries=retries,
        include_builder=include_b,
        builder_addr=builder_addr,
        builder_fee_tenth_bps=builder_fee,
        px_dec_fallback=px_fallback,
        sz_dec_fallback=sz_fallback,
        tick_fallback=tick_fb,
        lotsz_fallback=lotsz_fb,
        client_id=client_id
    )

def fmt_decimal_str(x: str | float | Decimal, decimals: int) -> str:
    d = Decimal(str(x))
    q = Decimal(1) / (Decimal(10) ** decimals)
    s = d.quantize(q, rounding=ROUND_DOWN).normalize()
    return format(s, 'f')

def decimals_of(d: Decimal) -> int:
    return max(0, -d.as_tuple().exponent)

def one_tick_from_dec(px_dec: int) -> Decimal:
    return Decimal(1) / (Decimal(10) ** px_dec)

def snap_to_step(value: Decimal, step: Decimal, direction: str = "down") -> Decimal:
    """Snap value to the grid of `step`."""
    if step <= 0:
        return value
    q = (value / step)
    if direction == "up":
        base = q.to_integral_value(rounding=ROUND_DOWN)
        q = base if q == base else base + 1
    else:
        q = q.to_integral_value(rounding=ROUND_DOWN)
    snapped = q * step
    return snapped.quantize(step, rounding=ROUND_DOWN)

def _parse_index(sym_or_idx: str) -> Optional[int]:
    s = sym_or_idx.strip().upper()
    if s.startswith("@"):
        s = s[1:]
    return int(s) if s.isdigit() else None

def _get_universe() -> list:
    smeta = info_spot_meta() or {}
    return smeta.get("universe", [])

def _extract_steps(a: Dict, px_dec: int, sz_dec: int, lotsz_fb: Decimal) -> Tuple[Decimal, Decimal]:
    tick = a.get("tickSz") or a.get("ticksz") or a.get("tick_size")
    lot  = a.get("lotSz")  or a.get("lotsz")  or a.get("lot_size")
    tick_sz = Decimal(str(tick)) if tick is not None else one_tick_from_dec(px_dec)
    lot_sz  = Decimal(str(lot))  if lot is not None  else (Decimal(1) / (Decimal(10) ** sz_dec) if sz_dec > 0 else lotsz_fb)
    return tick_sz, lot_sz

def resolve_asset_fields(cfg: Config) -> AssetInfo:
    uni = _get_universe()
    idx = _parse_index(cfg.symbol)

    if idx is not None:
        asset_id = 10000 + idx
        px_dec, sz_dec = cfg.px_dec_fallback, cfg.sz_dec_fallback
        name = f"@{idx}"
        tick_sz, lot_sz = cfg.tick_fallback, cfg.lotsz_fallback

        if 0 <= idx < len(uni):
            a = uni[idx]
            px_dec = int(a.get("pxDecimals") or cfg.px_dec_fallback)
            sz_dec = int(a.get("szDecimals") or cfg.sz_dec_fallback)
            name   = a.get("name", name)
            tick_sz, lot_sz = _extract_steps(a, px_dec, sz_dec, cfg.lotsz_fallback)
        else:
            tick_sz = one_tick_from_dec(px_dec)
            lot_sz  = cfg.lotsz_fallback if sz_dec == 0 else Decimal(1) / (Decimal(10) ** sz_dec)

        return AssetInfo(asset_id, px_dec, sz_dec, idx, name, tick_sz, lot_sz)

    target = cfg.symbol.upper()
    for i, a in enumerate(uni):
        if a.get("name", "").upper() == target:
            px_dec = int(a.get("pxDecimals") or cfg.px_dec_fallback)
            sz_dec = int(a.get("szDecimals") or cfg.sz_dec_fallback)
            asset_id = 10000 + i
            tick_sz, lot_sz = _extract_steps(a, px_dec, sz_dec, cfg.lotsz_fallback)
            return AssetInfo(asset_id, px_dec, sz_dec, i, a.get("name", target), tick_sz, lot_sz)

    names = ", ".join(a.get("name","") for a in uni[:30])
    raise ValueError(f"Spot symbol not found: {cfg.symbol}. Available (first 30): {names}")

def get_mid_by_index(idx: int) -> Decimal:
    mids = info_all_mids() or {}
    key = f"@{idx}"
    val = mids.get(key)
    if val is None:
        raise RuntimeError(f"Mid not found for spot index {idx} (key {key})")
    return Decimal(str(val))

def clamp_price_to_ref_band(idx: Optional[int], raw_px: Decimal) -> Tuple[Decimal, Tuple[Decimal, Decimal], Optional[Decimal]]:
    if idx is None:
        return raw_px, (raw_px, raw_px), None
    mid = get_mid_by_index(idx)
    low = (mid * Decimal("0.05"))
    high = (mid * Decimal("1.95"))
    px = min(max(raw_px, low), high)
    return px, (low, high), mid

def infer_tick_from_bbo(err_msg: str) -> Optional[Decimal]:
    m = re.search(r"bbo was ([0-9.]+)@([0-9.]+)", err_msg or "")
    if not m:
        return None
    bid = Decimal(m.group(1)); ask = Decimal(m.group(2))
    d = max(decimals_of(bid), decimals_of(ask))
    return Decimal(1) / (Decimal(10) ** d) if d > 0 else Decimal(1)

def next_coarser_tick(current: Decimal) -> Optional[Decimal]:
    for t in COMMON_TICKS:
        if t > current:
            return t
    return None

def build_and_send(cfg: Config, action: Dict) -> Dict:
    nonce = hlh.get_timestamp_ms()
    domain, types, message = hlh.construct_l1_action(action=action, nonce=nonce, is_mainnet=cfg.is_mainnet)
    signature = hlh.sign_typed_data(cfg.private_key, domain, types, message)
    return post_json(EXCHANGE_URL, {"action": action, "nonce": nonce, "signature": signature})

def place_spot_limit_order(cfg: Config, asset: AssetInfo, is_buy: bool,px: Decimal, sz: Decimal, tif: str, post_only: bool, reduce_only: bool = False, override_tick: Optional[Decimal] = None) -> Dict:
    tick_sz = override_tick or asset.tick_sz
    px = snap_to_step(px, tick_sz, direction="down")
    sz = snap_to_step(sz, asset.lot_sz, direction="down")

    px_wire = fmt_decimal_str(px, decimals_of(tick_sz))
    sz_wire = fmt_decimal_str(sz, decimals_of(asset.lot_sz))
    tif_eff = "Alo" if post_only else tif

    order = {
        "a": asset.asset_id, "b": bool(is_buy), "p": px_wire, "s": sz_wire,
        "r": bool(reduce_only), "t": {"limit": {"tif": tif_eff}}
    }
    if cfg.client_id:
        order["c"] = cfg.client_id

    action: Dict = {"type": "order", "orders": [order], "grouping": "na"}
    if cfg.include_builder:
        action["builder"] = {"b": cfg.builder_addr, "f": cfg.builder_fee_tenth_bps}

    print("=== DEBUG action ===")
    print(f"Spot Name: {asset.name}  Index: {asset.index}  AssetID: {asset.asset_id}  "f"Decimals: px={asset.px_dec} sz={asset.sz_dec}  tick={tick_sz} lot={asset.lot_sz}")
    print(json.dumps(action, indent=2))

    res = build_and_send(cfg, action)
    print("=== RESPONSE ===")
    print(json.dumps(res, indent=2))
    return res

def smart_submit(cfg: Config, asset: AssetInfo, is_buy: bool, px: Decimal, sz: Decimal,tif: str, post_only: bool, max_retries: int) -> Dict:
    cur_tick = asset.tick_sz
    cur_px, cur_sz = px, sz
    attempt = 0

    while True:
        res = place_spot_limit_order(cfg, asset, is_buy, cur_px, cur_sz, tif, post_only, reduce_only=False, override_tick=cur_tick)

        statuses = res.get("response", {}).get("data", {}).get("statuses", [])
        err_msg = (statuses[0].get("error") if statuses and isinstance(statuses[0], dict) else None)

        if not err_msg:
            return res

        m_bbo = re.search(r"bbo was ([0-9.]+)@([0-9.]+)", err_msg or "")
        if "Post only order would have immediately matched" in (err_msg or "") and m_bbo and attempt < max_retries:
            bid = Decimal(m_bbo.group(1)); ask = Decimal(m_bbo.group(2))
            inferred = infer_tick_from_bbo(err_msg)
            if inferred:
                cur_tick = inferred
            cur_px = snap_to_step((bid - cur_tick) if is_buy else (ask + cur_tick), cur_tick, direction="down")
            attempt += 1
            print(f"↺ Alo hit BBO {bid}@{ask}. Retry#{attempt} with px={cur_px}, tick={cur_tick}")
            continue

        if "Price must be divisible by tick size" in (err_msg or "") and attempt < max_retries:
            inferred = infer_tick_from_bbo(err_msg)
            if inferred and inferred != cur_tick:
                cur_tick = inferred
            else:
                cur_tick = next_coarser_tick(cur_tick) or Decimal("0.00001")
            cur_px = snap_to_step(cur_px, cur_tick, direction="down")
            attempt += 1
            print(f"↺ Tick not aligned. Retry#{attempt} with px={cur_px}, tick={cur_tick}")
            continue

        return res

def cancel_by_oid(cfg: Config, asset_id: int, oid: int):
    action = {"type": "cancel", "cancels": [{"a": asset_id, "o": oid}]}
    return build_and_send(cfg, action)

def cancel_by_cloid(cfg: Config, asset_id: int, cloid: str):
    action = {"type": "cancelByCloid", "cancels": [{"asset": asset_id, "cloid": cloid}]}
    return build_and_send(cfg, action)

def schedule_cancel_all(cfg: Config, at_ms: Optional[int] = None):
    action = {"type": "scheduleCancel"}
    if at_ms:
        action["time"] = at_ms
    return build_and_send(cfg, action)

if __name__ == "__main__":
    cfg = load_config()
    asset = resolve_asset_fields(cfg)

    if cfg.price_env is not None:
        px_raw = cfg.price_env
    else:
        idx_from_symbol = _parse_index(cfg.symbol)
        if idx_from_symbol is None:
            raise SystemExit("❌ Please set PRICE in env (name symbols can't auto-mid)")
        px_raw = get_mid_by_index(idx_from_symbol)

    px_clamped, (lo, hi), mid = clamp_price_to_ref_band(asset.index, px_raw)
    if mid is not None and px_clamped != px_raw:
        print(f"⚠️ PRICE={px_raw} -> clamped={px_clamped} (mid={mid}, band=[{lo},{hi}])")

    notional = px_clamped * cfg.size
    if notional < Decimal("10"):
        print(f"⚠️  Notional ~{notional} < 10 (quote). อาจโดนปฏิเสธ")

    try:
        smart_submit(
            cfg=cfg,
            asset=asset,
            is_buy=cfg.side_buy,
            px=px_clamped,
            sz=cfg.size,
            tif=cfg.tif,
            post_only=cfg.post_only,
            max_retries=cfg.retries
        )
    except Exception as e:
        raise SystemExit(f"❌ Place spot order error: {e}")