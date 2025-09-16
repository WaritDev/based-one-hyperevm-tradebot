import os
from dataclasses import dataclass
from decimal import Decimal, getcontext
from dotenv import load_dotenv

load_dotenv()
getcontext().prec = 50

@dataclass
class Settings:
    # Core
    PRIVATE_KEY: str
    IS_MAINNET: bool
    BASE_URL: str
    SYMBOL: str
    SIZE: Decimal
    PRICE: Decimal | None
    TIF: str
    POST_ONLY: bool
    RETRIES: int
    # Builder
    INCLUDE_BUILDER: bool
    BUILDER_ADDR: str
    BUILDER_FEE_TENTH_BPS: int
    # Fallbacks
    PX_DEC: int
    SZ_DEC: int
    TICK_FALLBACK: Decimal
    LOTSZ_FALLBACK: Decimal
    # Client
    CLIENT_ID: str | None
    # Scheduling
    ORDERS_PER_MINUTE: int
    BUY_PER_MIN: int
    SELL_PER_MIN: int
    ORDER_TTL_SEC: int
    # Range
    RANGE_LOWER: Decimal | None
    RANGE_UPPER: Decimal | None
    RANGE_PCT: Decimal | None
    # User (for close pos)
    USER_ADDR: str | None
    # Auth
    AUTH_API_URL: str | None
    AUTH_API_TOKEN: str | None
    PASSWORD: str | None
    # Bias / side control
    START_SIDE: str # "sell" | "buy"
    IMBALANCE_SELL_BOOST: int

def _to_bool(v: str | None, default: bool) -> bool:
    if v is None: return default
    return v.strip().lower() == "true"

def _to_decimal(s: str | None, default: str | None = None) -> Decimal | None:
    from decimal import Decimal, InvalidOperation
    if s is None:
        return Decimal(default) if default is not None else None
    s = s.strip()
    if s.lower() in ("", "nan", "none", "null"):
        return Decimal(default) if default is not None else None
    try:
        return Decimal(s)
    except InvalidOperation as e:
        raise SystemExit(f"Bad decimal for env '{s}': {e}")

def load_settings() -> Settings:
    private_key = os.getenv("PRIVATE_KEY")
    if not private_key:
        raise SystemExit("PRIVATE_KEY not set in .env")

    is_mainnet = _to_bool(os.getenv("IS_MAINNET"), True)
    base_url = os.getenv("BASE_URL") or ("https://api.hyperliquid.xyz" if is_mainnet else "https://api.hyperliquid-testnet.xyz")

    symbol = (os.getenv("SPOT_SYMBOL") or os.getenv("SYMBOL") or "@223").upper()
    size = _to_decimal(os.getenv("SIZE") or "100")
    price = _to_decimal(os.getenv("PRICE"))
    tif = os.getenv("TIF") or "Gtc"
    post_only = _to_bool(os.getenv("POST_ONLY"), True)
    retries = int(os.getenv("RETRIES") or 5)

    orders_per_min = int(os.getenv("ORDERS_PER_MINUTE") or 10)
    buy_per_min    = int(os.getenv("BUY_PER_MIN") or 5)
    sell_per_min   = int(os.getenv("SELL_PER_MIN") or 5)
    order_ttl_sec  = int(os.getenv("ORDER_TTL_SEC") or 20)

    include_b   = _to_bool(os.getenv("INCLUDE_BUILDER"), True)
    builder_addr= (os.getenv("BUILDER_ADDR") or "0x1924b8561eef20e70ede628a296175d358be80e5").lower()
    builder_fee = int(os.getenv("BUILDER_FEE_TENTH_BPS") or 100)

    px_fallback = int(os.getenv("PX_DEC", "6"))
    sz_fallback = int(os.getenv("SZ_DEC", "0"))
    tick_fb     = _to_decimal(os.getenv("TICK_FALLBACK"), "0.000001")
    lotsz_fb    = _to_decimal(os.getenv("LOTSZ_FALLBACK"), "1")

    client_id = os.getenv("CLIENT_ID")
    if client_id:
        body = client_id.lower().removeprefix("0x")
        if len(body) != 32 or any(c not in "0123456789abcdef" for c in body):
            raise SystemExit("CLIENT_ID must be 0x + 32 hex chars (16 bytes)")

    rlower = _to_decimal(os.getenv("RANGE_LOWER"))
    rupper = _to_decimal(os.getenv("RANGE_UPPER"))
    rpct   = _to_decimal(os.getenv("RANGE_PCT"))

    user_addr = os.getenv("USER_ADDR") or os.getenv("USER_ADDRESS")

    auth_api_url   = os.getenv("AUTH_API_URL")
    auth_api_token = os.getenv("AUTH_API_TOKEN")
    password       = os.getenv("PASSWORD")

    start_side = (os.getenv("START_SIDE") or "sell").strip().lower()
    if start_side not in ("sell", "buy"):
        start_side = "sell"
    imbalance_sell_boost = int(os.getenv("IMBALANCE_SELL_BOOST") or 2)

    return Settings(
        PRIVATE_KEY=private_key,
        IS_MAINNET=is_mainnet,
        BASE_URL=base_url,
        SYMBOL=symbol,
        SIZE=size,
        PRICE=price,
        TIF=tif,
        POST_ONLY=post_only,
        RETRIES=retries,
        INCLUDE_BUILDER=include_b,
        BUILDER_ADDR=builder_addr,
        BUILDER_FEE_TENTH_BPS=builder_fee,
        PX_DEC=px_fallback,
        SZ_DEC=sz_fallback,
        TICK_FALLBACK=tick_fb,
        LOTSZ_FALLBACK=lotsz_fb,
        CLIENT_ID=client_id,
        ORDERS_PER_MINUTE=orders_per_min,
        BUY_PER_MIN=buy_per_min,
        SELL_PER_MIN=sell_per_min,
        ORDER_TTL_SEC=order_ttl_sec,
        RANGE_LOWER=rlower,
        RANGE_UPPER=rupper,
        RANGE_PCT=rpct,
        USER_ADDR=user_addr,
        AUTH_API_URL=auth_api_url,
        AUTH_API_TOKEN=auth_api_token,
        PASSWORD=password,
        START_SIDE=start_side,
        IMBALANCE_SELL_BOOST=imbalance_sell_boost,
    )