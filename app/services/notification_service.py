import requests
from app.config import Config

def send_telegram_alert(message: str) -> bool:
    """
    Gửi tin nhắn cảnh báo tức thì về Telegram Bot cho Quản trị viên
    Hỗ trợ định dạng HTML.
    """
    token = Config.TELEGRAM_BOT_TOKEN
    chat_id = Config.TELEGRAM_CHAT_ID

    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:
        r = requests.post(url, json=payload, timeout=8)
        return r.status_code == 200
    except Exception as e:
        print(f"[Telegram Alert] Gửi thông báo thất bại: {e}")
        return False
