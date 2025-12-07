import os
import json
import random
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# === 配置 ===
BOT_TOKEN = os.environ["BOT_TOKEN"]
BOT_USERNAME = os.environ["BOT_USERNAME"]  # e.g. "xiaotaotaoo_bot"
CONFIG_URL = os.environ.get(
    "CONFIG_URL",
    "https://raw.githubusercontent.com/huangya777/tg/main/replies.json"
)
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# 默认安全回复（防止配置加载失败）
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
        print(f"⚠️ 配置加载失败: {e}")
        _config_cache = DEFAULT_REPLIES
    return _config_cache

@app.route('/reload-config', methods=['GET'])
def reload_config():
    global _config_cache
    _config_cache = None
    get_replies()  # 重新加载
    return jsonify({"status": "Config reloaded"}), 200

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.json
    if "message" in update:
        handle_incoming_message(update["message"])
    return '', 200

def handle_incoming_message(message):
    # 忽略非文本消息（如图片、贴纸等）
    if "text" not in message:
        return

    text = message["text"].strip()
    chat = message["chat"]
    chat_id = chat["id"]
    from_user = message.get("from", {})
    user_id = from_user.get("id")
    message_id = message["message_id"]  # ← 新增：获取消息ID用于回复

    # 获取 Bot 自身 ID 和用户名
    bot_id = int(BOT_TOKEN.split(":")[0])
    bot_username = BOT_USERNAME

    # 🔒 关键：忽略机器人自己的消息（防止刷屏）
    if user_id == bot_id:
        return

    # 判断是否群聊
    is_group = chat["type"] in ("group", "supergroup")

    # 检查是否被 @ 提及
    is_mentioned = False
    if is_group and "entities" in message:
        for entity in message["entities"]:
            if entity["type"] == "mention":
                mentioned = text[entity["offset"]:entity["offset"] + entity["length"]]
                if mentioned == f"@{bot_username}":
                    is_mentioned = True
                    break

    # 检查是否回复机器人
    is_reply_to_bot = False
    if "reply_to_message" in message:
        replied_msg = message["reply_to_message"]
        if replied_msg.get("from", {}).get("id") == bot_id:
            is_reply_to_bot = True

    # 决定是否响应
    should_respond = False
    if not is_group:
        # 私聊：总是响应
        should_respond = True
    else:
        # 群聊：必须被 @ 或 回复才响应
        if is_mentioned or is_reply_to_bot:
            should_respond = True

    if not should_respond:
        return  # 静默忽略

    # 加载回复配置
    replies = get_replies()

    # 匹配关键词
    reply_pool = []
    triggered_by_keyword = False
    for keyword in replies["keywords"]:
        if keyword in text:
            reply_pool = replies["keywords"][keyword]
            triggered_by_keyword = True
            break

    # 未触发关键词时的兜底逻辑
    if not triggered_by_keyword:
        if is_group and (is_mentioned or is_reply_to_bot):
            reply_pool = replies["mentioned_or_replied"]
        elif not is_group:
            reply_pool = replies["fallback"]

    # 发送回复
    if reply_pool:
        reply_text = random.choice(reply_pool)
        print(f"📤 发送回复: '{reply_text}' 到聊天 {chat_id}")

        try:
            if reply_text.startswith("voice:"):
                filename = reply_text.replace("voice:", "").strip()
                voice_url = f"https://github.com/huangya777/tg/releases/download/v1.0/{filename}"
                voice_data = requests.get(voice_url, timeout=10).content
                # 发送语音并回复原消息
                requests.post(
                    f"{TELEGRAM_API}/sendVoice",
                    data={
                        "chat_id": chat_id,
                        "reply_to_message_id": message_id  # ← 关键：实现回复效果
                    },
                    files={"voice": ("voice.ogg", voice_data, "audio/ogg")},
                    timeout=10
                )
            else:
                actual_text = reply_text.replace("text:", "").strip()
                # 发送文字并回复原消息
                requests.post(
                    f"{TELEGRAM_API}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": actual_text,
                        "reply_to_message_id": message_id  # ← 关键：实现回复效果
                    },
                    timeout=5
                )
        except Exception as e:
            print(f"❌ 发送失败: {e}")

if __name__ == '__main__':
    app.run(debug=True)
