import re

from address_validation import is_msf_solana_address
from maker_sources import build_pair_makers_text
from pair_sources import build_pair_resolve_text
from utils import compact


PAIR_RECOMMENDATION_RE = re.compile(r"Use this address for /makertrades:\s*(?P<pair>\S+)")


def extract_recommended_pair(pair_resolve_text: str):
    match = PAIR_RECOMMENDATION_RE.search(pair_resolve_text or "")
    if not match:
        return None

    pair = match.group("pair").strip()
    if not is_msf_solana_address(pair):
        return None

    return pair


def extract_line(text: str, prefix: str):
    for line in (text or "").splitlines():
        if line.startswith(prefix):
            return line
    return None


def build_msf_signal_analysis_text(address: str):
    pair_resolve_text = build_pair_resolve_text(address)
    pair = extract_recommended_pair(pair_resolve_text)

    if not pair:
        return pair_resolve_text

    pair_makers_text = build_pair_makers_text(pair, mode="normal", show_full=False)
    unique_makers = extract_line(pair_makers_text, "Unique makers:")
    raw_scanned = extract_line(pair_makers_text, "Raw pair trades scanned:")

    summary_lines = [
        "MSF Signal Analysis",
        f"Input: {compact(address)}",
        f"Resolved best pair: {pair}",
        "Pairmakers mode: normal",
    ]

    if unique_makers:
        summary_lines.append(unique_makers)
    if raw_scanned:
        summary_lines.append(raw_scanned)

    summary_lines.extend(
        [
            "Notes: no PnL calculated; no trading advice.",
            "",
            pair_resolve_text,
            "",
            "---",
            "",
            pair_makers_text,
        ]
    )

    return "\n".join(summary_lines)
