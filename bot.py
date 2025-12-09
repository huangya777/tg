# === 导入 ===
import os
import json
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

# === 静态文件服务（用于托管用户上传的语音等）===
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

# JSONBin 配置（用于持久化存储用户上传的语音/贴纸）
JSONBIN_IO_API_KEY = os.environ.get("JSONBIN_IO_API_KEY")
JSONBIN_IO_BIN_ID = os.environ.get("JSONBIN_IO_BIN_ID")
JSONBIN_IO_READ_URL = f"https://api.jsonbin.io/v3/b/{JSONBIN_IO_BIN_ID}/latest"
JSONBIN_IO_WRITE_URL = f"https://api.jsonbin.io/v3/b/{JSONBIN_IO_BIN_ID}"

# 防刷冷却：每个用户 3 秒内只响应一次
_last_trigger = defaultdict(float)
COOLDOWN_SECONDS = 3

# 防重复回复：记录每个用户上一次的完整回复标识（避免短时间内完全相同）
_last_user_reply = defaultdict(str)

# 默认安全回复
DEFAULT_REPLIES = {
    "keywords": {},
    "mentioned_or_replied": ["我在呢～", "你说？", "我听着呢！"],
    "fallback": ["你好！我是小桃桃 🍑"]
}

_config_cache = None
_jsonbin_cache = None

def get_replies():
    """加载预设关键词回复（仅文本）"""
    global _config_cache
    try:
        res = requests.get(CONFIG_URL, timeout=5)
        res.raise_for_status()
        _config_cache = res.json()
    except Exception as e:
        logger.error(f"⚠️ 配置加载失败: {e}")
        _config_cache = DEFAULT_REPLIES
    return _config_cache

def get_jsonbin_data():
    """从 JSONBin 加载用户上传的语音/贴纸数据"""
    global _jsonbin_cache
    if not JSONBIN_IO_API_KEY or not JSONBIN_IO_BIN_ID:
        return {}
    try:
        headers = {"X-Access-Key": JSONBIN_IO_API_KEY}
        res = requests.get(JSONBIN_IO_READ_URL, headers=headers, timeout=5)
        res.raise_for_status()
        data = res.json()  # ✅ 直接使用整个 JSON，不再取 .record
        _jsonbin_cache = data
        return data
    except Exception as e:
        logger.error(f"⚠️ JSONBin 数据加载失败: {e}")
        return {}

def save_to_jsonbin(data):
    """保存数据到 JSONBin"""
    if not JSONBIN_IO_API_KEY or not JSONBIN_IO_BIN_ID:
        return
    try:
        headers = {
            "Content-Type": "application/json",
            "X-Access-Key": JSONBIN_IO_API_KEY
        }
        # ✅ 不再包装成 {"record": data}，直接发送 data
        res = requests.put(JSONBIN_IO_WRITE_URL, headers=headers, json=data, timeout=10)
        res.raise_for_status()
        logger.info("✅ 用户数据已保存到 JSONBin")
    except Exception as e:
        logger.error(f"❌ 保存到 JSONBin 失败: {e}")

def merge_replies(static_replies, dynamic_data):
    """合并静态文本回复 + 动态语音/贴纸"""
    merged = {}
    # 先加入静态文本
    for kw, texts in static_replies.get("keywords", {}).items():
        merged[kw] = {"text": texts, "voice": [], "sticker": []}
    # 再合并动态内容
    for kw, items in dynamic_data.items():
        if kw not in merged:
            merged[kw] = {"text": [], "voice": [], "sticker": []}
        for item in items:
            if item.startswith("voice:"):
                merged[kw]["voice"].append(item[6:])
            elif item.startswith("sticker:"):
                merged[kw]["sticker"].append(item[8:])
    return merged

@app.route('/reload-config', methods=['GET'])
def reload_config():
    global _config_cache, _jsonbin_cache
    _config_cache = None
    _jsonbin_cache = None
    get_replies()
    get_jsonbin_data()
    return jsonify({"status": "Config reloaded"}), 200

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.json
    if "message" in update:
        handle_incoming_message(update["message"])
    return '', 200

def handle_incoming_message(message):
    if "text" not in message:
        # 处理用户上传：语音或贴纸作为关键词回复
        handle_user_upload(message)
        return

    text = message["text"]
    chat = message["chat"]
    chat_id = chat["id"]
    from_user = message.get("from", {})
    user_id = from_user.get("id")
    message_id = message["message_id"]

    bot_id = int(BOT_TOKEN.split(":")[0])
    if user_id == bot_id:
        return

    is_group = chat["type"] in ("group", "supergroup")

    current_time = time.time()
    if current_time - _last_trigger[user_id] < COOLDOWN_SECONDS:
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
        replied_from = replied_msg.get("from") or {}
        replied_user_id = replied_from.get("id")
        if replied_user_id == bot_id:
            is_reply_to_bot = True

    replies_static = get_replies()
    replies_dynamic = get_jsonbin_data()
    merged_replies = merge_replies(replies_static, replies_dynamic)

    reply_pool = []
    triggered_by_keyword = False

    for keyword in merged_replies:
        if keyword in text:
            pool = []
            pool.extend([("text", t) for t in merged_replies[keyword].get("text", [])])
            pool.extend([("voice", v) for v in merged_replies[keyword].get("voice", [])])
            pool.extend([("sticker", s) for s in merged_replies[keyword].get("sticker", [])])
            if pool:
                reply_pool = pool
                triggered_by_keyword = True
                break

    if not triggered_by_keyword:
        if is_group:
            if is_mentioned or is_reply_to_bot:
                pool = []
                pool.extend([("text", t) for t in replies_static.get("mentioned_or_replied", [])])
                reply_pool = pool
            else:
                return
        else:
            pool = []
            pool.extend([("text", t) for t in replies_static.get("fallback", [])])
            reply_pool = pool

    if not reply_pool:
        return

    last_reply = _last_user_reply.get(user_id, "")
    chosen = random.choice(reply_pool)
    reply_type, content = chosen

    # 防重复：用 (type, content) 作为唯一标识
    reply_key = f"{reply_type}:{content}"
    attempts = 0
    while len(reply_pool) > 1 and reply_key == last_reply and attempts < 3:
        chosen = random.choice(reply_pool)
        reply_type, content = chosen
        reply_key = f"{reply_type}:{content}"
        attempts += 1

    _last_user_reply[user_id] = reply_key

    try:
        if reply_type == "voice":
            requests.post(
                f"{TELEGRAM_API}/sendVoice",
                data={
                    "chat_id": chat_id,
                    "voice": content,
                    "reply_to_message_id": message_id
                },
                timeout=10
            )
        elif reply_type == "sticker":
            requests.post(
                f"{TELEGRAM_API}/sendSticker",
                data={
                    "chat_id": chat_id,
                    "sticker": content,
                    "reply_to_message_id": message_id
                },
                timeout=10
            )
        else:  # text
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
        logger.error(f"❌ 发送消息失败: {e}")

def handle_user_upload(message):
    """处理用户上传的语音/贴纸（需回复机器人并带关键词）"""
    chat = message["chat"]
    chat_id = chat["id"]
    from_user = message.get("from", {})
    user_id = from_user.get("id")
    message_id = message["message_id"]

    bot_id = int(BOT_TOKEN.split(":")[0])
    if user_id == bot_id:
        return

    if "reply_to_message" not in message:
        return

    replied_msg = message["reply_to_message"]
    if "text" not in replied_msg:
        return

    # 检查是否是给机器人的指令，例如：“晚安”
    keyword = replied_msg["text"].strip()
    if not keyword:
        return

    new_item = None
    if "voice" in message:
        file_id = message["voice"]["file_id"]
        new_item = f"voice:{file_id}"
    elif "sticker" in message:
        sticker_id = message["sticker"]["file_id"]
        new_item = f"sticker:{sticker_id}"
    else:
        return

    # 保存到 JSONBin
    data = get_jsonbin_data()
    if keyword not in data:
        data[keyword] = []
    if new_item not in data[keyword]:
        data[keyword].append(new_item)
        save_to_jsonbin(data)

    # 回复用户
    try:
        msg = "✅ 已将该内容添加为关键词“{}”的回复！".format(keyword)
        requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": chat_id, "text": msg, "reply_to_message_id": message_id},
            timeout=10
        )
    except Exception as e:
        logger.error(f"❌ 确认消息发送失败: {e}")

if __name__ == '__main__':
    app.run(debug=True)
