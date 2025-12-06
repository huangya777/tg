# bot.py - Telegram Bot for Vercel (Webhook Mode)
import os
import json
import random
import requests
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

# 环境变量
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CONFIG_URL = os.environ.get("CONFIG_URL")
WEBHOOK_PATH = f"/{BOT_TOKEN}" if BOT_TOKEN else "/"

if not BOT_TOKEN:
    raise RuntimeError("❌ Missing BOT_TOKEN in environment variables")

# 加载远程 replies.json
def load_replies():
    try:
        res = requests.get(CONFIG_URL, timeout=5)
        res.raise_for_status()
        data = res.json()
        required = {"keywords", "mentioned_or_replied", "fallback"}
        if not required.issubset(data.keys()):
            raise ValueError("Invalid JSON structure")
        return data
    except Exception as e:
        print(f"⚠️ Failed to load config: {e}")
        return {
            "keywords": {},
            "mentioned_or_replied": ["我在呢～（配置加载失败）"],
            "fallback": ["嗯？（配置异常）"]
        }

REPLIES = load_replies()

# 消息处理
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    for keyword in REPLIES["keywords"]:
        if keyword in text:
            reply_pool = REPLIES["keywords"][keyword]
            triggered = True
            break

    if not triggered and (is_mentioned or is_reply_to_bot):
        reply_pool = REPLIES["mentioned_or_replied"]
        triggered = True

    if not triggered:
        reply_pool = REPLIES["fallback"]

    if reply_pool:
        await message.reply_text(random.choice(reply_pool))

# Flask App for Vercel
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
def reload_config_endpoint():
    global REPLIES
    REPLIES = load_replies()
    return {"status": "Config reloaded"}

if __name__ == "__main__":
    app.run(debug=True)