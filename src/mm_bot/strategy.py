import time
from uuid import uuid4
from decimal import Decimal
from typing import Optional, List, Dict

from pybotters.helpers import hyperliquid as hlh

from .config import Settings
from .stats import Stats
from .panel import render_panel
from .utils import to_decimal_safe
from .info import get_mid_by_index, user_spot_balances
from .exchange import (
    smart_submit,
    schedule_cancel_all,
    place_market_ioc,
    cancel_by_cloid,
)


class MakerBot:
    def __init__(self, cfg: Settings, asset):
        self.cfg = cfg
        self.asset = asset
        self.stats = Stats()

        self.anchor_mid: Optional[Decimal] = None
        self.range_lo: Optional[Decimal] = cfg.RANGE_LOWER
        self.range_hi: Optional[Decimal] = cfg.RANGE_UPPER

        self.live: Dict[str, float] = {}

        self._last_side = True if cfg.START_SIDE == "sell" else False
        if cfg.START_SIDE == "sell":
            self._last_side = True
        else:
            self._last_side = False

    def compute_band(self) -> Optional[Decimal]:
        if self.asset.index is None:
            return None
        mid = get_mid_by_index(self.asset.index)
        self.stats.last_mid = mid

        if self.anchor_mid is None:
            self.anchor_mid = mid
            if self.range_lo is None and self.range_hi is None and self.cfg.RANGE_PCT:
                self.range_lo = self.anchor_mid * (Decimal(1) - self.cfg.RANGE_PCT)
                self.range_hi = self.anchor_mid * (Decimal(1) + self.cfg.RANGE_PCT)
        return mid

    def in_range(self, price: Decimal) -> bool:
        if self.range_lo is not None and price < self.range_lo:
            return False
        if self.range_hi is not None and price > self.range_hi:
            return False
        return True

    def _bump_stats_after_submit(self, is_buy: bool, mid_used: Decimal):
        if is_buy:
            self.stats.total_buy += 1
            self.stats.vol_base_buy += self.cfg.SIZE
            self.stats.notional_buy += (mid_used * self.cfg.SIZE)
            self.stats.buys_this_min += 1
        else:
            self.stats.total_sell += 1
            self.stats.vol_base_sell += self.cfg.SIZE
            self.stats.notional_sell += (mid_used * self.cfg.SIZE)
            self.stats.sells_this_min += 1

    def _gen_cloid(self) -> str:
        """Generate 0x + 32 hex (16 bytes) CLOID per order."""
        return "0x" + uuid4().hex[:32]

    def place_one(self, is_buy: bool, mid: Decimal):
        px = mid + (self.asset.tick_sz * (Decimal(3) if not is_buy else Decimal(-3)))
        try:
            cloid = self._gen_cloid()
            smart_submit(
                self.cfg,
                self.asset,
                is_buy,
                px,
                self.cfg.SIZE,
                self.cfg.TIF,
                self.cfg.POST_ONLY,
                self.cfg.RETRIES,
                cloid=cloid,
            )
            self._bump_stats_after_submit(is_buy, mid)
            side_txt = "BUY " if is_buy else "SELL"
            self.stats.last_action = f"{side_txt}{self.cfg.SIZE} @~{mid:.6f} (±3 ticks)"
            self.live[cloid] = time.time()
        except Exception:
            self.stats.last_action = "place: failed/retried"

    def cancel_all(self):
        try:
            schedule_cancel_all(self.cfg, at_ms=hlh.get_timestamp_ms())
            self.stats.cancels += 1
            self.stats.last_action = "Scheduled cancel-all"
        except Exception:
            self.stats.last_action = "cancel-all: attempted"
        self.live.clear()

    def close_position(self):
        if not self.cfg.USER_ADDR:
            self.stats.last_action = "No USER_ADDR; skip close."
            return

        qty = Decimal(0)
        try:
            data = user_spot_balances(self.cfg.USER_ADDR)
            target = self.asset.name.split("/")[0] if "/" in self.asset.name else self.asset.name
            for row in data:
                token = str(row.get("token") or row.get("symbol") or "")
                if token.upper() == target.upper():
                    qty = to_decimal_safe(row.get("total") or row.get("available") or "0", "balance.total")
                    break
        except Exception:
            qty = Decimal(0)

        if qty <= 0:
            self.stats.last_action = "No base position to close."
            return

        try:
            place_market_ioc(self.cfg, self.asset, side_buy=False, sz=qty)
            self.stats.closes += 1
            self.stats.last_action = f"Close position IOC sell {qty}"
        except Exception:
            self.stats.last_action = "close position: attempted"

    def prune_stale(self):
        """Auto-cancel open orders whose age > ORDER_TTL_SEC (per-cloid)."""
        if not self.live:
            return
        ttl = int(getattr(self.cfg, "ORDER_TTL_SEC", 0) or 0)
        if ttl <= 0:
            return

        now = time.time()
        cutoff = now - ttl
        expired = [c for c, ts in list(self.live.items()) if ts < cutoff]
        if not expired:
            return

        canceled = 0
        for c in expired:
            try:
                cancel_by_cloid(self.cfg, self.asset.asset_id, c)
                canceled += 1
            except Exception:
                pass
            finally:
                self.live.pop(c, None)

        if canceled:
            self.stats.cancels += canceled
            self.stats.last_action = f"Auto-cancel {canceled} stale order(s)"

    def _choose_side(self) -> bool | None:
        """True=buy, False=sell, None=done for this minute."""
        buy_rem = max(0, self.cfg.BUY_PER_MIN - self.stats.buys_this_min)
        sell_rem = max(0, self.cfg.SELL_PER_MIN - self.stats.sells_this_min)
        if buy_rem == 0 and sell_rem == 0:
            return None

        imbalance = self.stats.total_buy - self.stats.total_sell
        if sell_rem > 0 and imbalance >= self.cfg.IMBALANCE_SELL_BOOST:
            return False

        if sell_rem > buy_rem:
            return False
        if buy_rem > sell_rem:
            return True

        return not self._last_side

    def run(self):
        assert (
            self.cfg.BUY_PER_MIN + self.cfg.SELL_PER_MIN == self.cfg.ORDERS_PER_MINUTE
        ), "BUY_PER_MIN + SELL_PER_MIN must equal ORDERS_PER_MINUTE"

        interval = 60.0 / max(1, self.cfg.ORDERS_PER_MINUTE)
        current_min = int(time.time() // 60)
        next_ts = time.time()

        while True:
            now = time.time()
            if now < next_ts:
                self.prune_stale()
                render_panel(self.cfg, self.asset, self.stats)
                time.sleep(max(0.0, min(0.25, next_ts - now)))
                continue

            minute_now = int(time.time() // 60)
            if minute_now != current_min:
                current_min = minute_now
                self.stats.minute_key = current_min
                self.stats.buys_this_min = 0
                self.stats.sells_this_min = 0
                self._last_side = True if self.cfg.START_SIDE == "sell" else False

            mid = self.compute_band()
            if mid is None:
                self.stats.last_action = "Waiting for mid..."
                render_panel(self.cfg, self.asset, self.stats)
                next_ts += interval
                continue

            if not self.in_range(mid):
                self.stats.last_action = (
                    f"⛔ Mid {mid:.6f} out of range [{self.range_lo}, {self.range_hi}] → cancel+close"
                )
                render_panel(self.cfg, self.asset, self.stats)
                self.cancel_all()
                self.close_position()
                next_ts += interval
                continue

            side = self._choose_side()
            if side is None:
                self.stats.last_action = "Minute quotas reached"
                render_panel(self.cfg, self.asset, self.stats)
                next_ts += interval
                continue

            self.place_one(side, mid)
            self.prune_stale()
            self._last_side = side

            render_panel(self.cfg, self.asset, self.stats)
            next_ts += interval