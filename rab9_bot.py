import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from colorama import init, Fore, Style

init(autoreset=True)

# ================== НАСТРОЙКИ ==================
TOKEN = "8459717047:AAEIbHqtTph_GOm9cBha1WP8UeU3yUcf6AU"
GROK_API_KEY = "твой_реальный_grok_ключ_здесь"   # ← ОБЯЗАТЕЛЬНО ЗАМЕНИ!
GROUP_ID = -1003979753733

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != GROUP_ID:
        await update.message.reply_text("❌ Бот работает только в этой группе.")
        return
    await update.message.reply_text(
        "👑 <b>rab9 — On-Chain Sniper</b>\n\n"
        "Отправь CA токена — получи анализ.",
        parse_mode='HTML'
    )

async def check_token_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != GROUP_ID:
        return

    ca = update.message.text.strip()
    if len(ca) < 30 or len(ca) > 50:
        return

    await update.message.reply_text("🔍 Анализирую on-chain...")

    try:
        # Dexscreener
        ds = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{ca}", timeout=12).json()
        pair = ds.get("pairs", [{}])[0]
        base = pair.get("baseToken", {})

        name = base.get("name", "Unknown")
        symbol = base.get("symbol", "???")
        price = float(pair.get("priceUsd") or 0)
        mc = float(pair.get("fdv") or 0)
        liquidity = float(pair.get("liquidity", {}).get("usd") or 0)
        volume = float(pair.get("volume", {}).get("h24") or 0)
        change_24h = pair.get("priceChange", {}).get("h24", 0)

        final_text = f"""
🔥 <b>{name} ({symbol})</b>
├ <code>{ca}</code>

📊 Метрики
├ MC: ${mc:,.0f}
├ Liquidity: ${liquidity:,.0f}
├ 24h Vol: ${volume:,.0f}
├ 24h: {change_24h}%

🧠 Анализ в разработке...
"""

        await update.message.reply_text(final_text.strip(), parse_mode='HTML')

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:80]}")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_token_handler))

    print("🚀 rab9 запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
