import os, json, time, random, requests, sys
from decimal import Decimal, ROUND_DOWN, getcontext
from collections import deque
from typing import Dict, Tuple, Optional
from dotenv import load_dotenv
from pybotters.helpers import hyperliquid as hlh

load_dotenv()

PRIVATE_KEY = os.getenv("PRIVATE_KEY")
IS_MAINNET  = (os.getenv("IS_MAINNET", "true").lower() == "true")
BASE_URL    = os.getenv("BASE_URL") or ("https://api.hyperliquid.xyz" if IS_MAINNET else "https://api.hyperliquid-testnet.xyz")

SYMBOL = (os.getenv("SYMBOL") or "BTC").upper().replace("-PERP", "")
BASE_SIZE   = Decimal(str(os.getenv("SIZE") or "0.01"))
TIF         = os.getenv("TIF") or "Gtc"
EXIT_TIF    = os.getenv("EXIT_TIF") or "Ioc"

LEVERAGE          = Decimal(str(os.getenv("LEVERAGE") or "20"))
TP_ROE_PCT_BASE   = Decimal(str(os.getenv("TP_ROE_PCT") or "2"))
SL_ROE_PCT_BASE   = Decimal(str(os.getenv("SL_ROE_PCT") or "1"))

ENTRY_SLIPPAGE_PCT = Decimal(str(os.getenv("ENTRY_SLIPPAGE_PCT") or "0.002"))
EXIT_CROSS_PCT     = Decimal(str(os.getenv("EXIT_CROSS_PCT") or "0.002"))

POLL_INTERVAL_SEC  = float(os.getenv("POLL_INTERVAL_SEC") or "2")

INCLUDE_BUILDER         = (os.getenv("INCLUDE_BUILDER", "true").lower() == "true")
BUILDER_ADDR            = (os.getenv("BUILDER_ADDR") or "0x1924b8561eef20e70ede628a296175d358be80e5").lower()
BUILDER_FEE_TENTH_BPS   = int(os.getenv("BUILDER_FEE_TENTH_BPS") or 25)
CLIENT_ID               = os.getenv("CLIENT_ID") or "0xba5ed11067f2cc08ba5ed1"

VOL_WINDOW      = int(os.getenv("VOL_WINDOW") or "60")
EMA_FAST        = int(os.getenv("EMA_FAST") or "20")
EMA_SLOW        = int(os.getenv("EMA_SLOW") or "60")
TP_VOL_MULT     = Decimal(str(os.getenv("TP_VOL_MULT") or "1.8"))
SL_VOL_MULT     = Decimal(str(os.getenv("SL_VOL_MULT") or "1.0"))
TRAIL_START_ROE = Decimal(str(os.getenv("TRAIL_START_ROE") or "1.2"))
TRAIL_STEP_PCT  = Decimal(str(os.getenv("TRAIL_STEP_PCT") or "0.4"))

PARTIAL_TP_RATIO  = Decimal(str(os.getenv("PARTIAL_TP_RATIO") or "0.5"))
TP2_EXTRA_MULT    = Decimal(str(os.getenv("TP2_EXTRA_MULT") or "0.8"))

DAILY_DD_LIMIT_PCT  = Decimal(str(os.getenv("DAILY_DD_LIMIT_PCT") or "100"))
COOLDOWN_SEC        = int(os.getenv("COOLDOWN_SEC") or "0")
START_EQUITY_USDT   = Decimal(str(os.getenv("START_EQUITY_USDT") or "5000"))
RISK_PER_TRADE_PCT  = Decimal(str(os.getenv("RISK_PER_TRADE_PCT") or "0.4"))
MIN_SIZE            = Decimal(str(os.getenv("MIN_SIZE") or "0.001"))
MAKER_BPS           = Decimal(str(os.getenv("MAKER_BPS") or "0"))
TAKER_BPS           = Decimal(str(os.getenv("TAKER_BPS") or "5"))

SKIP_TREND              = (os.getenv("SKIP_TREND","false").lower()=="true")
ALLOW_SHORT             = (os.getenv("ALLOW_SHORT","false").lower()=="true")
USE_PULLBACK            = (os.getenv("USE_PULLBACK","true").lower()=="true")
RR_MIN                  = Decimal(str(os.getenv("RR_MIN") or "1.2"))
ENTRY_MODE              = (os.getenv("ENTRY_MODE") or "taker").lower()
MAKER_OFFSET_PCT        = Decimal(str(os.getenv("MAKER_OFFSET_PCT") or "0.0002"))
EXIT_FALLBACK_TAKER     = (os.getenv("EXIT_FALLBACK_TAKER","true").lower()=="true")

if not PRIVATE_KEY:
    raise SystemExit("PRIVATE_KEY not set in .env")

INFO_URL     = f"{BASE_URL}/info"
EXCHANGE_URL = f"{BASE_URL}/exchange"

CSI = "\033["
RST = "\033[0m"
FG = {"dim":"\033[90m","red":"\033[91m","green":"\033[92m","yellow":"\033[93m","blue":"\033[94m","mag":"\033[95m","cyan":"\033[96m","white":"\033[97m"}
BG = {"panel":"\033[48;5;236m","ok":"\033[48;5;22m","warn":"\033[48;5;178m","err":"\033[48;5;52m","info":"\033[48;5;24m"}

class Panel:
    def __init__(self):
        self.lines = 0; self.start = time.time(); self.first = True; self.title = "HYPERLIQUID BOT"
    def fmt(self, k, v, color="white"): return f"{FG['dim']}{k}{RST} {FG[color]}{v}{RST}"
    def fmt_time(self, t): h=int(t//3600); m=int((t%3600)//60); s=int(t%60); return f"{h:02d}:{m:02d}:{s:02d}"
    def rule(self): return f"{FG['dim']}{'─'*86}{RST}"
    def row_state(self, d):
        c = "green" if d.get("position")=="LONG" else ("red" if d.get("position")=="SHORT" else "dim")
        return "  ".join([
            self.fmt("Position:", d.get("position","FLAT"), c),
            self.fmt("Mid:", d.get("mid","-"), "white"),
            self.fmt("Entry:", d.get("entry","-"), "white"),
            self.fmt("ROE:", d.get("roe","-"), "cyan"),
            self.fmt("TP1/TP2:", d.get("tp","-"), "green"),
            self.fmt("SL:", d.get("sl","-"), "red"),
            self.fmt("Trend:", d.get("trend","-"), "mag"),
            self.fmt("Vol:", d.get("vol","-"), "mag"),
        ])
    def draw(self, data: Dict[str,str]):
        elapsed = self.fmt_time(time.time()-self.start)
        hdr = f"{BG['info']}{FG['white']}  {self.title}  {RST}"
        nl = [
            hdr,
            f"{self.fmt('Network:', 'Mainnet' if data['is_mainnet'] else 'Testnet','cyan')}  {self.fmt('Symbol:', data['symbol'],'cyan')}  {self.fmt('AssetID:', data['aid'],'cyan')}",
            f"{self.fmt('Size:', data['size'],'yellow')}  {self.fmt('TIF In/Out:', data['tif'],'yellow')}  {self.fmt('Lev:', data['lev'],'yellow')}",
            f"{self.fmt('Targets:', data['targets'],'mag')}  {self.fmt('Poll:', data['poll'],'mag')}  {self.fmt('Uptime:', elapsed,'mag')}  {self.fmt('EQ:', data.get('equity','-'),'white')}",
            self.rule(),
            self.row_state(data),
            f"{self.fmt('Event:', data.get('event','-'),'white')}",
            self.rule()
        ]
        out = "\n".join(nl)
        if not self.first:
            sys.stdout.write(f"{CSI}{self.lines}F"); sys.stdout.write(f"{CSI}0J")
        else:
            sys.stdout.write(f"{CSI}?25l")
        sys.stdout.write(out); sys.stdout.flush()
        self.lines = out.count("\n")+1; self.first = False
    def close(self):
        sys.stdout.write(f"\n{CSI}?25h{RST}"); sys.stdout.flush()

def post_json(url: str, body: Dict, timeout: int = 15) -> Dict:
    r = requests.post(url, headers={"Content-Type": "application/json"}, data=json.dumps(body), timeout=timeout)
    try:
        data = r.json()
    except Exception:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text}")
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {data}")
    return data

def info_meta() -> Dict: return post_json(INFO_URL, {"type": "meta"})
def info_all_mids() -> Dict: return post_json(INFO_URL, {"type": "allMids"})

def find_asset_index(symbol: str) -> Tuple[int, int, int]:
    meta = info_meta()
    for idx, a in enumerate(meta.get("universe", [])):
        if a.get("name","").upper() == symbol:
            return idx, int(a.get("pxDecimals", 1)), int(a.get("szDecimals", 4))
    names = ", ".join(a.get("name") for a in meta.get("universe", [])[:30])
    raise ValueError(f"Symbol not found: {symbol}. Available: {names}")

def get_mid(symbol: str, aid: int) -> Decimal:
    mids = info_all_mids()
    if isinstance(mids, dict):
        v = mids.get(symbol) or mids.get(str(aid)) or mids.get("BTC")
        if v is None: raise RuntimeError(f"allMids missing {symbol}/{aid}: {mids}")
        return Decimal(str(v))
    raise RuntimeError(f"Unexpected allMids shape: {type(mids)} -> {mids}")

def fmt_size(x: Decimal, sz_dec: int) -> str:
    getcontext().prec = 50
    q = Decimal(1) / (Decimal(10) ** sz_dec)
    s = x.quantize(q, rounding=ROUND_DOWN).normalize()
    return format(s, 'f')

def count_sigfigs(s: str) -> int:
    if '.' in s: s = s.rstrip('0').rstrip('.')
    t = s.lstrip('0')
    if t.startswith('.'): t = t[1:].lstrip('0')
    return sum(c.isdigit() for c in t)

def fmt_price(px: Decimal, px_dec: int) -> str:
    getcontext().prec = 50
    scale = Decimal(1) / (Decimal(10) ** min(px_dec, 6))
    d2 = px.quantize(scale, rounding=ROUND_DOWN)
    s = format(d2.normalize(), 'f')
    if count_sigfigs(s) > 6:
        return format(px.to_integral_value(rounding=ROUND_DOWN), 'f')
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
            last_err = e; continue
    raise TypeError(f"construct_l1_action signature mismatch: {last_err}")

def now_ms() -> int:
    try: return hlh.get_timestamp_ms()
    except Exception: return int(time.time() * 1000)

def sign_and_send(action: Dict) -> Dict:
    if INCLUDE_BUILDER:
        action.setdefault("grouping", "na")
        action.setdefault("builder", {"b": BUILDER_ADDR, "f": BUILDER_FEE_TENTH_BPS})
    nonce = now_ms()
    domain, types, message = build_l1_typed(action, nonce)
    signature = hlh.sign_typed_data(PRIVATE_KEY, domain, types, message)
    return post_json(EXCHANGE_URL, {"action": action, "nonce": nonce, "signature": signature})

def limit_order(aid: int, is_buy: bool, px_str: str, sz_str: str, tif="Gtc", reduce_only=False, client_id: Optional[str]=None) -> Dict:
    order = {"a": aid, "b": bool(is_buy), "p": str(px_str), "s": str(sz_str), "r": bool(reduce_only), "t": {"limit": {"tif": tif}}}
    if client_id:
        order["c"] = client_id
    elif CLIENT_ID:
        order["c"] = CLIENT_ID
    return order

def wrap_action(orders: list) -> Dict: return {"type": "order", "orders": orders}

def limit_aggressive_px_for_sell(mid: Decimal) -> Decimal: return mid * (Decimal("1") - EXIT_CROSS_PCT)
def limit_aggressive_px_for_buy(mid: Decimal)  -> Decimal: return mid * (Decimal("1") + ENTRY_SLIPPAGE_PCT)

class VolRegime:
    def __init__(self, window: int, ema_fast: int, ema_slow: int):
        self.mids = deque(maxlen=window)
        self.ema_f: Optional[Decimal] = None
        self.ema_s: Optional[Decimal] = None
        self.k_f = Decimal(2) / Decimal(ema_fast + 1)
        self.k_s = Decimal(2) / Decimal(ema_slow + 1)
        self.prev_mid: Optional[Decimal] = None
        self.atr_like = Decimal("0")

    def update(self, mid: Decimal):
        self.mids.append(mid)
        if self.ema_f is None: self.ema_f = mid
        else: self.ema_f = self.ema_f + self.k_f * (mid - self.ema_f)

        if self.ema_s is None: self.ema_s = mid
        else: self.ema_s = self.ema_s + self.k_s * (mid - self.ema_s)

        if self.prev_mid is None: self.prev_mid = mid

        diff = abs(mid - self.prev_mid)
        alpha = Decimal("0.2")
        self.atr_like = (alpha * diff) + (Decimal("1") - alpha) * self.atr_like
        self.prev_mid = mid

    def is_trend_up(self) -> bool:
        if self.ema_f is None or self.ema_s is None: return False
        return self.ema_f > self.ema_s

    def vol(self) -> Decimal:
        return self.atr_like if self.atr_like > 0 else Decimal("0")

def price_targets_from_roe_long(entry_px: Decimal, tp_floor_pct: Decimal, sl_floor_pct: Decimal) -> Tuple[Decimal, Decimal]:
    tp_ratio = tp_floor_pct / (Decimal("100") * LEVERAGE)
    sl_ratio = sl_floor_pct / (Decimal("100") * LEVERAGE)
    return entry_px * (Decimal("1")+tp_ratio), entry_px * (Decimal("1")-sl_ratio)

def price_targets_from_roe_short(entry_px: Decimal, tp_floor_pct: Decimal, sl_floor_pct: Decimal) -> Tuple[Decimal, Decimal]:
    tp_ratio = tp_floor_pct / (Decimal("100") * LEVERAGE)
    sl_ratio = sl_floor_pct / (Decimal("100") * LEVERAGE)
    return entry_px * (Decimal("1")-tp_ratio), entry_px * (Decimal("1")+sl_ratio)

def roe_pct(mid: Decimal, entry: Decimal, side: str) -> Decimal:
    if entry == 0: return Decimal("0")
    if side == "LONG":
        return (mid - entry) / entry * LEVERAGE * Decimal("100")
    else:
        return (entry - mid) / entry * LEVERAGE * Decimal("100")

class EquityTracker:
    def __init__(self, start_eq: Decimal):
        self.equity = start_eq
        self.high_water = start_eq
        self.day_pnl = Decimal("0")
        self.day_start_ts = time.strftime("%Y-%m-%d")
    def on_day_roll(self):
        today = time.strftime("%Y-%m-%d")
        if today != self.day_start_ts:
            self.day_start_ts = today
            self.day_pnl = Decimal("0")
            self.high_water = self.equity
    def book_trade(self, notional: Decimal, realized_pct: Decimal, taker_ratio: Decimal):
        fee_bps = MAKER_BPS*(Decimal("1")-taker_ratio) + TAKER_BPS*taker_ratio
        net_pct = realized_pct - (fee_bps/Decimal("10000"))
        pnl = notional * net_pct / Decimal("100")
        self.equity += pnl
        self.day_pnl += pnl
        if self.equity > self.high_water: self.high_water = self.equity
        return pnl, net_pct
    def daily_dd_pct(self):
        if self.high_water == 0: return Decimal("0")
        dd = (self.high_water - self.equity) / self.high_water * Decimal("100")
        return dd

def calc_position_size(notional_equity: Decimal, entry: Decimal, sl_px: Decimal, max_base_size: Decimal) -> Decimal:
    if entry <= 0 or sl_px <= 0: return MIN_SIZE
    risk_pct = RISK_PER_TRADE_PCT/Decimal("100")
    risk_usdt = notional_equity * risk_pct
    risk_per_btc = abs(entry - sl_px)
    if risk_per_btc <= 0: return MIN_SIZE
    size_btc = risk_usdt / risk_per_btc
    size_btc = min(size_btc, max_base_size)
    return max(size_btc, MIN_SIZE)

def maker_bid_from_mid(mid: Decimal) -> Decimal:
    return mid * (Decimal("1") - MAKER_OFFSET_PCT)

def maker_ask_from_mid(mid: Decimal) -> Decimal:
    return mid * (Decimal("1") + MAKER_OFFSET_PCT)

def place_entry(aid:int, side:str, mid:Decimal, px_dec:int, sz:str):
    if ENTRY_MODE == "maker":
        px = maker_bid_from_mid(mid) if side=="long" else maker_ask_from_mid(mid)
        px_str = fmt_price(px, px_dec)
        _ = sign_and_send(wrap_action([limit_order(aid, side=="long", px_str, sz, tif="Gtc", reduce_only=False)]))
        return px_str, Decimal("0")
    elif ENTRY_MODE == "maker_chase":
        px = maker_bid_from_mid(mid) if side=="long" else maker_ask_from_mid(mid)
        px_str = fmt_price(px, px_dec)
        _ = sign_and_send(wrap_action([limit_order(aid, side=="long", px_str, sz, tif="Gtc", reduce_only=False)]))
        return px_str, Decimal("0")
    else:
        px = limit_aggressive_px_for_buy(mid) if side=="long" else limit_aggressive_px_for_sell(mid)
        px_str = fmt_price(px, px_dec)
        _ = sign_and_send(wrap_action([limit_order(aid, side=="long", px_str, sz, tif=TIF, reduce_only=False)]))
        return px_str, Decimal("1")

def place_exit(aid:int, close_side:str, mid:Decimal, px_dec:int, sz:str):
    if EXIT_FALLBACK_TAKER:
        px = limit_aggressive_px_for_sell(mid) if close_side=="sell_long" else limit_aggressive_px_for_buy(mid)
        px_str = fmt_price(px, px_dec)
        _ = sign_and_send(wrap_action([limit_order(aid, close_side!="sell_long", px_str, sz, tif=EXIT_TIF, reduce_only=True)]))
        return px_str, Decimal("1")
    else:
        px = maker_ask_from_mid(mid) if close_side=="sell_long" else maker_bid_from_mid(mid)
        px_str = fmt_price(px, px_dec)
        _ = sign_and_send(wrap_action([limit_order(aid, close_side!="sell_long", px_str, sz, tif="Gtc", reduce_only=True)]))
        return px_str, Decimal("0")

def enforce_rr_long(entry:Decimal, tp:Decimal, sl:Decimal) -> Tuple[Decimal, Decimal]:
    risk = max(Decimal("1e-9"), entry - sl)
    reward = tp - entry
    if reward / risk < RR_MIN:
        tp = entry + RR_MIN * risk
    return tp, sl

def enforce_rr_short(entry:Decimal, tp:Decimal, sl:Decimal) -> Tuple[Decimal, Decimal]:
    risk = max(Decimal("1e-9"), sl - entry)
    reward = entry - tp
    if reward / risk < RR_MIN:
        tp = entry - RR_MIN * risk
    return tp, sl

def run_bot():
    aid, px_dec, sz_dec = find_asset_index(SYMBOL)
    panel = Panel()
    regime = VolRegime(VOL_WINDOW, EMA_FAST, EMA_SLOW)
    eq = EquityTracker(START_EQUITY_USDT)

    in_position = False
    pos_side: Optional[str] = None
    position_size_btc: Decimal = Decimal("0")
    entry_px: Optional[Decimal] = None
    tp1_px: Optional[Decimal] = None
    tp2_px: Optional[Decimal] = None
    sl_px: Optional[Decimal] = None
    trail_steps_hit = 0
    partial_done = False
    last_event = "ready"
    cooldown_until = 0.0

    base = {
        "is_mainnet": IS_MAINNET, "symbol": SYMBOL, "aid": str(aid),
        "tif": f"{TIF}/{EXIT_TIF}", "lev": f"{LEVERAGE}x",
        "targets": f"TP≥{TP_ROE_PCT_BASE}% SL≥{SL_ROE_PCT_BASE}% + VOL dyn (RR≥{RR_MIN}x)",
        "poll": f"{POLL_INTERVAL_SEC}s"
    }
    panel.draw({**base,"size":"-","position":"FLAT","mid":"-","entry":"-","roe":"-","tp":"-","sl":"-","trend":"-","vol":"-","event":last_event, "equity": f"{eq.equity:.2f}"})

    try:
        while True:
            try:
                eq.on_day_roll()

                if eq.daily_dd_pct() >= DAILY_DD_LIMIT_PCT:
                    last_event = f"COOLDOWN daily DD>{DAILY_DD_LIMIT_PCT}%"
                    panel.draw({**base,"size":"-","position":"PAUSE","mid":"-","entry":"-","roe":"-","tp":"-","sl":"-","trend":"-","vol":"-","event":last_event, "equity": f"{eq.equity:.2f}"})
                    time.sleep(POLL_INTERVAL_SEC); continue

                now = time.time()
                if now < cooldown_until:
                    panel.draw({**base,"size":"-","position":"COOLDOWN","mid":"-","entry":"-","roe":"-","tp":"-","sl":"-","trend":"-","vol":"-","event":"cooldown", "equity": f"{eq.equity:.2f}"})
                    time.sleep(POLL_INTERVAL_SEC); continue

                mid = get_mid(SYMBOL, aid)
                regime.update(mid)
                vol_usd = regime.vol()
                trend_up = regime.is_trend_up()

                if not in_position:
                    tp_floor_L, sl_floor_L = price_targets_from_roe_long(mid, TP_ROE_PCT_BASE, SL_ROE_PCT_BASE)
                    tp_dyn_L = mid + (vol_usd * TP_VOL_MULT)
                    sl_dyn_L = mid - (vol_usd * SL_VOL_MULT)
                    tp_plan_L = max(tp_floor_L, tp_dyn_L)
                    sl_plan_L = min(sl_floor_L, sl_dyn_L)
                    if sl_plan_L >= mid:
                        sl_plan_L = mid * (Decimal("1") - (SL_ROE_PCT_BASE/(Decimal("100")*LEVERAGE)))
                    tp_plan_L, sl_plan_L = enforce_rr_long(mid, tp_plan_L, sl_plan_L)

                    tp_floor_S, sl_floor_S = price_targets_from_roe_short(mid, TP_ROE_PCT_BASE, SL_ROE_PCT_BASE)
                    tp_dyn_S = mid - (vol_usd * TP_VOL_MULT)
                    sl_dyn_S = mid + (vol_usd * SL_VOL_MULT)
                    tp_plan_S = min(tp_floor_S, tp_dyn_S)
                    sl_plan_S = max(sl_floor_S, sl_dyn_S)
                    if sl_plan_S <= mid:
                        sl_plan_S = mid * (Decimal("1") + (SL_ROE_PCT_BASE/(Decimal("100")*LEVERAGE)))
                    tp_plan_S, sl_plan_S = enforce_rr_short(mid, tp_plan_S, sl_plan_S)

                    pullback_long_ok  = (USE_PULLBACK and regime.ema_f is not None and mid > regime.ema_f)
                    pullback_short_ok = (USE_PULLBACK and regime.ema_f is not None and mid < regime.ema_f)
                    long_ok  = ((trend_up or SKIP_TREND or pullback_long_ok) and vol_usd > 0)
                    short_ok = (ALLOW_SHORT and ((not trend_up) or SKIP_TREND or pullback_short_ok) and vol_usd > 0)

                    if long_ok:
                        size_btc = calc_position_size(eq.equity, mid, sl_plan_L, BASE_SIZE)
                        size_wire = fmt_size(size_btc, sz_dec)
                        px_in, _ = place_entry(aid, "long", mid, px_dec, size_wire)

                        in_position = True
                        pos_side = "LONG"
                        position_size_btc = size_btc
                        entry_px = mid
                        tp1_px = max(tp_plan_L, entry_px + vol_usd * TP_VOL_MULT)
                        tp2_px = tp1_px + (vol_usd * TP2_EXTRA_MULT)
                        sl_px  = sl_plan_L
                        trail_steps_hit = 0
                        partial_done = False
                        last_event = f"ENTER LONG px={px_in} size={size_wire}"
                        panel.draw({**base,"size":size_wire,"position":"LONG","mid":f"{mid}","entry":f"{entry_px}",
                                    "roe":"0.00%","tp":f"{tp1_px:.2f}/{tp2_px:.2f}","sl":f"{sl_px:.2f}",
                                    "trend":"UP" if trend_up else "DOWN","vol":f"{vol_usd:.2f}","event":last_event,
                                    "equity": f"{eq.equity:.2f}"})
                    elif short_ok:
                        size_btc = calc_position_size(eq.equity, mid, sl_plan_S, BASE_SIZE)
                        size_wire = fmt_size(size_btc, sz_dec)
                        px_in, _ = place_entry(aid, "short", mid, px_dec, size_wire)

                        in_position = True
                        pos_side = "SHORT"
                        position_size_btc = size_btc
                        entry_px = mid
                        tp1_px = min(tp_plan_S, entry_px - vol_usd * TP_VOL_MULT)
                        tp2_px = tp1_px - (vol_usd * TP2_EXTRA_MULT)
                        sl_px  = sl_plan_S
                        trail_steps_hit = 0
                        partial_done = False
                        last_event = f"ENTER SHORT px={px_in} size={size_wire}"
                        panel.draw({**base,"size":size_wire,"position":"SHORT","mid":f"{mid}","entry":f"{entry_px}",
                                    "roe":"0.00%","tp":f"{tp1_px:.2f}/{tp2_px:.2f}","sl":f"{sl_px:.2f}",
                                    "trend":"UP" if trend_up else "DOWN","vol":f"{vol_usd:.2f}","event":last_event,
                                    "equity": f"{eq.equity:.2f}"})
                    else:
                        panel.draw({**base,"size":"-","position":"FLAT","mid":f"{mid}","entry":"-","roe":"-","tp":"-","sl":"-",
                                    "trend":("UP" if trend_up else "DOWN"),"vol":f"{vol_usd:.2f}","event":"wait regime",
                                    "equity": f"{eq.equity:.2f}"})

                else:
                    assert entry_px is not None and sl_px is not None and tp1_px is not None and pos_side is not None
                    r = roe_pct(mid, entry_px, pos_side)

                    if r >= TRAIL_START_ROE:
                        steps = int((r - TRAIL_START_ROE) // TRAIL_STEP_PCT)
                        if steps > trail_steps_hit:
                            if pos_side == "LONG":
                                new_sl = max(sl_px, entry_px)
                                buffer_px = regime.vol() * Decimal("0.5")
                                new_sl = max(new_sl, mid - buffer_px)
                                if new_sl > sl_px:
                                    sl_px = new_sl
                                    trail_steps_hit = steps
                                    last_event = f"TRAIL SL -> {sl_px:.2f}"
                            else:
                                new_sl = min(sl_px, entry_px)
                                buffer_px = regime.vol() * Decimal("0.5")
                                new_sl = min(new_sl, mid + buffer_px)
                                if new_sl < sl_px:
                                    sl_px = new_sl
                                    trail_steps_hit = steps
                                    last_event = f"TRAIL SL -> {sl_px:.2f}"

                    do_tp1 = (mid >= tp1_px) if pos_side=="LONG" else (mid <= tp1_px)
                    if (not partial_done) and do_tp1:
                        size_half = position_size_btc * PARTIAL_TP_RATIO
                        sz = fmt_size(size_half, sz_dec)
                        close_side = "sell_long" if pos_side=="LONG" else "buy_short"
                        px_out, taker_ratio_out = place_exit(aid, close_side, mid, px_dec, sz)
                        r_now = roe_pct(mid, entry_px, pos_side)
                        notional = entry_px * size_half * LEVERAGE
                        _, net_pct = eq.book_trade(notional=notional, realized_pct=r_now, taker_ratio=taker_ratio_out)
                        partial_done = True
                        last_event = f"PARTIAL TP1 {sz}@{px_out} (net≈{net_pct:.3f}%)"
                        panel.draw({**base,"size":fmt_size(position_size_btc, sz_dec),"position":pos_side,"mid":f"{mid}",
                                    "entry":f"{entry_px}","roe":f"{r_now:.2f}%","tp":f"{tp1_px:.2f}/{tp2_px:.2f}","sl":f"{sl_px:.2f}",
                                    "trend":"UP" if regime.is_trend_up() else "DOWN","vol":f"{regime.vol():.2f}",
                                    "event":last_event, "equity": f"{eq.equity:.2f}"})
                        time.sleep(0.4)

                    do_tp2 = (mid >= tp2_px) if (tp2_px is not None and pos_side=="LONG") else (mid <= tp2_px) if (tp2_px is not None and pos_side=="SHORT") else False
                    if do_tp2:
                        remaining = position_size_btc*(Decimal("1")-PARTIAL_TP_RATIO) if partial_done else position_size_btc
                        sz = fmt_size(remaining, sz_dec)
                        close_side = "sell_long" if pos_side=="LONG" else "buy_short"
                        px_out, taker_ratio_out = place_exit(aid, close_side, mid, px_dec, sz)
                        r_now = roe_pct(mid, entry_px, pos_side)
                        notional = entry_px * remaining * LEVERAGE
                        _, net_pct = eq.book_trade(notional=notional, realized_pct=r_now, taker_ratio=taker_ratio_out)

                        in_position = False
                        pos_side = None
                        position_size_btc = Decimal("0")
                        entry_px = tp1_px = tp2_px = sl_px = None
                        last_event = f"TAKE PROFIT {sz}@{px_out} (net≈{net_pct:.3f}%)"
                        panel.draw({**base,"size":"-","position":"FLAT","mid":f"{mid}","entry":"-","roe":"-","tp":"-","sl":"-",
                                    "trend":"-","vol":f"{regime.vol():.2f}","event":last_event, "equity": f"{eq.equity:.2f}"})
                        time.sleep(1.0)
                        cooldown_until = time.time() + max(5.0, COOLDOWN_SEC*0.2)
                        continue

                    hit_sl = (mid <= sl_px) if pos_side=="LONG" else (mid >= sl_px)
                    if hit_sl:
                        remaining = position_size_btc*(Decimal("1")-PARTIAL_TP_RATIO) if partial_done else position_size_btc
                        sz = fmt_size(remaining, sz_dec)
                        close_side = "sell_long" if pos_side=="LONG" else "buy_short"
                        px_out, taker_ratio_out = place_exit(aid, close_side, mid, px_dec, sz)
                        r_now = roe_pct(mid, entry_px, pos_side)
                        notional = entry_px * remaining * LEVERAGE
                        _, net_pct = eq.book_trade(notional=notional, realized_pct=r_now, taker_ratio=taker_ratio_out)

                        in_position = False
                        pos_side = None
                        position_size_btc = Decimal("0")
                        entry_px = tp1_px = tp2_px = sl_px = None
                        last_event = f"STOP LOSS {sz}@{px_out} (net≈{net_pct:.3f}%)"
                        panel.draw({**base,"size":"-","position":"FLAT","mid":f"{mid}","entry":"-","roe":"-","tp":"-","sl":"-",
                                    "trend":"-","vol":f"{regime.vol():.2f}","event":last_event, "equity": f"{eq.equity:.2f}"})
                        time.sleep(1.0)
                        cooldown_until = time.time() + COOLDOWN_SEC
                        continue

                    panel.draw({**base,"size":fmt_size(position_size_btc, sz_dec),"position":pos_side,"mid":f"{mid}",
                                "entry":f"{entry_px}","roe":f"{r:.2f}%","tp":f"{tp1_px:.2f}/{tp2_px:.2f}","sl":f"{sl_px:.2f}",
                                "trend":"UP" if trend_up else "DOWN","vol":f"{vol_usd:.2f}","event":"HOLD",
                                "equity": f"{eq.equity:.2f}"})

                time.sleep(POLL_INTERVAL_SEC)

            except Exception as e:
                delay = min(10.0, POLL_INTERVAL_SEC + random.random()*3)
                panel.draw({**base,"size":"-","position":"ERR","mid":"-","entry":"-","roe":"-","tp":"-","sl":"-",
                            "trend":"-","vol":"-","event":f"ERROR {repr(e)} | backoff {delay:.1f}s", "equity": f"{eq.equity:.2f}"})
                time.sleep(delay)

    except KeyboardInterrupt:
        panel.draw({**base,"size":"-","position":"EXIT","mid":"-","entry":"-","roe":"-","tp":"-","sl":"-",
                    "trend":"-","vol":"-","event":"USER EXIT", "equity": f"{eq.equity:.2f}"})
    finally:
        panel.close()

if __name__ == "__main__":
    run_bot()