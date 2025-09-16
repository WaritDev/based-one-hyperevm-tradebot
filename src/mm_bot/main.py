from .config import load_settings
from .auth import verify_or_exit
from .info import init_info, resolve_asset_fields, clamp_price_to_ref_band
from .exchange import init_exchange, smart_submit
from .strategy import MakerBot

def run_bot():
    cfg = load_settings()
    init_info(cfg)
    init_exchange(cfg)

    verify_or_exit(cfg)

    asset = resolve_asset_fields(cfg)

    if cfg.PRICE is not None:
        px0, _, _ = clamp_price_to_ref_band(asset.index, cfg.PRICE)
        try:
            smart_submit(cfg, asset, is_buy=True,  px=px0, sz=cfg.SIZE,
                        tif=cfg.TIF, post_only=cfg.POST_ONLY, max_retries=cfg.RETRIES)
        except Exception:
            pass
        try:
            smart_submit(cfg, asset, is_buy=False, px=px0, sz=cfg.SIZE,
                        tif=cfg.TIF, post_only=cfg.POST_ONLY, max_retries=cfg.RETRIES)
        except Exception:
            pass

    bot = MakerBot(cfg, asset)
    bot.run()

def main():
    run_bot()

if __name__ == "__main__":
    main()