# utils.py
import re, shutil, time
from decimal import Decimal, ROUND_DOWN, InvalidOperation
from typing import Tuple, Optional

COMMON_TICKS = [
    Decimal("0.000001"), Decimal("0.000005"), Decimal("0.00001"),
    Decimal("0.00005"),  Decimal("0.0001"),   Decimal("0.001")
]

# ---------- Decimal helpers (robust against messy strings) ----------
_number_re = re.compile(r"[-+]?\d+(?:\.\d+)?")

def _extract_number_loose(s: str) -> Optional[str]:
    """Pick the first well-formed decimal in s; tolerates trailing punctuation."""
    if s is None:
        return None
    # remove thousand separators if any
    s = str(s).replace(",", " ")
    m = _number_re.search(s)
    return m.group(0) if m else None

def to_decimal_safe(x, name: str = "value", *, loose: bool = False) -> Decimal:
    """
    Strict by default; if loose=True, extract the first decimal-like token
    (handles cases like '0.12583.' or '≈0.12583;').
    """
    if isinstance(x, Decimal):
        return x
    if x is None:
        raise ValueError(f"{name} is None")

    s = str(x).strip()
    if s.lower() in ("", "nan", "none", "null"):
        raise ValueError(f"{name} is empty or NaN: {repr(x)}")

    if loose:
        picked = _extract_number_loose(s)
        if picked is None:
            raise ValueError(f"{name} not a valid decimal (loose parse failed): {repr(x)}")
        s = picked

    try:
        return Decimal(s)
    except InvalidOperation as e:
        # last attempt: loose parse if not already tried
        if not loose:
            picked = _extract_number_loose(s)
            if picked:
                try:
                    return Decimal(picked)
                except InvalidOperation:
                    pass
        raise ValueError(f"{name} not a valid decimal: {repr(x)} ({e})")

def fmt_decimal_str(x, decimals: int) -> str:
    d = to_decimal_safe(x, "fmt_decimal_str.x")
    if decimals < 0:
        raise ValueError("fmt_decimal_str.decimals negative")
    q = Decimal(1) / (Decimal(10) ** decimals)
    s = d.quantize(q, rounding=ROUND_DOWN).normalize()
    return format(s, "f")

def decimals_of(d: Decimal) -> int:
    return max(0, -d.as_tuple().exponent)

def one_tick_from_dec(px_dec: int) -> Decimal:
    return Decimal(1) / (Decimal(10) ** px_dec)

def snap_to_step(value: Decimal, step: Decimal, direction: str = "down") -> Decimal:
    v  = to_decimal_safe(value, "snap.value")
    st = to_decimal_safe(step,  "snap.step")
    if st <= 0:
        return v
    q = (v / st)
    if direction == "up":
        base = q.to_integral_value(rounding=ROUND_DOWN)
        q = base if q == base else base + 1
    else:
        q = q.to_integral_value(rounding=ROUND_DOWN)
    snapped = q * st
    return snapped.quantize(st, rounding=ROUND_DOWN)

# ---------- Time / terminal ----------
def human_time(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    if d: return f"{d}d {h}h {m}m {s}s"
    if h: return f"{h}h {m}m {s}s"
    if m: return f"{m}m {s}s"
    return f"{s}s"

def term_width(minw=80, maxw=120) -> int:
    cols = shutil.get_terminal_size((100, 20)).columns
    return max(minw, min(maxw, cols))

_bbo_re = re.compile(r"bbo was\s+([^\s@]+)@([^\s]+)", re.IGNORECASE)

def find_bbo(err_msg: str) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    if not err_msg:
        return None, None
    m = _bbo_re.search(err_msg)
    if not m:
        return None, None
    try:
        from .utils import to_decimal_safe as _tds  # safe in both package/local contexts
    except Exception:
        _tds = to_decimal_safe
    try:
        bid = _tds(m.group(1), "BBO.bid", loose=True)
        ask = _tds(m.group(2), "BBO.ask", loose=True)
        return bid, ask
    except Exception:
        return None, None

def infer_tick_from_bbo(err_msg: str) -> Optional[Decimal]:
    bid, ask = find_bbo(err_msg)
    if bid is None or ask is None:
        return None
    d = max(decimals_of(bid), decimals_of(ask))
    return Decimal(1) / (Decimal(10) ** d) if d > 0 else Decimal(1)

def next_coarser_tick(current: Decimal) -> Optional[Decimal]:
    for t in COMMON_TICKS:
        if t > current:
            return t
    return None