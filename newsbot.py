import asyncio
import logging
import requests
import os
from datetime import datetime
from collections import defaultdict
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram import Update

logging.basicConfig(level=logging.WARNING)

API_ID = 31302205
API_HASH = "f8050c118642ca3b4a92414798136ed5"
BOT_TOKEN = "8138415576:AAEY6-m9sPogteVGp7ZFiN8ITHZ2Ar09FmE"
CMC_KEY = "30dd4f5838d84656afc425ed4e3e18e1"
SESSION_STRING = os.environ.get("SESSION_STRING", "")

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

BULLISH = ["рост", "растёт", "памп", "buy", "bull", "bullish", "вырос", "выше", "moon", "pump", "green", "увеличил"]
BEARISH = ["падение", "падает", "dump", "sell", "bear", "bearish", "упал", "ниже", "обвал", "снизил", "кризис", "down"]

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
                result[sym] = {"price": q["price"], "change_24h": q["percent_change_24h"]}
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
    mentioned_coins = set()
    for text in news_list:
        bull, bear, coins = analyze(text)
        total_bull += bull
        total_bear += bear
        mentioned_coins.update(coins)
    total = total_bull + total_bear
    if total == 0:
        sentiment, direction = "Недостаточно данных", "Боковик"
    elif total_bull > total_bear * 1.3:
        sentiment, direction = "Рынок БЫЧИЙ", "Вероятен рост"
    elif total_bear > total_bull * 1.3:
        sentiment, direction = "Рынок МЕДВЕЖИЙ", "Вероятно падение"
    else:
        sentiment, direction = "Рынок НЕЙТРАЛЬНЫЙ", "Боковое движение"
    msg = f"ПРОГНОЗ на основе {len(news_list)} новостей\n"
    msg += f"{sentiment}\n{direction}\n"
    msg += f"Бычьих: {total_bull} | Медвежьих: {total_bear}\n"
    if mentioned_coins:
        prices = get_prices(list(mentioned_coins))
        if prices:
            msg += "\nЦены:\n"
            for coin, data in prices.items():
                arrow = "+" if data["change_24h"] > 0 else "-"
                msg += f"{coin}: ${data['price']:,.2f} ({data['change_24h']:+.2f}%)\n"
    msg += f"\n{datetime.now().strftime('%H:%M %d.%m.%Y')}"
    msg += "\nНе является финансовым советом!"
    return msg

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MY_CHAT_ID
    MY_CHAT_ID = update.effective_chat.id
    await update.message.reply_text("Bot started!\n/add @channel\n/list\n/forecast\n/price BTC ETH\n/clear")

async def add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Example: /add @news_crypto")
        return
    channel = context.args[0]
    if not channel.startswith("@"):
        channel = "@" + channel
    if channel not in CHANNELS:
        CHANNELS.append(channel)
        await update.message.reply_text(f"Added {channel}!")
    else:
        await update.message.reply_text("Already exists.")

async def list_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("\n".join(CHANNELS) if CHANNELS else "No channels.")

async def price_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbols = [s.upper() for s in context.args] if context.args else ["BTC", "ETH", "SOL"]
    prices = get_prices(symbols)
    if not prices:
        await update.message.reply_text("Failed to get prices.")
        return
    msg = "Prices:\n"
    for coin, data in prices.items():
        msg += f"{coin}: ${data['price']:,.2f} ({data['change_24h']:+.2f}%)\n"
    await update.message.reply_text(msg)

async def forecast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not news_buffer:
        await update.message.reply_text("No news yet.")
        return
    await update.message.reply_text(make_forecast(news_buffer))

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    news_buffer.clear()
    await update.message.reply_text("Cleared.")

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
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await client.connect()
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
                tone = "Positive" if bull > bear else "Negative" if bear > bull else "Neutral"
                coins_str = " | ".join(coins) if coins else "market"
                msg = f"@{username}\n{tone} | {coins_str}\n\n{text[:250]}\n\n/forecast"
                await app.bot.send_message(chat_id=MY_CHAT_ID, text=msg)
        except Exception as e:
            logging.error(e)
    print("Newsbot started!")
    await client.run_until_disconnected()

asyncio.run(run_bot())
