import os
import json
import random
import requests
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CONFIG_URL = os.environ.get("CONFIG_URL")

if not BOT_TOKEN:
    raise RuntimeError("❌ Missing BOT_TOKEN")

WEBHOOK_PATH = f"/{BOT_TOKEN}"

REPLIES_CACHE = None
REPLIES_LOADED = False

def load_replies():
    global REPLIES_CACHE, REPLIES_LOADED
    try:
        res = requests.get(CONFIG_URL, timeout=3)
        res.raise_for_status()
        data = res.json()
        required = {"keywords", "mentioned_or_replied", "fallback"}
        if not required.issubset(data.keys()):
            raise ValueError("Invalid JSON structure")
        REPLIES_CACHE = data
    except Exception as e:
        print(f"⚠️ Config load failed: {e}")
        REPLIES_CACHE = {
            "keywords": {},
            "mentioned_or_replied": ["我在呢～（配置加载失败）"],
            "fallback": ["嗯？（配置异常）"]
        }
    REPLIES_LOADED = True

def get_replies():
    if not REPLIES_LOADED:
        load_replies()
    return REPLIES_CACHE

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    replies = get_replies()
    message = update.message
    if not message or not message.text:
        return

    text = message.text.strip()
    bot_id = context.bot.id
    bot_username = context.bot.username

    is_mentioned = f"@{bot_username}" in text
    is_reply_to_bot = (
        message.reply_to_message and
        message.reply_to_message.from_user and
        message.reply_to_message.from_user.id == bot_id
    )

    reply_pool = []
    triggered = False

    for keyword in replies["keywords"]:
        if keyword in text:
            reply_pool = replies["keywords"][keyword]
            triggered = True
            break

    if not triggered and (is_mentioned or is_reply_to_bot):
        reply_pool = replies["mentioned_or_replied"]
        triggered = True

    if not triggered:
        reply_pool = replies["fallback"]

    if reply_pool:
        await message.reply_text(random.choice(reply_pool))

app = Flask(__name__)

@app.route(WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    update = Update.de_json(request.get_json(force=True), application.bot)
    application.update_queue.put_nowait(update)
    return "OK", 200

@app.route("/health")
def health_check():
    return "✅ Bot is running on Vercel!"

@app.route("/reload-config")
def reload_config():
    global REPLIES_LOADED
    REPLIES_LOADED = False
    get_replies()
    return jsonify({"status": "Config reloaded"})
