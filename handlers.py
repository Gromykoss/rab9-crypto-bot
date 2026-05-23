import re
import asyncio
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from address_validation import is_msf_solana_address
from config import TELEGRAM_GROUP_ID, XAI_API_KEY, ARKHAM_API_KEY, LEGACY_WATCHLIST_ALERTS_ENABLED
from utils import utc_now_text, split_text
from dex import get_dex_latest_profiles
from keyboards import main_reply_keyboard, main_inline_keyboard, token_chain_keyboard
from scanner import build_micro_scan_text, build_degen_scan_text, build_normal_scan_text, build_hot_scan_text
from token_intel import build_token_intel_text, ask_grok
from watchlist import (
    add_to_watchlist,
    remove_from_watchlist,
    format_watchlist_text,
    build_watch_check_text,
    refresh_watchlist_snapshots,
    load_watchlist,
)
from alerts import build_watch_alerts_text
from arkham import (
    build_arkham_status_text,
    build_ark_token_text,
    build_wallet_text,
    build_wallet_flow_text,
    build_token_flow_text,
    build_wallet_tx_text,
    build_wallet_trade_text,
)
from price_sources import build_price_source_text
from swap_sources import build_wallet_swaps_text
from maker_sources import build_maker_find_text, build_maker_trades_text, build_pair_makers_text
from pair_sources import build_pair_resolve_text
from wallet_profile import build_wallet_profile_text
from wallet_watch import (
    add_wallet_to_watchlist,
    remove_wallet_from_watchlist,
    format_walletlist_text,
    build_checkwallets_text,
)

logger = logging.getLogger("rab9_crypto_intel_bot")

SOLANA_RE = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")
EVM_RE = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
RAB9_SIGNAL_RE = re.compile(
    r"\bRAB9_SIGNAL\s+solana\s+(?P<address>[1-9A-HJ-NP-Za-km-z]{32,44})\b",
    re.IGNORECASE,
)
ALLOWED_FLOW_PERIODS = {"1h", "6h", "12h", "24h", "7d", "30d"}
FLOW_PERIOD_HINT = "Допустимый период: 1h, 6h, 12h, 24h, 7d, 30d"


def is_allowed_chat_id(chat_id) -> bool:
    return str(chat_id) == str(TELEGRAM_GROUP_ID)


async def deny_if_wrong_group(update: Update) -> bool:
    if update.message and update.effective_chat:
        if not is_allowed_chat_id(update.effective_chat.id):
            await update.message.reply_text("⛔ Этот бот работает только в разрешённой группе.")
            return True

    if update.callback_query and update.callback_query.message:
        chat_id = update.callback_query.message.chat_id

        if not is_allowed_chat_id(chat_id):
            await update.callback_query.answer("⛔ Не разрешённая группа.", show_alert=True)
            return True

    return False


def build_status_text() -> str:
    checks = [
        "✅ Telegram Bot: online",
        f"✅ Group Lock: {TELEGRAM_GROUP_ID}",
        "✅ XAI/Grok key: loaded" if XAI_API_KEY else "❌ XAI/Grok key: missing",
        "✅ Arkham key: loaded" if ARKHAM_API_KEY else "❌ Arkham key: missing",
    ]

    dex = get_dex_latest_profiles()

    if dex["ok"]:
        checks.append(f"✅ Dexscreener: online ({dex['status_code']})")
    else:
        checks.append(f"❌ Dexscreener: error ({dex['status_code']}) {dex['text'][:120]}")

    checks.append(f"📋 Watchlist: {len(load_watchlist())} token(s)")
    checks.append(f"🕒 Time: {utc_now_text()}")

    return "\n".join(checks)


async def reply_long(update: Update, text: str, reply_markup=None):
    chunks = split_text(text)

    for idx, chunk in enumerate(chunks):
        await update.message.reply_text(
            chunk,
            reply_markup=reply_markup if idx == len(chunks) - 1 else None,
            disable_web_page_preview=True,
        )


def compact_log_value(value, left=6, right=4) -> str:
    if not value:
        return "n/a"

    text = str(value)
    if len(text) <= left + right + 3:
        return text

    return f"{text[:left]}...{text[-right:]}"


def telegram_safe_plain_text(text) -> str:
    text = "" if text is None else str(text)
    return "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)


async def reply_walletswaps_report(update: Update, text: str, reply_markup=None):
    safe_text = telegram_safe_plain_text(text)
    chunks = split_text(safe_text)

    logger.info(
        "walletswaps report generated: length=%s chunks=%s first120=%r",
        len(safe_text),
        len(chunks),
        safe_text[:120],
    )

    try:
        for idx, chunk in enumerate(chunks):
            logger.info(
                "walletswaps sending chunk: index=%s/%s length=%s first120=%r",
                idx + 1,
                len(chunks),
                len(chunk),
                chunk[:120],
            )
            await update.message.reply_text(
                chunk,
                reply_markup=reply_markup if idx == len(chunks) - 1 else None,
                disable_web_page_preview=True,
            )
    except Exception:
        logger.exception(
            "walletswaps reply_text failed: report_len=%s chunks=%s first500=%r last500=%r",
            len(safe_text),
            len(chunks),
            safe_text[:500],
            safe_text[-500:],
        )
        try:
            await update.message.reply_text(
                "Wallet swaps report send failed. Check bot logs for details.",
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
        except Exception:
            logger.exception("walletswaps fallback reply failed")


async def send_long_to_chat(context: ContextTypes.DEFAULT_TYPE, chat_id, text: str):
    for chunk in split_text(text):
        await context.bot.send_message(
            chat_id=chat_id,
            text=chunk,
            disable_web_page_preview=True,
        )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    await update.message.reply_text(
        "RAB9 Crypto Intel Bot online.\n\n"
        "Сетка сканеров:\n"
        "/micro — MC $20K–$100K\n"
        "/degen — MC $100K–$2M\n"
        "/scan — MC $2M–$15M\n\n"
        "Watchlist:\n"
        "/watch solana ADDRESS заметка\n"
        "/watchlist\n"
        "/checkwatch\n"
        "/refreshwatch\n"
        "/unwatch ADDRESS",
        reply_markup=main_reply_keyboard(),
    )


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"MENU COMMAND FROM CHAT: {update.effective_chat.id if update.effective_chat else 'no_chat'}")

    if await deny_if_wrong_group(update):
        return

    await update.message.reply_text(
        "RAB9 меню. Выбирай действие:",
        reply_markup=main_inline_keyboard(),
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    await update.message.reply_text("Проверяю системы...")
    text = await asyncio.to_thread(build_status_text)
    await reply_long(update, text, main_reply_keyboard())


async def arkhamstatus_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    await update.message.reply_text("Проверяю Arkham API...")
    text = await asyncio.to_thread(build_arkham_status_text)
    await reply_long(update, text, main_reply_keyboard())


async def arktoken_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    if len(context.args) < 1:
        await update.message.reply_text(
            "Формат:\n"
            "/arktoken ADDRESS\n"
            "или:\n"
            "/arktoken solana ADDRESS",
            reply_markup=main_reply_keyboard(),
        )
        return

    if len(context.args) == 1:
        chain = "solana"
        address = context.args[0].strip()
    else:
        chain = context.args[0].strip().lower()
        address = context.args[1].strip()

    await update.message.reply_text(f"Проверяю Arkham token intel: {chain} / {address}")
    text = await asyncio.to_thread(build_ark_token_text, chain, address)
    await reply_long(update, text, main_reply_keyboard())


async def wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    if len(context.args) < 1:
        await update.message.reply_text(
            "Формат:\n/wallet ADDRESS",
            reply_markup=main_reply_keyboard(),
        )
        return

    address = context.args[0].strip()

    await update.message.reply_text(f"Проверяю Arkham wallet/address intel: {address}")
    text = await asyncio.to_thread(build_wallet_text, address)
    await reply_long(update, text, main_reply_keyboard())


async def walletflow_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    if len(context.args) < 1:
        await update.message.reply_text(
            "Формат:\n/walletflow ADDRESS",
            reply_markup=main_reply_keyboard(),
        )
        return

    address = context.args[0].strip()
    time_last = context.args[1].strip() if len(context.args) > 1 else "24h"

    if time_last not in ALLOWED_FLOW_PERIODS:
        await update.message.reply_text(FLOW_PERIOD_HINT, reply_markup=main_reply_keyboard())
        return

    await update.message.reply_text(f"Проверяю Arkham wallet flow: {address} / {time_last}")
    text = await asyncio.to_thread(build_wallet_flow_text, address, time_last)
    await reply_long(update, text, main_reply_keyboard())


async def tokenflow_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Формат:\n/tokenflow chain ADDRESS",
            reply_markup=main_reply_keyboard(),
        )
        return

    chain = context.args[0].strip().lower()
    address = context.args[1].strip()
    time_last = context.args[2].strip() if len(context.args) > 2 else "24h"

    if time_last not in ALLOWED_FLOW_PERIODS:
        await update.message.reply_text(FLOW_PERIOD_HINT, reply_markup=main_reply_keyboard())
        return

    await update.message.reply_text(f"Проверяю Arkham token top flow: {chain} / {address} / {time_last}")
    text = await asyncio.to_thread(build_token_flow_text, chain, address, time_last)
    await reply_long(update, text, main_reply_keyboard())


async def wallettx_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Формат:\n/wallettx WALLET TOKEN\n/wallettx WALLET TOKEN 25",
            reply_markup=main_reply_keyboard(),
        )
        return

    wallet = context.args[0].strip()
    token = context.args[1].strip()
    limit = 25

    if len(context.args) > 2:
        try:
            limit = int(context.args[2])
        except ValueError:
            limit = 25

    limit = min(max(limit, 1), 50)

    await update.message.reply_text(f"Проверяю Arkham transfers: {wallet} / {token} / limit {limit}")
    text = await asyncio.to_thread(build_wallet_tx_text, wallet, token, limit)
    await reply_long(update, text, main_reply_keyboard())


async def wallettrade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Формат:\n/wallettrade WALLET TOKEN",
            reply_markup=main_reply_keyboard(),
        )
        return

    wallet = context.args[0].strip()
    token = context.args[1].strip()

    await update.message.reply_text(f"Анализирую wallet trade pattern: {wallet} / {token}")
    text = await asyncio.to_thread(build_wallet_trade_text, wallet, token)
    await reply_long(update, text, main_reply_keyboard())


async def pricesource_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Формат:\n/pricesource TOKEN 2026-05-07T18:45:29Z",
            reply_markup=main_reply_keyboard(),
        )
        return

    token = context.args[0].strip()
    timestamp = context.args[1].strip()

    await update.message.reply_text(f"Проверяю Birdeye historical price: {token} / {timestamp}")
    text = await asyncio.to_thread(build_price_source_text, token, timestamp)
    await reply_long(update, text, main_reply_keyboard())


async def walletswaps_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    if len(context.args) < 1:
        await update.message.reply_text(
            "Формат:\n/walletswaps WALLET\n/walletswaps WALLET TOKEN\n/walletswaps WALLET TOKEN 50\n/walletswaps WALLET TOKEN 50 deep\n/walletswaps WALLET TOKEN 50 deep10",
            reply_markup=main_reply_keyboard(),
        )
        return

    wallet = context.args[0].strip()
    token = None
    limit = 20
    mode = "normal"

    if len(context.args) > 1:
        if context.args[1].isdigit():
            limit = int(context.args[1])
        else:
            token = context.args[1].strip()

    if len(context.args) > 2:
        if context.args[2].lower() in {"deep", "deep10"}:
            mode = context.args[2].lower()
        else:
            try:
                limit = int(context.args[2])
            except ValueError:
                limit = 20

    if len(context.args) > 3 and context.args[3].lower() in {"deep", "deep10"}:
        mode = context.args[3].lower()

    limit = min(max(limit, 1), 50)

    logger.info(
        "walletswaps parsed args: wallet=%s token=%s limit=%s mode=%s",
        compact_log_value(wallet),
        compact_log_value(token),
        limit,
        mode,
    )

    target = f"{wallet} / {token}" if token else wallet
    await update.message.reply_text(f"Проверяю parsed wallet swaps: {target} / limit {limit} / {mode}")

    try:
        text = await asyncio.to_thread(build_wallet_swaps_text, wallet, token, limit, mode)
    except Exception:
        logger.exception(
            "walletswaps build failed: wallet=%s token=%s limit=%s mode=%s",
            compact_log_value(wallet),
            compact_log_value(token),
            limit,
            mode,
        )
        await update.message.reply_text(
            "Wallet swaps report build failed. Check bot logs for details.",
            reply_markup=main_reply_keyboard(),
        )
        return

    await reply_walletswaps_report(update, text, main_reply_keyboard())


async def makertrades_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Формат:\n/makertrades PAIR MAKER\n/makertrades PAIR MAKER 50\n/makertrades PAIR MAKER 50 deep\n/makertrades PAIR MAKER 50 deep10",
            reply_markup=main_reply_keyboard(),
        )
        return

    pair = context.args[0].strip()
    maker = context.args[1].strip()
    limit = 50
    mode = "normal"

    if len(context.args) > 2:
        if context.args[2].lower() in {"deep", "deep10"}:
            mode = context.args[2].lower()
        else:
            try:
                limit = int(context.args[2])
            except ValueError:
                limit = 50

    if len(context.args) > 3 and context.args[3].lower() in {"deep", "deep10"}:
        mode = context.args[3].lower()

    limit = min(max(limit, 1), 50)

    await update.message.reply_text(f"Проверяю maker trades: {pair} / {maker} / limit {limit} / {mode}")
    text = await asyncio.to_thread(build_maker_trades_text, pair, maker, limit, mode)
    await reply_long(update, text, main_reply_keyboard())


async def makerfind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Формат:\n/makerfind PAIR MAKER\n/makerfind PAIR MAKER deep\n/makerfind PAIR MAKER deep50\n/makerfind PAIR MAKER around TIMESTAMP\n/makerfind PAIR MAKER around TIMESTAMP fallback",
            reply_markup=main_reply_keyboard(),
        )
        return

    pair = context.args[0].strip()
    maker = context.args[1].strip()
    mode = "deep"
    anchor_time = None
    allow_fallback = False

    if len(context.args) > 2 and context.args[2].lower() in {"deep", "deep50"}:
        mode = context.args[2].lower()
    elif len(context.args) > 2 and context.args[2].lower() == "around":
        if len(context.args) < 4:
            await update.message.reply_text(
                "Формат:\n/makerfind PAIR MAKER around TIMESTAMP",
                reply_markup=main_reply_keyboard(),
            )
            return
        mode = "around"
        anchor_time = context.args[3].strip()
        allow_fallback = len(context.args) > 4 and context.args[4].lower() == "fallback"

    await update.message.reply_text(f"Ищу maker глубже: {pair} / {maker} / {mode}")
    text = await asyncio.to_thread(build_maker_find_text, pair, maker, mode, anchor_time, allow_fallback)
    await reply_long(update, text, main_reply_keyboard())


async def pairmakers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    if len(context.args) < 1:
        await update.message.reply_text(
            "Формат:\n/pairmakers PAIR\n/pairmakers PAIR deep\n/pairmakers PAIR deep50\n/pairmakers PAIR deep50 full",
            reply_markup=main_reply_keyboard(),
        )
        return

    pair = context.args[0].strip()
    mode = "deep"
    show_full = False
    if len(context.args) > 1 and context.args[1].lower() in {"deep", "deep50"}:
        mode = context.args[1].lower()
    if any(item.lower() == "full" for item in context.args[1:]):
        show_full = True

    await update.message.reply_text(f"Ищу top makers по pair: {pair} / {mode}")
    text = await asyncio.to_thread(build_pair_makers_text, pair, mode, show_full)
    await reply_long(update, text, main_reply_keyboard())


async def pairresolve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    if len(context.args) < 1:
        await update.message.reply_text(
            "Формат:\n/pairresolve ADDRESS",
            reply_markup=main_reply_keyboard(),
        )
        return

    address = context.args[0].strip()

    await update.message.reply_text(f"Проверяю pair/pool candidates: {address}")
    text = await asyncio.to_thread(build_pair_resolve_text, address)
    await reply_long(update, text, main_reply_keyboard())


async def testsignal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    if len(context.args) < 1:
        await update.message.reply_text("Формат:\n/testsignal ADDRESS", reply_markup=main_reply_keyboard())
        return

    address = context.args[0].strip()

    if not is_msf_solana_address(address):
        await update.message.reply_text("Invalid Solana address.", reply_markup=main_reply_keyboard())
        return

    logger.info("Manual testsignal triggered for %s", address)
    await update.message.reply_text("🔎 RAB9 начал анализ MSF-сигнала...")
    text = await asyncio.to_thread(build_pair_resolve_text, address)
    await reply_long(update, text, main_reply_keyboard())


async def walletprofile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Формат:\n/walletprofile WALLET PAIR:TOKEN PAIR:TOKEN\n/walletprofile WALLET PAIR:TOKEN:TIMESTAMP",
            reply_markup=main_reply_keyboard(),
        )
        return

    wallet = context.args[0].strip()
    cases = [item.strip() for item in context.args[1:] if item.strip()]

    await update.message.reply_text(f"Собираю wallet profile: {wallet} / cases {len(cases)}")
    text = await asyncio.to_thread(build_wallet_profile_text, wallet, cases)
    await reply_long(update, text, main_reply_keyboard())


async def watchwallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    if len(context.args) < 1:
        await update.message.reply_text(
            "Формат:\n/watchwallet ADDRESS заметка",
            reply_markup=main_reply_keyboard(),
        )
        return

    address = context.args[0].strip()
    note = " ".join(context.args[1:]).strip()

    status, item = await asyncio.to_thread(add_wallet_to_watchlist, address, note)
    label = "Добавил" if status == "added" else "Обновил"

    await update.message.reply_text(
        f"👛 {label} wallet в watchlist\n"
        f"Address: {item['address']}\n"
        f"Note: {item.get('note') or 'без заметки'}",
        reply_markup=main_reply_keyboard(),
    )


async def walletlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    text = await asyncio.to_thread(format_walletlist_text)
    await reply_long(update, text, main_reply_keyboard())


async def unwatchwallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Формат:\n/unwatchwallet ADDRESS",
            reply_markup=main_reply_keyboard(),
        )
        return

    address = context.args[0].strip()
    removed = await asyncio.to_thread(remove_wallet_from_watchlist, address)

    if not removed:
        await update.message.reply_text("Не нашёл такой wallet в watchlist.", reply_markup=main_reply_keyboard())
        return

    await update.message.reply_text(f"🗑 Удалил wallet из watchlist: {len(removed)}", reply_markup=main_reply_keyboard())


async def checkwallets_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    await update.message.reply_text("Проверяю wallet watchlist...")
    text = await asyncio.to_thread(build_checkwallets_text)
    await reply_long(update, text, main_reply_keyboard())


async def micro_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    await update.message.reply_text("Запускаю Scan Micro: MC $20K–$100K...")
    text = await asyncio.to_thread(build_micro_scan_text)
    await reply_long(update, text, main_reply_keyboard())


async def degen_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    await update.message.reply_text("Запускаю Scan Degen: MC $100K–$2M...")
    text = await asyncio.to_thread(build_degen_scan_text)
    await reply_long(update, text, main_reply_keyboard())


async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    await update.message.reply_text("Запускаю Scan Normal: MC $2M–$15M...")
    text = await asyncio.to_thread(build_normal_scan_text)
    await reply_long(update, text, main_reply_keyboard())


async def hot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    await update.message.reply_text("Запускаю Hot Scan: ищу резкий volume/price импульс...")
    text = await asyncio.to_thread(build_hot_scan_text)
    await reply_long(update, text, main_reply_keyboard())


async def token_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Формат:\n/token solana ADDRESS\n\nИли просто отправь адрес токена в чат.",
            reply_markup=main_reply_keyboard(),
        )
        return

    chain_id = context.args[0].strip().lower()
    token_address = context.args[1].strip()

    await update.message.reply_text(f"Анализирую токен: {chain_id} / {token_address}\nЭто может занять несколько секунд.")
    text = await asyncio.to_thread(build_token_intel_text, chain_id, token_address)
    await reply_long(update, text, main_reply_keyboard())


async def watch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Формат:\n/watch solana ADDRESS заметка",
            reply_markup=main_reply_keyboard(),
        )
        return

    chain = context.args[0].strip().lower()
    address = context.args[1].strip()
    note = " ".join(context.args[2:]).strip()

    status, item = await asyncio.to_thread(add_to_watchlist, chain, address, note)
    label = "Добавил" if status == "added" else "Обновил"

    await update.message.reply_text(
        f"👁 {label} в watchlist\n"
        f"Chain: {item['chain']}\n"
        f"Address: {item['address']}\n"
        f"Note: {item.get('note') or 'без заметки'}",
        reply_markup=main_reply_keyboard(),
    )


async def watchlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    text = await asyncio.to_thread(format_watchlist_text)
    await reply_long(update, text, main_reply_keyboard())


async def refreshwatch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    await update.message.reply_text("Обновляю snapshots для watchlist...")
    text = await asyncio.to_thread(refresh_watchlist_snapshots)
    await reply_long(update, text, main_reply_keyboard())


async def unwatch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    if not context.args:
        await update.message.reply_text("Формат:\n/unwatch ADDRESS", reply_markup=main_reply_keyboard())
        return

    address = context.args[0].strip()
    removed = await asyncio.to_thread(remove_from_watchlist, address)

    if not removed:
        await update.message.reply_text("Не нашёл такой адрес в watchlist.", reply_markup=main_reply_keyboard())
        return

    await update.message.reply_text(f"🗑 Удалил из watchlist: {len(removed)}", reply_markup=main_reply_keyboard())


async def checkwatch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    await update.message.reply_text("Проверяю watchlist...")
    text = await asyncio.to_thread(build_watch_check_text)
    await reply_long(update, text, main_reply_keyboard())


async def alertsnow_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    if not LEGACY_WATCHLIST_ALERTS_ENABLED:
        await update.message.reply_text(
            "Legacy watchlist alerts are disabled. MSF signals are the active trigger source.",
            reply_markup=main_reply_keyboard(),
        )
        return

    await update.message.reply_text("Проверяю alert triggers по watchlist...")
    text = await asyncio.to_thread(build_watch_alerts_text)

    if not text:
        await update.message.reply_text(
            "Новых alert triggers нет. Состояние watchlist обновлено.",
            reply_markup=main_reply_keyboard(),
        )
        return

    await reply_long(update, text, main_reply_keyboard())


async def grok_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    user_text = " ".join(context.args).strip()

    if not user_text:
        await update.message.reply_text("Формат: /grok проанализируй токен XYZ")
        return

    await update.message.reply_text("Думаю через Grok...")

    prompt = (
        "Проанализируй запрос как crypto intel assistant. "
        "Дай структурный ответ: сигнал, риск, что проверить, что делать дальше.\n\n"
        f"Запрос: {user_text}"
    )

    text = await asyncio.to_thread(ask_grok, prompt)
    await reply_long(update, text, main_reply_keyboard())


async def morning_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    prompt = (
        "Сформируй утренний crypto intel ritual report. "
        "Структура: 1) режим рынка, 2) что мониторить, 3) риски, "
        "4) план на день, 5) что не делать. "
        "Данных рынка сейчас мало, поэтому не выдумывай факты, а дай рабочий чек-лист."
    )

    await update.message.reply_text("Готовлю Morning Intel...")
    text = await asyncio.to_thread(ask_grok, prompt)
    await reply_long(update, f"🌅 Morning Intel\n\n{text}", main_reply_keyboard())


async def evening_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    prompt = (
        "Сформируй вечерний crypto intel ritual report. "
        "Структура: 1) что проверить по watchlist, 2) что закрыть, "
        "3) какие токены удалить из внимания, 4) риски на ночь, "
        "5) план на завтра. Не выдумывай факты."
    )

    await update.message.reply_text("Готовлю Evening Intel...")
    text = await asyncio.to_thread(ask_grok, prompt)
    await reply_long(update, f"🌙 Evening Intel\n\n{text}", main_reply_keyboard())


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if not query or not query.message:
        return

    chat_id = query.message.chat_id

    if not is_allowed_chat_id(chat_id):
        await query.answer("⛔ Не разрешённая группа.", show_alert=True)
        return

    data = query.data or ""

    logger.info(f"BUTTON CALLBACK DATA: {data}")

    await query.answer("Принято")

    if data == "menu:status":
        await context.bot.send_message(chat_id=chat_id, text="Проверяю системы...")
        text = await asyncio.to_thread(build_status_text)
        await send_long_to_chat(context, chat_id, text)
        return

    if data == "scan:micro":
        await context.bot.send_message(chat_id=chat_id, text="Запускаю Scan Micro...")
        text = await asyncio.to_thread(build_micro_scan_text)
        await send_long_to_chat(context, chat_id, text)
        return

    if data == "scan:degen":
        await context.bot.send_message(chat_id=chat_id, text="Запускаю Scan Degen...")
        text = await asyncio.to_thread(build_degen_scan_text)
        await send_long_to_chat(context, chat_id, text)
        return

    if data == "scan:normal":
        await context.bot.send_message(chat_id=chat_id, text="Запускаю Scan Normal...")
        text = await asyncio.to_thread(build_normal_scan_text)
        await send_long_to_chat(context, chat_id, text)
        return

    if data == "scan:hot":
        await context.bot.send_message(chat_id=chat_id, text="Запускаю Hot Scan...")
        text = await asyncio.to_thread(build_hot_scan_text)
        await send_long_to_chat(context, chat_id, text)
        return

    if data == "watch:list":
        text = await asyncio.to_thread(format_watchlist_text)
        await send_long_to_chat(context, chat_id, text)
        return

    if data == "watch:check":
        await context.bot.send_message(chat_id=chat_id, text="Проверяю watchlist...")
        text = await asyncio.to_thread(build_watch_check_text)
        await send_long_to_chat(context, chat_id, text)
        return

    if data == "wallet:list":
        text = await asyncio.to_thread(format_walletlist_text)
        await send_long_to_chat(context, chat_id, text)
        return

    if data == "wallet:check":
        await context.bot.send_message(chat_id=chat_id, text="Проверяю wallet watchlist...")
        text = await asyncio.to_thread(build_checkwallets_text)
        await send_long_to_chat(context, chat_id, text)
        return

    if data == "menu:morning":
        await context.bot.send_message(chat_id=chat_id, text="Готовлю Morning Intel...")
        prompt = "Сформируй утренний crypto intel ritual report. Дай краткий чек-лист."
        text = await asyncio.to_thread(ask_grok, prompt)
        await send_long_to_chat(context, chat_id, f"🌅 Morning Intel\n\n{text}")
        return

    if data == "menu:evening":
        await context.bot.send_message(chat_id=chat_id, text="Готовлю Evening Intel...")
        prompt = "Сформируй вечерний crypto intel ritual report. Дай краткий чек-лист."
        text = await asyncio.to_thread(ask_grok, prompt)
        await send_long_to_chat(context, chat_id, f"🌙 Evening Intel\n\n{text}")
        return

    if data == "menu:token_help":
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "Как анализировать токен:\n\n"
                "1) /token solana ADDRESS\n"
                "2) Просто отправь адрес токена в чат — я дам кнопки выбора сети.\n"
                "3) Добавить в watchlist:\n/watch solana ADDRESS заметка"
            ),
        )
        return

    if data.startswith("token:"):
        try:
            _, chain_id, address = data.split(":", 2)
        except ValueError:
            await context.bot.send_message(chat_id=chat_id, text="Ошибка callback token data.")
            return

        await context.bot.send_message(chat_id=chat_id, text=f"Анализирую: {chain_id} / {address}")
        text = await asyncio.to_thread(build_token_intel_text, chain_id, address)
        await send_long_to_chat(context, chat_id, text)
        return

    if data.startswith("arktoken:"):
        try:
            _, chain_id, address = data.split(":", 2)
        except ValueError:
            await context.bot.send_message(chat_id=chat_id, text="Ошибка callback arktoken data.")
            return

        await context.bot.send_message(chat_id=chat_id, text=f"Проверяю Arkham token intel: {chain_id} / {address}")
        text = await asyncio.to_thread(build_ark_token_text, chain_id, address)
        await send_long_to_chat(context, chat_id, text)
        return

    if data.startswith("wallet:"):
        try:
            _, address = data.split(":", 1)
        except ValueError:
            await context.bot.send_message(chat_id=chat_id, text="Ошибка callback wallet data.")
            return

        await context.bot.send_message(chat_id=chat_id, text=f"Проверяю Arkham wallet/address intel: {address}")
        text = await asyncio.to_thread(build_wallet_text, address)
        await send_long_to_chat(context, chat_id, text)
        return

    if data.startswith("watchwallet:"):
        try:
            _, address = data.split(":", 1)
        except ValueError:
            await context.bot.send_message(chat_id=chat_id, text="Ошибка callback watchwallet data.")
            return

        status, item = await asyncio.to_thread(add_wallet_to_watchlist, address, "added from button")
        label = "Добавил" if status == "added" else "Обновил"

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"👛 {label} wallet в watchlist\nAddress: {item['address']}",
        )
        return

    if data.startswith("watchadd:"):
        try:
            _, chain_id, address = data.split(":", 2)
        except ValueError:
            await context.bot.send_message(chat_id=chat_id, text="Ошибка callback watch data.")
            return

        status, item = await asyncio.to_thread(add_to_watchlist, chain_id, address, "added from button")
        label = "Добавил" if status == "added" else "Обновил"

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"👁 {label} в watchlist\nChain: {item['chain']}\nAddress: {item['address']}",
        )
        return

    await context.bot.send_message(chat_id=chat_id, text=f"Неизвестная кнопка: {data}")


async def plain_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_wrong_group(update):
        return

    text = (update.message.text or "").strip()

    rab9_signal_match = RAB9_SIGNAL_RE.search(text)
    evm_match = EVM_RE.search(text)
    sol_match = SOLANA_RE.search(text)

    if rab9_signal_match:
        address = rab9_signal_match.group("address")
        await update.message.reply_text("🔎 RAB9 начал анализ MSF-сигнала...")
        result = await asyncio.to_thread(build_pair_resolve_text, address)
        await reply_long(update, result, main_reply_keyboard())
        return

    if evm_match:
        address = evm_match.group(0)
        await update.message.reply_text(
            f"Похоже на EVM-адрес:\n{address}\n\nВыбери сеть:",
            reply_markup=token_chain_keyboard(address, "evm"),
        )
        return

    if sol_match:
        address = sol_match.group(0)
        await update.message.reply_text(
            f"Похоже на Solana-адрес:\n{address}\n\nЧто делаем?",
            reply_markup=token_chain_keyboard(address, "solana"),
        )
        return


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Telegram handler error", exc_info=context.error)


def register_handlers(app: Application):
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("arkhamstatus", arkhamstatus_command))
    app.add_handler(CommandHandler("arktoken", arktoken_command))
    app.add_handler(CommandHandler("wallet", wallet_command))
    app.add_handler(CommandHandler("walletflow", walletflow_command))
    app.add_handler(CommandHandler("tokenflow", tokenflow_command))
    app.add_handler(CommandHandler("wallettx", wallettx_command))
    app.add_handler(CommandHandler("wallettrade", wallettrade_command))
    app.add_handler(CommandHandler("pricesource", pricesource_command))
    app.add_handler(CommandHandler("walletswaps", walletswaps_command))
    app.add_handler(CommandHandler("makertrades", makertrades_command))
    app.add_handler(CommandHandler("makerfind", makerfind_command))
    app.add_handler(CommandHandler("pairmakers", pairmakers_command))
    app.add_handler(CommandHandler("pairresolve", pairresolve_command))
    app.add_handler(CommandHandler("testsignal", testsignal_command))
    app.add_handler(CommandHandler("walletprofile", walletprofile_command))
    app.add_handler(CommandHandler("watchwallet", watchwallet_command))
    app.add_handler(CommandHandler("walletlist", walletlist_command))
    app.add_handler(CommandHandler("unwatchwallet", unwatchwallet_command))
    app.add_handler(CommandHandler("checkwallets", checkwallets_command))

    app.add_handler(CommandHandler("micro", micro_command))
    app.add_handler(CommandHandler("degen", degen_command))
    app.add_handler(CommandHandler("scan", scan_command))
    app.add_handler(CommandHandler("hot", hot_command))

    app.add_handler(CommandHandler("token", token_command))
    app.add_handler(CommandHandler("watch", watch_command))
    app.add_handler(CommandHandler("watchlist", watchlist_command))
    app.add_handler(CommandHandler("refreshwatch", refreshwatch_command))
    app.add_handler(CommandHandler("unwatch", unwatch_command))
    app.add_handler(CommandHandler("checkwatch", checkwatch_command))
    app.add_handler(CommandHandler("alertsnow", alertsnow_command))

    app.add_handler(CommandHandler("grok", grok_command))
    app.add_handler(CommandHandler("morning", morning_command))
    app.add_handler(CommandHandler("evening", evening_command))

    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, plain_text_handler))
    app.add_error_handler(error_handler)
