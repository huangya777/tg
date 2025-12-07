import os
import json
import random
import requests
from flask import Flask, request, jsonify

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CONFIG_URL = os.environ.get("CONFIG_URL")

if not BOT_TOKEN:
    raise RuntimeError("❌ Missing BOT_TOKEN")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

REPLIES_CACHE = None
REPLIES_LOADED = False

def load_replies():
    global REPLIES_CACHE, REPLIES_LOADED
    try:
        res = requests.get(CONFIG_URL, timeout=5)
        res.raise_for_status()
        data = res.json()
        required = {"keywords", "mentioned_or_replied", "fallback"}
        if not required.issubset(data.keys()):
            raise ValueError("Invalid JSON structure")
        REPLIES_CACHE = data
    except Exception as e:
        print(f"⚠️ Config load failed: {e}")
        REPLIES_CACHE = {
            "keywords": {"测试": ["✅ 配置加载失败，但我在运行！"]},
            "mentioned_or_replied": ["我在（备用模式）"],
            "fallback": ["嗯？（配置异常）"]
        }
    REPLIES_LOADED = True

def get_replies():
    if not REPLIES_LOADED:
        load_replies()
    return REPLIES_CACHE

def handle_incoming_message(message):
    replies = get_replies()
    text = message.get("text", "").strip()
    chat_id = message["chat"]["id"]
    from_user = message["from"]
    bot_id = int(BOT_TOKEN.split(":")[0])  # 从 token 提取 bot ID

    # 判断是否被提及或回复
    is_mentioned = f"@{message.get('entities', [])}"  # 简化：直接用关键词匹配
    is_reply_to_bot = (
        message.get("reply_to_message") and
        message["reply_to_message"].get("from", {}).get("id") == bot_id
    )

    reply_pool = []
    triggered = False

    # 关键词匹配
    for keyword in replies["keywords"]:
        if keyword in text:
            reply_pool = replies["keywords"][keyword]
            triggered = True
            break

    if not triggered and (f"@xiaotaotaoo_bot" in text or is_reply_to_bot):
        reply_pool = replies["mentioned_or_replied"]
        triggered = True

    if not triggered:
        reply_pool = replies["fallback"]

    if reply_pool:
        reply_text = random.choice(reply_pool)
        # 直接调用 Telegram API 发送回复
        requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": chat_id, "text": reply_text}
        )

app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    try:
        data = request.get_json()
        if data and "message" in data and "text" in data["message"]:
            handle_incoming_message(data["message"])
        return "OK", 200
    except Exception as e:
        print(f"❌ Webhook error: {e}")
        return "OK", 200  # 始终返回 200 避免 Telegram 重试

@app.route("/health")
def health_check():
    return "✅ Bot is running on Vercel!"

@app.route("/reload-config")
def reload_config():
    global REPLIES_LOADED
    REPLIES_LOADED = False
    get_replies()
    return jsonify({"status": "Config reloaded"})
