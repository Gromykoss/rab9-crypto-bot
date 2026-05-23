import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

load_dotenv(os.path.join(BASE_DIR, ".env"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_GROUP_ID = os.getenv("TELEGRAM_GROUP_ID")

XAI_API_KEY = os.getenv("XAI_API_KEY")
ARKHAM_API_KEY = os.getenv("ARKHAM_API_KEY")
BIRDEYE_API_KEY = os.getenv("BIRDEYE_API_KEY")
SOLSCAN_API_KEY = os.getenv("SOLSCAN_API_KEY")

DEXSCREENER_BASE_URL = os.getenv("DEXSCREENER_BASE_URL", "https://api.dexscreener.com")
XAI_BASE_URL = os.getenv("XAI_BASE_URL", "https://api.x.ai")
RAB9_HTTP_HOST = os.getenv("RAB9_HTTP_HOST", "127.0.0.1")
RAB9_HTTP_PORT = int(os.getenv("RAB9_HTTP_PORT", "8089"))
RAB9_HTTP_SECRET = os.getenv("RAB9_HTTP_SECRET")

WATCHLIST_PATH = os.path.join(BASE_DIR, "watchlist.json")
ALERT_STATE_PATH = os.path.join(BASE_DIR, "alert_state.json")
WALLET_WATCHLIST_PATH = os.path.join(BASE_DIR, "wallet_watchlist.json")

ALERT_INTERVAL_SECONDS = int(os.getenv("ALERT_INTERVAL_SECONDS", "3600"))
ALERT_COOLDOWN_SECONDS = int(os.getenv("ALERT_COOLDOWN_SECONDS", "3600"))
LEGACY_WATCHLIST_ALERTS_ENABLED = os.getenv("LEGACY_WATCHLIST_ALERTS_ENABLED", "false").lower() in {
    "1",
    "true",
    "yes",
    "on",
}


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
