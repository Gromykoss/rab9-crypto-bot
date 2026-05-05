import requests

from config import ARKHAM_API_KEY


ARKHAM_BASE_URL = "https://api.arkm.com"


def arkham_headers():
    return {
        "API-Key": ARKHAM_API_KEY or "",
        "Accept": "application/json",
    }


def arkham_get(path: str, timeout=20):
    if not ARKHAM_API_KEY:
        return {
            "ok": False,
            "status_code": None,
            "data": None,
            "text": "ARKHAM_API_KEY missing",
            "usage": {},
        }

    url = f"{ARKHAM_BASE_URL}{path}"

    try:
        response = requests.get(url, headers=arkham_headers(), timeout=timeout)

        usage = {
            "limit": response.headers.get("x-intel-datapoints-limit"),
            "remaining": response.headers.get("x-intel-datapoints-remaining"),
            "used": response.headers.get("x-intel-datapoints-usage"),
        }

        return {
            "ok": response.ok,
            "status_code": response.status_code,
            "data": response.json() if response.text else None,
            "text": response.text[:800] if response.text else "",
            "usage": usage,
        }

    except Exception as error:
        return {
            "ok": False,
            "status_code": None,
            "data": None,
            "text": str(error),
            "usage": {},
        }


def get_chains():
    return arkham_get("/chains")


def get_token_intelligence(chain: str, address: str):
    return arkham_get(f"/intelligence/token/{chain}/{address}")


def get_address_intelligence_all(address: str):
    return arkham_get(f"/intelligence/address/{address}/all")


def format_usage(usage: dict):
    if not usage:
        return "Usage: n/a"

    limit = usage.get("limit") or "n/a"
    remaining = usage.get("remaining") or "n/a"
    used = usage.get("used") or "n/a"

    return f"Usage: used {used}, remaining {remaining}, limit {limit}"


def build_arkham_status_text():
    chains = get_chains()

    if not chains["ok"]:
        return (
            "🕵️ Arkham Status\n\n"
            f"ARKHAM_API_KEY: {'loaded' if ARKHAM_API_KEY else 'missing'}\n"
            f"Status: error {chains['status_code']}\n"
            f"Response: {chains['text'][:500]}"
        )

    data = chains["data"]
    chains_text = ", ".join(data[:12]) if isinstance(data, list) else str(data)[:300]

    return (
        "🕵️ Arkham Status\n\n"
        f"ARKHAM_API_KEY: {'loaded' if ARKHAM_API_KEY else 'missing'}\n"
        f"Status: online ({chains['status_code']})\n"
        f"Chains: {chains_text}\n"
        f"{format_usage(chains.get('usage') or {})}"
    )


def build_ark_token_text(chain: str, address: str):
    token = get_token_intelligence(chain, address)
    address_intel = get_address_intelligence_all(address)

    lines = [
        "🕵️ Arkham Token Intel",
        "",
        f"Chain: {chain}",
        f"Address: {address}",
        "",
    ]

    if token["ok"]:
        data = token["data"] or {}
        identifier = data.get("identifier") or {}

        lines.extend(
            [
                "Token Intelligence:",
                f"Name: {data.get('name', 'n/a')}",
                f"Symbol: {data.get('symbol', 'n/a')}",
                f"Pricing ID: {identifier.get('pricingID', 'n/a')}",
                f"Identifier Chain: {identifier.get('chain', 'n/a')}",
                "",
                format_usage(token.get("usage") or {}),
                "",
            ]
        )
    else:
        lines.extend(
            [
                "Token Intelligence:",
                f"Status: error {token['status_code']}",
                f"Response: {token['text'][:400]}",
                "",
            ]
        )

    if address_intel["ok"]:
        data = address_intel["data"] or {}
        chain_data = data.get(chain) or {}

        label = chain_data.get("arkhamLabel") or {}
        entity = chain_data.get("arkhamEntity") or {}

        lines.extend(
            [
                "Address Intelligence:",
                f"Arkham Label: {label.get('name', 'n/a')}",
                f"Entity: {entity.get('name', 'n/a')}",
                f"Is User Address: {chain_data.get('isUserAddress', 'n/a')}",
                f"Program: {chain_data.get('program', 'n/a')}",
                "",
                format_usage(address_intel.get("usage") or {}),
            ]
        )
    else:
        lines.extend(
            [
                "Address Intelligence:",
                f"Status: error {address_intel['status_code']}",
                f"Response: {address_intel['text'][:400]}",
            ]
        )

    return "\n".join(lines)


def build_wallet_text(address: str):
    result = get_address_intelligence_all(address)

    if not result["ok"]:
        return (
            "👛 Arkham Wallet / Address Intel\n\n"
            f"Address: {address}\n"
            f"Status: error {result['status_code']}\n"
            f"Response: {result['text'][:500]}"
        )

    data = result["data"] or {}

    if not isinstance(data, dict) or not data:
        return (
            "👛 Arkham Wallet / Address Intel\n\n"
            f"Address: {address}\n"
            "No Arkham intelligence found."
        )

    lines = [
        "👛 Arkham Wallet / Address Intel",
        "",
        f"Address: {address}",
        "",
    ]

    for chain, chain_data in data.items():
        if not isinstance(chain_data, dict):
            continue

        label = chain_data.get("arkhamLabel") or {}
        entity = chain_data.get("arkhamEntity") or {}

        lines.extend(
            [
                f"Chain: {chain}",
                f"Arkham Label: {label.get('name', 'n/a')}",
                f"Entity: {entity.get('name', 'n/a')}",
                f"Is User Address: {chain_data.get('isUserAddress', 'n/a')}",
                f"Program: {chain_data.get('program', 'n/a')}",
                "",
            ]
        )

    lines.append(format_usage(result.get("usage") or {}))

    lines.extend(
        [
            "",
            "Notes:",
            "- Это базовая Arkham-разметка адреса.",
            "- Если Entity/Label пустые, Arkham не знает владельца адреса или не отдаёт его по текущему доступу.",
            "- Для smart-money логики позже добавим watchwallet и checkwallets.",
        ]
    )

    return "\n".join(lines)
