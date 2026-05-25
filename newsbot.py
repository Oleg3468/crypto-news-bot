import asyncio
import logging
import requests
from datetime import datetime
from collections import defaultdict
from telethon import TelegramClient, events
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram import Update

logging.basicConfig(level=logging.WARNING)

API_ID = 31302205
API_HASH = "f8050c118642ca3b4a92414798136ed5"
BOT_TOKEN = "8138415576:AAEY6-m9sPogteVGp7ZFiN8ITHZ2Ar09FmE"
CMC_KEY = "30dd4f5838d84656afc425ed4e3e18e1"

CHANNELS = []
MY_CHAT_ID = None
news_buffer = []

COINS = {
    "BTC": ["btc", "bitcoin", "биткоин"],
    "ETH": ["eth", "ethereum", "эфир"],
    "SOL": ["sol", "solana", "солана"],
    "BNB": ["bnb", "binance"],
    "XRP": ["xrp", "ripple", "рипл"],
}

BULLISH = ["рост", "растёт", "памп", "buy", "bull", "bullish", "вырос",
           "выше", "🚀", "moon", "pump", "green", "увеличил", "пробил"]
BEARISH = ["падение", "падает", "dump", "sell", "bear", "bearish", "упал",
           "ниже", "обвал", "снизил", "кризис", "red", "down", "дамп"]

def get_prices(symbols):
    try:
        url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
        headers = {"X-CMC_PRO_API_KEY": CMC_KEY}
        params = {"symbol": ",".join(symbols), "convert": "USD"}
        r = requests.get(url, headers=headers, params=params, timeout=10)
        data = r.json()
        result = {}
        for sym in symbols:
            if sym in data.get("data", {}):
                q = data["data"][sym]["quote"]["USD"]
                result[sym] = {
                    "price": q["price"],
                    "change_24h": q["percent_change_24h"],
                    "volume_24h": q["volume_24h"],
                }
        return result
    except:
        return {}

def analyze(text):
    t = text.lower()
    bull = sum(1 for w in BULLISH if w in t)
    bear = sum(1 for w in BEARISH if w in t)
    coins_found = [c for c, keys in COINS.items() if any(k in t for k in keys)]
    return bull, bear, coins_found

def make_forecast(news_list):
    total_bull = 0
    total_bear = 0
    coin_scores = defaultdict(lambda: [0, 0])
    mentioned_coins = set()

    for text in news_list:
        bull, bear, coins = analyze(text)
        total_bull += bull
        total_bear += bear
        for coin in coins:
            coin_scores[coin][0] += bull
            coin_scores[coin][1] += bear
            mentioned_coins.add(coin)

    total = total_bull + total_bear
    if total == 0:
        sentiment = "😐 Недостаточно данных"
        direction = "Боковик"
    elif total_bull > total_bear * 1.3:
        sentiment = "📈 Рынок БЫЧИЙ"
        direction = "Вероятен рост"
    elif total_bear > total_bull * 1.3:
        sentiment = "📉 Рынок МЕДВЕЖИЙ"
        direction = "Вероятно падение"
    else:
        sentiment = "😐 Рынок НЕЙТРАЛЬНЫЙ"
        direction = "Боковое движение"

    msg = f"🔮 ПРОГНОЗ на основе {len(news_list)} новостей\n"
    msg += f"{'─'*30}\n"
    msg += f"{sentiment}\n📊 {direction}\n"
    msg += f"🟢 Бычьих: {total_bull} | 🔴 Медвежьих: {total_bear}\n"

    if mentioned_coins:
        prices = get_prices(list(mentioned_coins))
        if prices:
            msg += f"\n💰 Цены прямо сейчас:\n"
            for coin, data in prices.items():
                arrow = "📈" if data["change_24h"] > 0 else "📉"
                msg += f"  {arrow} {coin}: ${data['price']:,.2f} ({data['change_24h']:+.2f}%)\n"

    msg += f"\n🕐 {datetime.now().strftime('%H:%M %d.%m.%Y')}"
    msg += f"\n⚠️ Не является финансовым советом!"
    return msg

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MY_CHAT_ID
    MY_CHAT_ID = update.effective_chat.id
    await update.message.reply_text(
        "✅ Бот запущен!\n\n"
        "/add @канал — добавить канал\n"
        "/list — список каналов\n"
        "/forecast — прогноз + цены\n"
        "/price BTC ETH — текущие цены\n"
        "/clear — очистить новости"
    )

async def add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Пример: /add @news_crypto")
        return
    channel = context.args[0]
    if not channel.startswith("@"):
        channel = "@" + channel
    if channel not in CHANNELS:
        CHANNELS.append(channel)
        await update.message.reply_text(f"✅ Канал {channel} добавлен!")
    else:
        await update.message.reply_text("Уже есть.")

async def list_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if CHANNELS:
        await update.message.reply_text("📋 " + "\n".join(CHANNELS))
    else:
        await update.message.reply_text("Нет каналов. /add @канал")

async def price_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbols = [s.upper() for s in context.args] if context.args else ["BTC", "ETH", "SOL"]
    prices = get_prices(symbols)
    if not prices:
        await update.message.reply_text("❌ Не удалось получить цены.")
        return
    msg = "💰 Текущие цены:\n"
    for coin, data in prices.items():
        arrow = "📈" if data["change_24h"] > 0 else "📉"
        msg += f"{arrow} {coin}: ${data['price']:,.2f} ({data['change_24h']:+.2f}%)\n"
    await update.message.reply_text(msg)

async def forecast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not news_buffer:
        await update.message.reply_text("📭 Новостей пока нет.")
        return
    await update.message.reply_text(make_forecast(news_buffer))

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    news_buffer.clear()
    await update.message.reply_text("🗑 Буфер очищен.")

async def run_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_channel))
    app.add_handler(CommandHandler("list", list_channels))
    app.add_handler(CommandHandler("forecast", forecast))
    app.add_handler(CommandHandler("price", price_cmd))
    app.add_handler(CommandHandler("clear", clear))
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    client = TelegramClient("session", API_ID, API_HASH)
    await client.start()

    @client.on(events.NewMessage())
    async def handler(event):
        if MY_CHAT_ID is None:
            return
        try:
            chat = await event.get_chat()
            username = getattr(chat, "username", None)
            if not username or f"@{username}" not in CHANNELS:
                return
            text = event.message.text or ""
            if not text:
                return
            bull, bear, coins = analyze(text)
            news_buffer.append(text)
            if len(news_buffer) > 100:
                news_buffer.pop(0)
            if bull > 0 or bear > 0:
                tone = "🟢 Позитив" if bull > bear else "🔴 Негатив" if bear > bull else "⚪️ Нейтрально"
                coins_str = " | ".join(coins) if coins else "общий рынок"
                msg = f"📢 @{username}\n{tone} | 💰 {coins_str}\n\n{text[:250]}\n\n💡 /forecast"
                await app.bot.send_message(chat_id=MY_CHAT_ID, text=msg)
        except Exception as e:
            logging.error(e)

    print("Newsbot v3 + CoinMarketCap запущен!")
    await client.run_until_disconnected()

asyncio.run(run_bot())
