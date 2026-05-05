import os
from dotenv import load_dotenv

load_dotenv("/root/rab9/.env")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_GROUP_ID = os.getenv("TELEGRAM_GROUP_ID")

XAI_API_KEY = os.getenv("XAI_API_KEY")
ARKHAM_API_KEY = os.getenv("ARKHAM_API_KEY")

DEXSCREENER_BASE_URL = os.getenv("DEXSCREENER_BASE_URL", "https://api.dexscreener.com")
XAI_BASE_URL = os.getenv("XAI_BASE_URL", "https://api.x.ai")

WATCHLIST_PATH = "/root/rab9/watchlist.json"
ALERT_STATE_PATH = "/root/rab9/alert_state.json"

ALERT_INTERVAL_SECONDS = int(os.getenv("ALERT_INTERVAL_SECONDS", "3600"))
ALERT_COOLDOWN_SECONDS = int(os.getenv("ALERT_COOLDOWN_SECONDS", "3600"))


SCAN_MICRO = {
    "name": "Micro",
    "limit_profiles": 50,
    "min_mc": 20_000,
    "max_mc": 100_000,
    "min_liquidity": 5_000,
    "min_volume24h": 20_000,
    "max_sell_buy_24h": 2.5,
    "min_score": 30,
    "max_age_hours": 24,
}

SCAN_DEGEN = {
    "name": "Degen",
    "limit_profiles": 40,
    "min_mc": 100_000,
    "max_mc": 2_000_000,
    "min_liquidity": 20_000,
    "min_volume24h": 50_000,
    "max_sell_buy_24h": 2.0,
    "min_score": 35,
    "max_age_hours": 48,
}

SCAN_NORMAL = {
    "name": "Normal",
    "limit_profiles": 35,
    "min_mc": 2_000_000,
    "max_mc": 15_000_000,
    "min_liquidity": 50_000,
    "min_volume24h": 100_000,
    "max_sell_buy_24h": 1.6,
    "min_score": 40,
}

SCAN_HOT = {
    "name": "Hot",
    "limit_profiles": 60,
    "min_mc": 20_000,
    "max_mc": 15_000_000,
    "min_liquidity": 10_000,
    "min_volume1h": 5_000,
    "min_price_change_1h": 10,
    "max_sell_buy_1h": 1.2,
    "min_score": 40,
}
