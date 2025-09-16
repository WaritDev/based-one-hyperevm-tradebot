# panel.py
import sys
import shutil
from decimal import Decimal

# Windows: ให้ ANSI ทำงาน
try:
    import colorama
    colorama.just_fix_windows_console()
except Exception:
    pass

# ===== Utils (ภายในไฟล์) =====
def _term_width(min_w: int = 80, max_w: int = 120) -> int:
    cols = shutil.get_terminal_size((100, 24)).columns
    return max(min_w, min(max_w, cols))

def _line(width: int, ch: str = "─") -> str:
    return ch * width

def _fmt_money(x: Decimal) -> str:
    return f"{x:.2f}"

def _human_time(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    if d: return f"{d}d {h}h {m}m {s}s"
    if h: return f"{h}h {m}m {s}s"
    if m: return f"{m}m {s}s"
    return f"{s}s"

def _get(cfg, *names, default=None):
    """อ่านค่า attr จาก cfg โดยรองรับทั้ง lower/UPPER case."""
    for n in names:
        if hasattr(cfg, n):
            return getattr(cfg, n)
    return default

def _bar(current: int, total: int, width: int = 20, label: str = "") -> str:
    total = max(1, int(total))
    current = max(0, min(int(current), total))
    fill = int((current / total) * width)
    return f"[{'█'*fill}{' '*(width-fill)}] {current}/{total}" + (f" {label}" if label else "")

# ===== Public API =====
def init_panel():
    # ซ่อนเคอร์เซอร์ และวางเคอร์เซอร์ไว้มุมซ้ายบน
    sys.stdout.write("\x1b[?25l\x1b[H")
    sys.stdout.flush()

def teardown_panel():
    # แสดงเคอร์เซอร์กลับ
    sys.stdout.write("\x1b[?25h\n")
    sys.stdout.flush()

def render_panel(cfg, asset, st) -> None:
    """
    วาดแพแนล “คงที่” ไม่เลื่อนจอ:
    - ใช้ \x1b[H ย้ายเคอร์เซอร์ไปบรรทัดแรกทุกครั้ง
    - ใช้ \x1b[0J ลบตั้งแต่ตำแหน่งปัจจุบันถึงท้ายจอ (กันเศษบรรทัดเก่า)
    - ไม่มีบรรทัด Errors ตามที่ขอ
    """
    # สรุปค่า
    w = _term_width()
    uptime = _human_time(__import__("time").time() - st.started_at)

    total_orders   = st.total_buy + st.total_sell
    total_vol_base = st.vol_base_buy + st.vol_base_sell
    total_notional = st.notional_buy + st.notional_sell

    # รองรับทั้ง cfg.range_lower (เดิม) และ cfg.RANGE_LOWER (แบบใหม่)
    rng_lower = _get(cfg, "range_lower", "RANGE_LOWER")
    rng_upper = _get(cfg, "range_upper", "RANGE_UPPER")
    rng_pct   = _get(cfg, "range_pct",   "RANGE_PCT")
    size      = _get(cfg, "size", "SIZE", default=0)
    buy_pm    = _get(cfg, "buy_per_min", "BUY_PER_MIN", default=0)
    sell_pm   = _get(cfg, "sell_per_min", "SELL_PER_MIN", default=0)
    ops_pm    = _get(cfg, "orders_per_min", "ORDERS_PER_MINUTE", default=0)

    # ช่วงราคา
    range_str = ""
    if rng_lower is not None or rng_upper is not None or rng_pct is not None:
        if rng_lower is not None and rng_upper is not None:
            range_str = f"[{rng_lower} … {rng_upper}]"
        elif rng_pct is not None and st.last_mid is not None:
            lo = st.last_mid * (Decimal(1) - Decimal(rng_pct))
            hi = st.last_mid * (Decimal(1) + Decimal(rng_pct))
            range_str = f"[{lo:.6f} … {hi:.6f}]"
        else:
            range_str = "(range set)"

    # ความไม่สมดุลฝั่ง (Buy - Sell)
    imbalance = st.total_buy - st.total_sell

    # ย้ายเคอร์เซอร์ขึ้นบนสุด + ลบหน้าจอจากตำแหน่งนี้ลงไป เพื่อ “ไม่เลื่อน”
    out = []
    out.append("\x1b[H\x1b[0J")  # home + clear to end

    # Header
    out.append(f"┌{' Market Maker Bot ':=^{w-2}}┐")
    meta_left  = f"Pair: {asset.name}  Index: {asset.index}  AssetID: {asset.asset_id}"
    meta_right = f"Tick: {asset.tick_sz}  Lot: {asset.lot_sz}  Uptime: {uptime}"
    pad = max(1, w - 4 - len(meta_left) - len(meta_right))
    out.append(f"│ {meta_left}{' '*pad}{meta_right} │")
    out.append(f"├{_line(w-2)}┤")

    # Mid + Range
    mid_str = f"Mid: {st.last_mid:.6f}" if st.last_mid is not None else "Mid: (loading)"
    rng_str = f"Range: {range_str}" if range_str else "Range: (off)"
    out.append(f"│ {mid_str:<38} {rng_str:<{w-42}} │")
    out.append(f"├{_line(w-2)}┤")

    # Totals
    totals_l1 = f"Orders: {total_orders}  (Buy {st.total_buy} / Sell {st.total_sell})"
    totals_l2 = f"Volume (base): {total_vol_base}   Notional≈ {_fmt_money(total_notional)}"
    pad2 = max(1, w - 4 - len(totals_l1) - len(totals_l2))
    out.append(f"│ {totals_l1}{' '*pad2}{totals_l2} │")

    # Admin (ตัด Errors ออกตามคำขอ)
    admin_l = f"Cancels: {st.cancels}   Closes: {st.closes}   Imbalance(B-S): {imbalance:+d}"
    out.append(f"│ {admin_l:<{w-2}} │")
    out.append(f"├{_line(w-2)}┤")

    # Minute budgets + progress bar สั้น ๆ (ดูง่ายขึ้น)
    buy_bar  = _bar(st.buys_this_min,  buy_pm,  width=18, label="BUY/min")
    sell_bar = _bar(st.sells_this_min, sell_pm, width=18, label="SELL/min")
    out.append(f"│ {buy_bar:<{(w-3)//2}}{sell_bar:>{w-3-(w-3)//2}} │")

    # บรรทัดรวมเป้าหมาย/ขนาด
    goals = f"Target: {ops_pm} ops/min   Size: {size}"
    out.append(f"│ {goals:<{w-2}} │")

    out.append(f"├{_line(w-2)}┤")

    # Last action (ไม่มี error count)
    action = st.last_action or "(idle)"
    out.append(f"│ Last: {action:<{w-8}} │")

    out.append(f"└{_line(w-2, ch='=')}┘")

    sys.stdout.write("\n".join(out))
    sys.stdout.flush()