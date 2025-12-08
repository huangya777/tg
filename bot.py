import os
import json
import random
import requests
import logging
import time
from collections import defaultdict
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
BOT_USERNAME = os.environ["BOT_USERNAME"].lower()
CONFIG_URL = os.environ.get(
    "CONFIG_URL",
    "https://raw.githubusercontent.com/huangya777/tg/main/replies.json"
)
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

_last_trigger = defaultdict(float)
COOLDOWN_SECONDS = 3

DEFAULT_REPLIES = {
    "keywords": {},
    "mentioned_or_replied": ["我在呢～", "你说？", "我听着呢！"],
    "fallback": ["你好！我是小桃桃 🍑"]
}

_config_cache = None

def get_replies():
    global _config_cache
    try:
        res = requests.get(CONFIG_URL, timeout=5)
        res.raise_for_status()
        _config_cache = res.json()
    except Exception as e:
        logger.error(f"⚠️ 配置加载失败: {e}")
        _config_cache = DEFAULT_REPLIES
    return _config_cache

@app.route('/reload-config', methods=['GET'])
def reload_config():
    global _config_cache
    _config_cache = None
    get_replies()
    return jsonify({"status": "Config reloaded"}), 200

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.json
    if "message" in update:
        handle_incoming_message(update["message"])
    return '', 200

def handle_incoming_message(message):
    if "text" not in message:
        return

    text = message["text"]
    chat = message["chat"]
    chat_id = chat["id"]
    from_user = message.get("from", {})
    user_id = from_user.get("id")
    message_id = message["message_id"]

    bot_id = int(BOT_TOKEN.split(":")[0])

    if user_id == bot_id:
        logger.info("🤖 忽略机器人自身消息")
        return

    is_group = chat["type"] in ("group", "supergroup")

    current_time = time.time()
    if current_time - _last_trigger[user_id] < COOLDOWN_SECONDS:
        logger.info(f"⏳ 用户 {user_id} 触发冷却，跳过响应")
        return
    _last_trigger[user_id] = current_time

    is_mentioned = False
    is_reply_to_bot = False

    if is_group and "entities" in message:
        expected_mention = f"@{BOT_USERNAME}"
        for entity in message["entities"]:
            if entity["type"] == "mention":
                mentioned = text[entity["offset"]:entity["offset"] + entity["length"]]
                if mentioned.lower().strip() == expected_mention.lower():
                    is_mentioned = True
                    break

    if "reply_to_message" in message:
        replied_msg = message["reply_to_message"]
        if replied_msg.get("from", {}).get("id") == bot_id:
            is_reply_to_bot = True

    logger.info(f"📥 收到消息 | 群聊: {is_group} | 文本: '{text}'")
    logger.info(f"🔍 @检测: {is_mentioned}, 回复Bot: {is_reply_to_bot}")

    replies = get_replies()

    reply_pool = []
    triggered_by_keyword = False

    for keyword in replies["keywords"]:
        if keyword in text:
            reply_pool = replies["keywords"][keyword]
            triggered_by_keyword = True
            break

    if triggered_by_keyword:
        pass
    else:
        if is_group:
            if is_mentioned or is_reply_to_bot:
                reply_pool = replies.get("mentioned_or_replied", ["我在呢～"])
            else:
                logger.info("🔇 无关键词且未触发互动，静默忽略")
                return
        else:
            reply_pool = replies.get("fallback", ["你好呀～"])

    if reply_pool:
        reply_text = random.choice(reply_pool)
        logger.info(f"📤 发送回复: '{reply_text}' 到 {chat_id}")

        try:
            if reply_text.startswith("voice:"):
                filename = reply_text.replace("voice:", "").strip()
                voice_url = f"https://github.com/huangya777/tg/releases/download/v1.0/{filename}"
                voice_data = requests.get(voice_url, timeout=10).content
                requests.post(
                    f"{TELEGRAM_API}/sendVoice",
                    data={
                        "chat_id": chat_id,
                        "reply_to_message_id": message_id
                    },
                    files={"voice": ("voice.ogg", voice_data, "audio/ogg")},
                    timeout=10
                )
            else:
                actual_text = reply_text.replace("text:", "").strip()
                requests.post(
                    f"{TELEGRAM_API}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": actual_text,
                        "reply_to_message_id": message_id
                    },
                    timeout=5
                )
        except Exception as e:
            logger.error(f"❌ 发送失败: {e}")

if __name__ == '__main__':
    app.run(debug=True)
