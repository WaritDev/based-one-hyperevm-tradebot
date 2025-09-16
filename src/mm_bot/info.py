import json, requests
from decimal import Decimal
from typing import Dict, Optional, Tuple, List
from .config import Settings
from .utils import to_decimal_safe, one_tick_from_dec

INFO_URL = None

def _post_json(url: str, body: Dict, timeout: int = 15) -> Dict:
    r = requests.post(url, headers={"Content-Type": "application/json"}, data=json.dumps(body), timeout=timeout)
    try:
        data = r.json()
    except Exception:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text}")
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {data}")
    return data

def init_info(cfg: Settings):
    global INFO_URL
    INFO_URL = f"{cfg.BASE_URL}/info"

def spot_meta() -> Dict:
    return _post_json(INFO_URL, {"type": "spotMeta"})

def all_mids() -> Dict:
    return _post_json(INFO_URL, {"type": "allMids"})

def user_spot_balances(addr: str) -> Dict:
    return _post_json(INFO_URL, {"type": "spotUserBalances", "user": addr})

def get_universe() -> list:
    smeta = spot_meta() or {}
    return smeta.get("universe", [])

def parse_index(sym_or_idx: str) -> int | None:
    s = sym_or_idx.strip().upper()
    if s.startswith("@"):
        s = s[1:]
    return int(s) if s.isdigit() else None

def extract_steps(a: Dict, px_dec: int, sz_dec: int, lotsz_fb: Decimal) -> tuple[Decimal, Decimal]:
    tick = a.get("tickSz") or a.get("ticksz") or a.get("tick_size")
    lot  = a.get("lotSz")  or a.get("lotsz")  or a.get("lot_size")
    tick_sz = to_decimal_safe(tick, "tickSz") if tick is not None else one_tick_from_dec(px_dec)
    lot_sz  = to_decimal_safe(lot,  "lotSz")  if lot  is not None else (Decimal(1) / (Decimal(10) ** sz_dec) if sz_dec > 0 else lotsz_fb)
    return tick_sz, lot_sz

def resolve_asset_fields(cfg: Settings):
    uni = get_universe()
    idx = parse_index(cfg.SYMBOL)

    from dataclasses import dataclass
    @dataclass
    class AssetInfo:
        asset_id: int
        px_dec: int
        sz_dec: int
        index: int | None
        name: str
        tick_sz: Decimal
        lot_sz: Decimal

    if idx is not None:
        asset_id = 10000 + idx
        px_dec, sz_dec = cfg.PX_DEC, cfg.SZ_DEC
        name = f"@{idx}"
        tick_sz, lot_sz = cfg.TICK_FALLBACK, cfg.LOTSZ_FALLBACK

        if 0 <= idx < len(uni):
            a = uni[idx]
            px_dec = int(a.get("pxDecimals") or cfg.PX_DEC)
            sz_dec = int(a.get("szDecimals") or cfg.SZ_DEC)
            name   = a.get("name", name)
            tick_sz, lot_sz = extract_steps(a, px_dec, sz_dec, cfg.LOTSZ_FALLBACK)
        else:
            from .utils import one_tick_from_dec
            tick_sz = one_tick_from_dec(px_dec)
            lot_sz  = cfg.LOTSZ_FALLBACK if sz_dec == 0 else (Decimal(1) / (Decimal(10) ** sz_dec))

        return AssetInfo(asset_id, px_dec, sz_dec, idx, name, tick_sz, lot_sz)

    target = cfg.SYMBOL.upper()
    for i, a in enumerate(uni):
        if a.get("name", "").upper() == target:
            px_dec = int(a.get("pxDecimals") or cfg.PX_DEC)
            sz_dec = int(a.get("szDecimals") or cfg.SZ_DEC)
            asset_id = 10000 + i
            tick_sz, lot_sz = extract_steps(a, px_dec, sz_dec, cfg.LOTSZ_FALLBACK)
            return AssetInfo(asset_id, px_dec, sz_dec, i, a.get("name", target), tick_sz, lot_sz)

    names = ", ".join(a.get("name","") for a in uni[:30])
    raise ValueError(f"Spot symbol not found: {cfg.SYMBOL}. Available (first 30): {names}")

def get_mid_by_index(idx: int) -> Decimal:
    mids = all_mids() or {}
    key = f"@{idx}"
    val = mids.get(key)
    if val is None:
        raise RuntimeError(f"Mid not found for spot index {idx} (key {key})")
    return to_decimal_safe(val, f"mid[{key}]")

def clamp_price_to_ref_band(idx: int | None, raw_px: Decimal) -> tuple[Decimal, tuple[Decimal, Decimal], Decimal | None]:
    if idx is None:
        return raw_px, (raw_px, raw_px), None
    mid = get_mid_by_index(idx)
    low = (mid * Decimal("0.05"))
    high = (mid * Decimal("1.95"))
    px = min(max(raw_px, low), high)
    return px, (low, high), mid