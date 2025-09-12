import os, json, time, requests, sys
from decimal import Decimal, ROUND_DOWN, getcontext
from typing import Dict, Tuple, Optional
from dotenv import load_dotenv
from pybotters.helpers import hyperliquid as hlh

load_dotenv()

PRIVATE_KEY = os.getenv("PRIVATE_KEY")
IS_MAINNET  = (os.getenv("IS_MAINNET", "true").lower() == "true")
BASE_URL    = os.getenv("BASE_URL") or ("https://api.hyperliquid.xyz" if IS_MAINNET else "https://api.hyperliquid-testnet.xyz")

SYMBOL = (os.getenv("SYMBOL") or "BTC").upper().replace("-PERP", "")
SIZE   = Decimal(str(os.getenv("SIZE") or "0.01"))
TIF    = os.getenv("TIF") or "Gtc"
EXIT_TIF = os.getenv("EXIT_TIF") or "Ioc"

LEVERAGE    = Decimal(str(os.getenv("LEVERAGE") or "20"))
TP_ROE_PCT  = Decimal(str(os.getenv("TP_ROE_PCT") or "2"))
SL_ROE_PCT  = Decimal(str(os.getenv("SL_ROE_PCT") or "1"))

ENTRY_SLIPPAGE_PCT = Decimal(str(os.getenv("ENTRY_SLIPPAGE_PCT") or "0.002"))
EXIT_CROSS_PCT     = Decimal(str(os.getenv("EXIT_CROSS_PCT") or "0.002"))
POLL_INTERVAL_SEC  = float(os.getenv("POLL_INTERVAL_SEC") or "2")

INCLUDE_BUILDER         = (os.getenv("INCLUDE_BUILDER", "true").lower() == "true")
BUILDER_ADDR            = (os.getenv("BUILDER_ADDR") or "0x1924b8561eef20e70ede628a296175d358be80e5").lower()
BUILDER_FEE_TENTH_BPS   = int(os.getenv("BUILDER_FEE_TENTH_BPS") or 25)
CLIENT_ID               = os.getenv("CLIENT_ID") or "0xba5ed11067f2cc08ba5ed1"

if not PRIVATE_KEY:
    raise SystemExit("PRIVATE_KEY not set in .env")

INFO_URL     = f"{BASE_URL}/info"
EXCHANGE_URL = f"{BASE_URL}/exchange"

CSI = "\033["
RST = "\033[0m"
FG = {
    "dim":"\033[90m","red":"\033[91m","green":"\033[92m","yellow":"\033[93m","blue":"\033[94m","mag":"\033[95m","cyan":"\033[96m","white":"\033[97m"
}
BG = {"panel":"\033[48;5;236m","ok":"\033[48;5;22m","warn":"\033[48;5;178m","err":"\033[48;5;52m","info":"\033[48;5;24m"}

class Panel:
    def __init__(self):
        self.lines = 0
        self.start = time.time()
        self.first = True
        self.title = "HYPERLIQUID BOT"
    def fmt(self, k, v, color="white"):
        return f"{FG['dim']}{k}{RST} {FG[color]}{v}{RST}"
    def fmt_time(self, t):
        h = int(t//3600); m = int((t%3600)//60); s = int(t%60)
        return f"{h:02d}:{m:02d}:{s:02d}"
    def draw(self, data: Dict[str,str]):
        elapsed = self.fmt_time(time.time()-self.start)
        hdr = f"{BG['info']}{FG['white']}  {self.title}  {RST}"
        nl = []
        nl.append(hdr)
        nl.append(f"{self.fmt('Network:', 'Mainnet' if data['is_mainnet'] else 'Testnet','cyan')}  {self.fmt('Symbol:', data['symbol'],'cyan')}  {self.fmt('AssetID:', data['aid'],'cyan')}")
        nl.append(f"{self.fmt('Size:', data['size'],'yellow')}  {self.fmt('TIF In/Out:', data['tif'],'yellow')}  {self.fmt('Leverage:', data['lev'],'yellow')}")
        nl.append(f"{self.fmt('Targets:', data['targets'],'mag')}  {self.fmt('Poll:', data['poll'],'mag')}  {self.fmt('Uptime:', elapsed,'mag')}")
        nl.append(f"{self.rule()}")
        nl.append(self.row_state(data))
        nl.append(f"{self.fmt('Event:', data.get('event','-'),'white')}")
        nl.append(self.rule())
        out = "\n".join(nl)
        if not self.first:
            sys.stdout.write(f"{CSI}{self.lines}F")
            sys.stdout.write(f"{CSI}0J")
        else:
            sys.stdout.write(f"{CSI}?25l")
        sys.stdout.write(out)
        sys.stdout.flush()
        self.lines = out.count("\n")+1
        self.first = False
    def row_state(self, d):
        pos = d.get("position","FLAT")
        c = "green" if pos=="LONG" else ("red" if pos=="SHORT" else "dim")
        mid = d.get("mid","-")
        entry = d.get("entry","-")
        roe = d.get("roe","-")
        tp = d.get("tp","-")
        sl = d.get("sl","-")
        return f"{self.fmt('Position:', pos, c)}  {self.fmt('Mid:', mid,'white')}  {self.fmt('Entry:', entry,'white')}  {self.fmt('ROE:', roe, 'cyan')}  {self.fmt('TP:', tp,'green')}  {self.fmt('SL:', sl,'red')}"
    def rule(self):
        return f"{FG['dim']}{'─'*72}{RST}"
    def close(self):
        sys.stdout.write(f"\n{CSI}?25h{RST}")
        sys.stdout.flush()

def ts():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

def post_json(url: str, body: Dict, timeout: int = 15) -> Dict:
    r = requests.post(url, headers={"Content-Type": "application/json"}, data=json.dumps(body), timeout=timeout)
    try:
        data = r.json()
    except Exception:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text}")
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {data}")
    return data

def info_meta() -> Dict:
    return post_json(INFO_URL, {"type": "meta"})

def info_all_mids() -> Dict:
    return post_json(INFO_URL, {"type": "allMids"})

def find_asset_index(symbol: str) -> Tuple[int, int, int]:
    meta = info_meta()
    for idx, a in enumerate(meta.get("universe", [])):
        if a.get("name", "").upper() == symbol:
            return idx, int(a.get("pxDecimals", 1)), int(a.get("szDecimals", 4))
    names = ", ".join(a.get("name") for a in meta.get("universe", [])[:30])
    raise ValueError(f"Symbol not found: {symbol}. Available: {names}")

def get_mid(symbol: str, aid: int) -> Decimal:
    mids = info_all_mids()
    if isinstance(mids, dict):
        v = mids.get(symbol) or mids.get(str(aid)) or mids.get("BTC")
        if v is None:
            raise RuntimeError(f"allMids missing {symbol}/{aid}: {mids}")
        return Decimal(str(v))
    raise RuntimeError(f"Unexpected allMids shape: {type(mids)} -> {mids}")

def fmt_size(x: Decimal, sz_dec: int) -> str:
    getcontext().prec = 50
    q = Decimal(1) / (Decimal(10) ** sz_dec)
    s = x.quantize(q, rounding=ROUND_DOWN).normalize()
    return format(s, 'f')

def count_sigfigs(s: str) -> int:
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    t = s.lstrip('0')
    if t.startswith('.'):
        t = t[1:].lstrip('0')
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
            last_err = e
            continue
    raise TypeError(f"construct_l1_action signature mismatch: {last_err}")

def now_ms() -> int:
    try:
        return hlh.get_timestamp_ms()
    except Exception:
        return int(time.time() * 1000)

def sign_and_send(action: Dict) -> Dict:
    if INCLUDE_BUILDER:
        action.setdefault("grouping", "na")
        action.setdefault("builder", {"b": BUILDER_ADDR, "f": BUILDER_FEE_TENTH_BPS})
    nonce = now_ms()
    domain, types, message = build_l1_typed(action, nonce)
    signature = hlh.sign_typed_data(PRIVATE_KEY, domain, types, message)
    return post_json(EXCHANGE_URL, {"action": action, "nonce": nonce, "signature": signature})

def limit_order(aid: int, is_buy: bool, px_str: str, sz_str: str, tif="Gtc", reduce_only=False) -> Dict:
    order = {
        "a": aid,
        "b": bool(is_buy),
        "p": str(px_str),
        "s": str(sz_str),
        "r": bool(reduce_only),
        "t": {"limit": {"tif": tif}},
    }
    if CLIENT_ID:
        order["c"] = CLIENT_ID
    return order

def wrap_action(orders: list) -> Dict:
    return {"type": "order", "orders": orders}

def limit_aggressive_px_for_sell(mid: Decimal) -> Decimal:
    return mid * (Decimal("1") - EXIT_CROSS_PCT)

def limit_aggressive_px_for_buy(mid: Decimal) -> Decimal:
    return mid * (Decimal("1") + ENTRY_SLIPPAGE_PCT)

def price_targets_from_roe(entry_px: Decimal) -> Tuple[Decimal, Decimal]:
    tp_ratio = TP_ROE_PCT / (Decimal("100") * LEVERAGE)
    sl_ratio = SL_ROE_PCT / (Decimal("100") * LEVERAGE)
    tp_px = entry_px * (Decimal("1") + tp_ratio)
    sl_px = entry_px * (Decimal("1") - sl_ratio)
    return tp_px, sl_px

def run_bot():
    aid, px_dec, sz_dec = find_asset_index(SYMBOL)
    size_wire = fmt_size(SIZE, sz_dec)
    panel = Panel()
    in_position = False
    entry_px: Optional[Decimal] = None
    tp_px: Optional[Decimal] = None
    sl_px: Optional[Decimal] = None
    base = {
        "is_mainnet": IS_MAINNET,
        "symbol": SYMBOL,
        "aid": str(aid),
        "size": str(size_wire),
        "tif": f"{TIF}/{EXIT_TIF}",
        "lev": f"{LEVERAGE}x",
        "targets": f"TP={TP_ROE_PCT}% SL={SL_ROE_PCT}%",
        "poll": f"{POLL_INTERVAL_SEC}s",
    }
    panel.draw({**base, "position":"FLAT","mid":"-","entry":"-","roe":"-","tp":"-","sl":"-","event":"ready"})
    try:
        while True:
            try:
                mid = get_mid(SYMBOL, aid)
                if not in_position:
                    desired_px = limit_aggressive_px_for_buy(mid)
                    px_str = fmt_price(desired_px, px_dec)
                    buy_action = wrap_action([limit_order(aid, True, px_str, size_wire, tif=TIF, reduce_only=False)])
                    _ = sign_and_send(buy_action)
                    entry_px = mid
                    tp_px, sl_px = price_targets_from_roe(entry_px)
                    in_position = True
                    panel.draw({**base,"position":"LONG","mid":f"{mid}","entry":f"{entry_px}","roe":"0.00%","tp":f"{tp_px}","sl":f"{sl_px}","event":f"ENTER LONG px={px_str}"})
                else:
                    assert entry_px is not None and tp_px is not None and sl_px is not None
                    if mid >= tp_px:
                        exit_px = limit_aggressive_px_for_sell(mid)
                        px_str = fmt_price(exit_px, px_dec)
                        sell_action = wrap_action([limit_order(aid, False, px_str, size_wire, tif=EXIT_TIF, reduce_only=True)])
                        _ = sign_and_send(sell_action)
                        in_position = False
                        entry_px = tp_px = sl_px = None
                        panel.draw({**base,"position":"FLAT","mid":f"{mid}","entry":"-","roe":"-","tp":"-","sl":"-","event":f"TAKE PROFIT px={px_str}"})
                        time.sleep(1.0)
                        continue
                    if mid <= sl_px:
                        exit_px = limit_aggressive_px_for_sell(mid)
                        px_str = fmt_price(exit_px, px_dec)
                        sell_action = wrap_action([limit_order(aid, False, px_str, size_wire, tif=EXIT_TIF, reduce_only=True)])
                        _ = sign_and_send(sell_action)
                        in_position = False
                        entry_px = tp_px = sl_px = None
                        panel.draw({**base,"position":"FLAT","mid":f"{mid}","entry":"-","roe":"-","tp":"-","sl":"-","event":f"STOP LOSS px={px_str}"})
                        time.sleep(1.0)
                        continue
                    roe_now = (mid - entry_px) / entry_px * LEVERAGE * Decimal("100")
                    panel.draw({**base,"position":"LONG","mid":f"{mid}","entry":f"{entry_px}","roe":f"{roe_now:.2f}%","tp":f"{tp_px}","sl":f"{sl_px}","event":"HOLD"})
                time.sleep(POLL_INTERVAL_SEC)
            except Exception as e:
                panel.draw({**base,"position":"ERR","mid":"-","entry":"-","roe":"-","tp":"-","sl":"-","event":f"ERROR {repr(e)}"})
                time.sleep(2.0)
    except KeyboardInterrupt:
        panel.draw({**base,"position":"EXIT","mid":"-","entry":"-","roe":"-","tp":"-","sl":"-","event":"USER EXIT"})
    finally:
        panel.close()

if __name__ == "__main__":
    run_bot()