import re


MSF_SOLANA_ADDRESS_RE = re.compile(r"^[1-9A-HJ-NP-Za-z]{32,44}$")


def is_msf_solana_address(address: str) -> bool:
    return bool(MSF_SOLANA_ADDRESS_RE.match((address or "").strip()))
