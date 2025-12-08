# === 导入 ===
import os
import json
import random
import requests
import logging
import time
from collections import defaultdict
from flask import Flask, request, jsonify, send_from_directory, Response  # ← 加上 Response

# === 日志配置 ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === 初始化应用 ===
app = Flask(__name__)
# === 内嵌语音文件 ===
MYVOICE_MP3_B64 = "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"

@app.route('/public/myvoice.mp3')
def serve_myvoice():
    import base64
    data = base64.b64decode(MYVOICE_MP3_B64)
    return Response(data, mimetype='audio/mpeg')

# === 静态文件服务 ===
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

# 防刷冷却：每个用户 3 秒内只响应一次
_last_trigger = defaultdict(float)
COOLDOWN_SECONDS = 3

# 防重复回复：记录每个用户上一次的回复文本
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
    # 只处理含文本的消息（但允许回复非文本）
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

    # === 检测是否被 @ 或回复了机器人（兼容贴纸/图片/语音等）===
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

    # 🔧 关键修复：安全提取 replied_user_id，支持回复贴纸/图片/语音
    if "reply_to_message" in message:
        replied_msg = message["reply_to_message"]
        replied_from = replied_msg.get("from") or {}
        replied_user_id = replied_from.get("id")
        if replied_user_id == bot_id:
            is_reply_to_bot = True

    # === 日志记录 ===
    logger.info(f"📥 收到消息 | 群聊: {is_group} | 文本: '{text}'")
    logger.info(f"🔍 @检测: {is_mentioned}, 回复Bot: {is_reply_to_bot}")

    replies = get_replies()

    reply_pool = []
    triggered_by_keyword = False

    # 尝试匹配关键词
    for keyword in replies["keywords"]:
        if keyword in text:
            reply_pool = replies["keywords"][keyword]
            triggered_by_keyword = True
            break

    # === 核心响应逻辑 ===
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

    # 如果有回复内容
    if reply_pool:
        last_reply = _last_user_reply.get(user_id, "")
        reply_text = random.choice(reply_pool)

        # 防止短时间内对同一用户发送完全相同的回复（最多尝试3次）
        attempts = 0
        while len(reply_pool) > 1 and reply_text == last_reply and attempts < 3:
            reply_text = random.choice(reply_pool)
            attempts += 1

        _last_user_reply[user_id] = reply_text
        logger.info(f"📤 发送回复: '{reply_text}' 到 {chat_id}")

        # === 发送回复：语音 or 文本 ===
        if reply_text.startswith("voice:"):
            filename = reply_text.replace("voice:", "").strip()
            voice_url = f"https://{os.environ.get('VERCEL_URL', 'your-bot.vercel.app')}/public/{filename}"
            print(f"🔊 DEBUG：尝试加载语音文件：{voice_url}")
            
            try:
                resp = requests.get(voice_url, timeout=10)
                print(f"📥 语音文件状态码：{resp.status_code}，大小：{len(resp.content)} 字节")
                resp.raise_for_status()
                
                voice_data = resp.content
                send_resp = requests.post(
                    f"{TELEGRAM_API}/sendVoice",
                    data={"chat_id": chat_id, "reply_to_message_id": message_id},
                    files={"voice": ("voice.ogg", voice_data, "audio/ogg")},
                    timeout=10
                )
                print(f"📤 Telegram 发送结果：{send_resp.status_code}")
                
            except Exception as e:
                print(f"❌ 语音发送失败：{e}")
        else:
            # 普通文本回复
            try:
                requests.post(
                    f"{TELEGRAM_API}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": reply_text,
                        "reply_to_message_id": message_id,
                        "parse_mode": "HTML"
                    },
                    timeout=10
                )
            except Exception as e:
                print(f"❌ 文本发送失败：{e}")

if __name__ == '__main__':
    app.run(debug=True)
