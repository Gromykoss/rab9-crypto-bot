import requests

from config import DEXSCREENER_BASE_URL
from utils import safe_float


def safe_get(url: str, headers=None, timeout=15):
    try:
        response = requests.get(url, headers=headers or {}, timeout=timeout)
        return {
            "ok": response.ok,
            "status_code": response.status_code,
            "data": response.json() if response.text else None,
            "text": response.text[:500] if response.text else "",
        }
    except Exception as error:
        return {
            "ok": False,
            "status_code": None,
            "data": None,
            "text": str(error),
        }


def get_dex_latest_profiles():
    url = f"{DEXSCREENER_BASE_URL}/token-profiles/latest/v1"
    return safe_get(url)


def get_dex_token_pairs(chain_id: str, token_address: str):
    url = f"{DEXSCREENER_BASE_URL}/token-pairs/v1/{chain_id}/{token_address}"
    return safe_get(url)


def pick_best_pair(pairs):
    if not isinstance(pairs, list) or not pairs:
        return None

    def score(pair):
        liquidity = pair.get("liquidity") or {}
        volume = pair.get("volume") or {}
        return safe_float(liquidity.get("usd")), safe_float(volume.get("h24"))

    return sorted(pairs, key=score, reverse=True)[0]
