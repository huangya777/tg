# === 导入 ===
import os
import random
import requests
import logging
import time
from collections import defaultdict
from flask import Flask, request, jsonify, send_from_directory

# === 日志配置 ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === 初始化应用 ===
app = Flask(__name__)

# === 静态文件服务（保留但基本不用）===
@app.route('/public/<path:filename>')
def serve_static(filename):
    return send_from_directory('public', filename)

# === 配置 ===
BOT_TOKEN = os.environ["BOT_TOKEN"]
BOT_USERNAME = os.environ["BOT_USERNAME"].lower()
CONFIG_URL = os.environ.get(
    "CONFIG_URL",
    "https://raw.githubusercontent.com/huangya777/tg/main/replies.json"
)
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# 防刷冷却
_last_trigger = defaultdict(float)
COOLDOWN_SECONDS = 3

# 防重复回复
_last_user_reply = defaultdict(str)

# 默认安全回复
DEFAULT_REPLIES = {
    "keywords": {},
    "mentioned_or_replied": ["我在呢～", "你说？", "我听着呢！"],
    "fallback": ["你好！我是小桃桃 🍑"]
}

_config_cache = None

def get_replies():
    global _config_cache
    if _config_cache is not None:
        return _config_cache
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
    chat = message["chat"]
    chat_id = chat["id"]
    from_user = message.get("from", {})
    user_id = from_user.get("id")
    message_id = message["message_id"]

    bot_id = int(BOT_TOKEN.split(":")[0])
    if user_id == bot_id:
        return

    is_group = chat["type"] in ("group", "supergroup")

    # 处理 /reload（仅私聊）
    if "text" in message and not is_group and message["text"] == "/reload":
        global _config_cache
        _config_cache = None
        get_replies()
        try:
            requests.post(
                f"{TELEGRAM_API}/sendMessage",
                json={"chat_id": chat_id, "text": "✅ 配置已刷新！"},
                timeout=10
            )
        except Exception as e:
            logger.error(f"❌ /reload 回复失败: {e}")
        return

    current_time = time.time()
    if current_time - _last_trigger[user_id] < COOLDOWN_SECONDS:
        return
    _last_trigger[user_id] = current_time

    # 检查是否被提及或回复
    is_mentioned = False
    is_reply_to_bot = False

    if is_group and "entities" in message and "text" in message:
        expected_mention = f"@{BOT_USERNAME}"
        for entity in message["entities"]:
            if entity["type"] == "mention":
                mentioned = message["text"][entity["offset"]:entity["offset"] + entity["length"]]
                if mentioned.lower().strip() == expected_mention.lower():
                    is_mentioned = True
                    break

    if "reply_to_message" in message:
        replied_msg = message["reply_to_message"]
        replied_from = replied_msg.get("from") or {}
        replied_user_id = replied_from.get("id")
        if replied_user_id == bot_id:
            is_reply_to_bot = True

    replies = get_replies()
    reply_pool = []
    triggered_by_keyword = False

    # 如果是文本消息，尝试关键词匹配
    if "text" in message:
        text = message["text"]
        logger.info(f"🔍 收到文本: '{text}'")
        for keyword in replies.get("keywords", {}):
            if keyword in text:
                texts = replies["keywords"][keyword]
                reply_pool = [("text", t) for t in texts]
                triggered_by_keyword = True
                logger.info(f"🎯 触发关键词: '{keyword}'")
                break

    # 如果没触发关键词，则根据场景决定是否回复
    if not triggered_by_keyword:
        if is_group:
            if is_mentioned or is_reply_to_bot:
                pool_texts = replies.get("mentioned_or_replied", [])
                reply_pool = [("text", t) for t in pool_texts]
            else:
                return  # 群聊不@不回复
        else:
            # 私聊：无论发文字、贴纸、语音，都走 fallback
            pool_texts = replies.get("fallback", [])
            reply_pool = [("text", t) for t in pool_texts]

    if not reply_pool:
        return

    # 防重复
    last_reply = _last_user_reply.get(user_id, "")
    chosen = random.choice(reply_pool)
    reply_type, content = chosen
    reply_key = f"{reply_type}:{content}"
    attempts = 0
    while len(reply_pool) > 1 and reply_key == last_reply and attempts < 3:
        chosen = random.choice(reply_pool)
        reply_type, content = chosen
        reply_key = f"{reply_type}:{content}"
        attempts += 1

    _last_user_reply[user_id] = reply_key

    # 发送回复（只支持文本）
    try:
        requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": content,
                "reply_to_message_id": message_id,
                "parse_mode": "HTML"
            },
            timeout=10
        )
    except Exception as e:
        logger.error(f"❌ 发送失败: {e}")

# 注意：已完全移除 handle_user_upload！

if __name__ == '__main__':
    app.run(debug=True)
