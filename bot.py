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
        print("🔍 正在尝试加载配置文件...")
        print(f"🌐 CONFIG_URL: {CONFIG_URL}")
        res = requests.get(CONFIG_URL, timeout=8)
        print(f"📥 HTTP 状态码: {res.status_code}")
        if res.status_code != 200:
            raise Exception(f"HTTP {res.status_code}")
        data = res.json()
        print("📄 原始配置内容:", data)

        # 检查必要字段
        required = {"keywords", "mentioned_or_replied", "fallback"}
        if not required.issubset(data.keys()):
            missing = required - set(data.keys())
            raise ValueError(f"缺少必要字段: {missing}")

        REPLIES_CACHE = data
        print("✅ 配置加载成功！")
    except Exception as e:
        print(f"⚠️ 配置加载失败: {e}")
        REPLIES_CACHE = {
            "keywords": {"测试": ["🔧 配置加载失败，但我在运行！"]},
            "mentioned_or_replied": ["我在（安全模式）"],
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
    bot_id = int(BOT_TOKEN.split(":")[0])

    # 判断是否被 @ 提及（正确方式）
    is_mentioned = False
    entities = message.get("entities", [])
    for entity in entities:
        if entity.get("type") == "mention":
            mentioned_text = text[entity["offset"]:entity["offset"] + entity["length"]]
            if mentioned_text == "@xiaotaotaoo_bot":
                is_mentioned = True
                break

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

    if not triggered and (is_mentioned or is_reply_to_bot):
        reply_pool = replies["mentioned_or_replied"]
        triggered = True

    if not triggered:
        reply_pool = replies["fallback"]

    if reply_pool:
        reply_text = random.choice(reply_pool)
        print(f"📤 发送回复: '{reply_text}' 到聊天 {chat_id}")
        try:
            requests.post(
                f"{TELEGRAM_API}/sendMessage",
                json={"chat_id": chat_id, "text": reply_text},
                timeout=5
            )
        except Exception as e:
            print(f"❌ 发送消息失败: {e}")

app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    print("📬 收到新消息！")
    try:
        data = request.get_json(force=True)
        if data and "message" in data and "text" in data["message"]:
            handle_incoming_message(data["message"])
        else:
            print("ℹ️ 非文本消息或格式不符，忽略")
        return "OK", 200
    except Exception as e:
        print(f"💥 Webhook 处理崩溃: {e}")
        return "OK", 200

@app.route("/health")
def health_check():
    return "✅ Bot is running on Vercel!"

@app.route("/reload-config")
def reload_config():
    global REPLIES_LOADED
    print("🔄 手动触发配置重载")
    REPLIES_LOADED = False
    get_replies()
    return jsonify({"status": "Config reloaded"})
