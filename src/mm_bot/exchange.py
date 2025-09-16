import json
from decimal import Decimal
from typing import Dict, Optional
import requests

from pybotters.helpers import hyperliquid as hlh

from .config import Settings
from .utils import (
    fmt_decimal_str,
    decimals_of,
    snap_to_step,
    to_decimal_safe,
    infer_tick_from_bbo,
    next_coarser_tick,
)

EXCHANGE_URL: Optional[str] = None

def init_exchange(cfg: Settings):
    """Call once at startup (see main.py)."""
    global EXCHANGE_URL
    EXCHANGE_URL = f"{cfg.BASE_URL}/exchange"

def _post_json(url: str, body: Dict, timeout: int = 15) -> Dict:
    r = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        data=json.dumps(body),
        timeout=timeout,
    )
    try:
        data = r.json()
    except Exception:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text}")
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {data}")
    return data

def build_and_send(cfg: Settings, action: Dict) -> Dict:
    if EXCHANGE_URL is None:
        raise RuntimeError("EXCHANGE_URL is not initialized. Call init_exchange(cfg) first.")
    nonce = hlh.get_timestamp_ms()
    domain, types, message = hlh.construct_l1_action(
        action=action, nonce=nonce, is_mainnet=cfg.IS_MAINNET
    )
    signature = hlh.sign_typed_data(cfg.PRIVATE_KEY, domain, types, message)
    return _post_json(EXCHANGE_URL, {"action": action, "nonce": nonce, "signature": signature})

def place_spot_limit_order(
    cfg: Settings,
    asset,
    is_buy: bool,
    px: Decimal,
    sz: Decimal,
    tif: str,
    post_only: bool,
    reduce_only: bool = False,
    override_tick: Optional[Decimal] = None,
    cloid: Optional[str] = None,
) -> Dict:
    tick_sz = override_tick or asset.tick_sz
    px = snap_to_step(px, tick_sz, direction="down")
    sz = snap_to_step(sz, asset.lot_sz, direction="down")

    px_wire = fmt_decimal_str(px, decimals_of(tick_sz))
    sz_wire = fmt_decimal_str(sz, decimals_of(asset.lot_sz))
    tif_eff = "Alo" if post_only else tif

    order = {
        "a": asset.asset_id,
        "b": bool(is_buy),
        "p": px_wire,
        "s": sz_wire,
        "r": bool(reduce_only),
        "t": {"limit": {"tif": tif_eff}},
    }
    if cloid:
        order["c"] = cloid
    elif cfg.CLIENT_ID:
        order["c"] = cfg.CLIENT_ID

    action: Dict = {"type": "order", "orders": [order], "grouping": "na"}
    if cfg.INCLUDE_BUILDER:
        action["builder"] = {"b": cfg.BUILDER_ADDR, "f": cfg.BUILDER_FEE_TENTH_BPS}

    return build_and_send(cfg, action)


def smart_submit(
    cfg: Settings,
    asset,
    is_buy: bool,
    px: Decimal,
    sz: Decimal,
    tif: str,
    post_only: bool,
    max_retries: int,
    cloid: Optional[str] = None,
) -> Dict:
    cur_tick = asset.tick_sz
    cur_px, cur_sz = px, sz
    attempt = 0

    while True:
        res = place_spot_limit_order(
            cfg,
            asset,
            is_buy,
            cur_px,
            cur_sz,
            tif,
            post_only,
            reduce_only=False,
            override_tick=cur_tick,
            cloid=cloid,
        )
        statuses = res.get("response", {}).get("data", {}).get("statuses", [])
        err_msg = (statuses[0].get("error") if statuses and isinstance(statuses[0], dict) else None)

        if not err_msg:
            return res

        if "Post only order would have immediately matched" in (err_msg or ""):
            inferred = infer_tick_from_bbo(err_msg)
            if inferred:
                cur_tick = inferred
            import re
            m = re.search(r"bbo was ([0-9.]+)@([0-9.]+)", err_msg or "")
            if m:
                bid = to_decimal_safe(m.group(1), "retry.bid")
                ask_raw = m.group(2).rstrip(" .")
                ask = to_decimal_safe(ask_raw, "retry.ask")
                cur_px = snap_to_step((bid - cur_tick) if is_buy else (ask + cur_tick), cur_tick, direction="down")
                attempt += 1
                if attempt <= max_retries:
                    continue
            return res

        if "Price must be divisible by tick size" in (err_msg or ""):
            inferred = infer_tick_from_bbo(err_msg)
            if inferred and inferred != cur_tick:
                cur_tick = inferred
            else:
                cur_tick = next_coarser_tick(cur_tick) or Decimal("0.00001")
            cur_px = snap_to_step(cur_px, cur_tick, direction="down")
            attempt += 1
            if attempt <= max_retries:
                continue
            return res

        return res


def cancel_by_cloid(cfg: Settings, asset_id: int, cloid: str):
    action = {"type": "cancelByCloid", "cancels": [{"asset": asset_id, "cloid": cloid}]}
    return build_and_send(cfg, action)


def schedule_cancel_all(cfg: Settings, at_ms: int | None = None):
    action = {"type": "scheduleCancel"}
    if at_ms:
        action["time"] = at_ms
    return build_and_send(cfg, action)


def place_market_ioc(cfg: Settings, asset, side_buy: bool, sz: Decimal) -> Dict:
    sz = snap_to_step(sz, asset.lot_sz, "down")
    sz_wire = fmt_decimal_str(sz, decimals_of(asset.lot_sz))
    order = {"a": asset.asset_id, "b": bool(side_buy), "s": sz_wire, "t": {"market": {"tif": "Ioc"}}}
    action: Dict = {"type": "order", "orders": [order], "grouping": "na"}
    if cfg.INCLUDE_BUILDER:
        action["builder"] = {"b": cfg.BUILDER_ADDR, "f": cfg.BUILDER_FEE_TENTH_BPS}
    return build_and_send(cfg, action)