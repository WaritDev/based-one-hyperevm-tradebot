from dataclasses import dataclass, field
from decimal import Decimal
import time

@dataclass
class Stats:
    started_at: float = field(default_factory=lambda: time.time())
    total_buy: int = 0
    total_sell: int = 0
    vol_base_buy: Decimal = Decimal(0)
    vol_base_sell: Decimal = Decimal(0)
    notional_buy: Decimal = Decimal(0)
    notional_sell: Decimal = Decimal(0)
    cancels: int = 0
    closes: int = 0
    errors: int = 0
    minute_key: int = field(default_factory=lambda: int(time.time() // 60))
    buys_this_min: int = 0
    sells_this_min: int = 0
    last_mid: Decimal | None = None
    last_action: str = ""