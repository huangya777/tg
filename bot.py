import os
import json
import random
import requests
import logging
import time
from collections import defaultdict
from flask import Flask, request, jsonify

# 日志配置
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# === 配置 ===
BOT_TOKEN = os.environ["BOT_TOKEN"]
BOT_USERNAME = os.environ["BOT_USERNAME"].lower()
CONFIG_URL = os.environ.get(
    "CONFIG_URL",
    "https://raw.githubusercontent.com/huangya777/tg/main/replies.json"
)
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# 防刷冷却：每个用户 3 秒内只响应一次
_last_trigger = defaultdict(float)
COOLDOWN_SECONDS = 3

# 默认安全回复
DEFAULT_REPLIES = {
    "keywords": {},
    "mentioned_or_replied": ["我在！但配置异常，请检查 replies.json"],
    "fallback": ["配置异常，请联系管理员"]
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

    # 获取 bot 自身 ID
    bot_id = int(BOT_TOKEN.split(":")[0])

    # 忽略机器人自己发的消息（防循环）
    if user_id == bot_id:
        logger.info("🤖 忽略机器人自身消息")
        return

    is_group = chat["type"] in ("group", "supergroup")

    # === 冷却检查（防刷）===
    current_time = time.time()
    if current_time - _last_trigger[user_id] < COOLDOWN_SECONDS:
        logger.info(f"⏳ 用户 {user_id} 触发冷却，跳过响应")
        return
    _last_trigger[user_id] = current_time

    # === 检测是否被 @ 或回复（用于日志，不影响响应）===
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

    # === 日志记录 ===
    logger.info(f"📥 收到消息 | 群聊: {is_group} | 文本: '{text}'")
    logger.info(f"🔍 @检测: {is_mentioned}, 回复Bot: {is_reply_to_bot}")

    # === 关键逻辑：只要不是自己发的，就处理（因 Privacy 已关闭）===
    # 不再限制 must be @ or replied — 全群消息都可触发关键词
    replies = get_replies()

    reply_pool = []
    triggered_by_keyword = False

    # 尝试匹配关键词
    for keyword in replies["keywords"]:
        if keyword in text:
            reply_pool = replies["keywords"][keyword]
            triggered_by_keyword = True
            break

    # 如果没匹配到关键词
if not triggered_by_keyword:
    if is_group:
        # 群聊：检查是否回复了机器人
        if is_reply_to_bot:
            # 即使没关键词，也回复 mentioned_or_replied 池
            reply_pool = replies.get("mentioned_or_replied", ["我在呢～"])
        else:
            # 普通群消息（非 @、非回复、无关键词）→ 静默
            logger.info("🔇 无关键词且未回复机器人，静默忽略")
            return
    else:
        # 私聊：用 fallback
        reply_pool = replies.get("fallback", ["你好呀～"])

    # 如果有回复内容
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
