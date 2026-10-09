import os
import secrets
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

class Config:
    # 1. Bảo mật Flask & Session
    SECRET_KEY = os.environ.get("SECRET_KEY")
    if not SECRET_KEY or SECRET_KEY == "super_secret_key_for_flash_messages_and_sessions_123":
        SECRET_KEY = os.environ.get("FLASK_SECRET")
        if not SECRET_KEY:
            secret_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".secret_key")
            if os.path.exists(secret_file):
                try:
                    with open(secret_file, "r") as f:
                        SECRET_KEY = f.read().strip()
                except Exception:
                    pass
            if not SECRET_KEY:
                SECRET_KEY = secrets.token_hex(32)
                try:
                    with open(secret_file, "w") as f:
                        f.write(SECRET_KEY)
                except Exception:
                    pass

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    # Bật Secure cookie nếu chạy HTTPS (ngrok / domain có SSL)
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "False").lower() in ("true", "1", "yes")
    PERMANENT_SESSION_LIFETIME = 86400 * 3  # Session tồn tại 3 ngày
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # Giới hạn file tải lên tối đa 10MB

    # 2. Xác thực Quản trị viên (Admin)
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com").strip().lower()
    _raw_admin_pass = os.environ.get("ADMIN_PASSWORD", "").strip()
    
    # Cho phép lưu trước chuỗi băm ADMIN_PASSWORD_HASH trong .env nếu muốn bảo mật tối đa
    ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH")
    if not ADMIN_PASSWORD_HASH and _raw_admin_pass:
        ADMIN_PASSWORD_HASH = generate_password_hash(_raw_admin_pass, method="scrypt")

    @classmethod
    def verify_admin(cls, email: str, password: str) -> bool:
        """Xác thực tài khoản admin bằng hash an toàn, chống timing attack"""
        if not email or not password:
            return False
        if email.strip().lower() != cls.ADMIN_EMAIL:
            return False
        if cls.ADMIN_PASSWORD_HASH:
            return check_password_hash(cls.ADMIN_PASSWORD_HASH, password)
        elif cls._raw_admin_pass:
            import hmac
            return hmac.compare_digest(cls._raw_admin_pass, password)
        return False

    # 3. Supabase Cloud Configuration
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_KEY = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_KEY", "")

    # 4. Mistral AI & Vision
    MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")
    MISTRAL_MODEL = os.environ.get("MISTRAL_MODEL", "ministral-8b-latest")

    # 5. Webshare Rotating Proxy
    WEBSHARE_USERNAME = os.environ.get("WEBSHARE_USERNAME", "qizklnon-rotate")
    WEBSHARE_PASSWORD = os.environ.get("WEBSHARE_PASSWORD", "e8y63lmvp8v3")
    WEBSHARE_HOST = os.environ.get("WEBSHARE_HOST", "p.webshare.io")
    WEBSHARE_PORT = int(os.environ.get("WEBSHARE_PORT", 9999))
    if WEBSHARE_HOST == "p.webshare.io" and WEBSHARE_PORT in [80, 8080]:
        WEBSHARE_PORT = 9999
    ENABLE_PROXY = os.environ.get("ENABLE_PROXY", "true").lower() in ("true", "1", "yes")

    # 6. Telegram Bot Alerts
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

    # 7. Server Settings
    PORT = int(os.environ.get("PORT", 5000))
    DEBUG = os.environ.get("FLASK_DEBUG", "False").lower() in ("true", "1", "yes")

    # 8. Feature Flags & Safety Controls
    AUTO_APPROVAL_ENABLED = os.environ.get("AUTO_APPROVAL_ENABLED", "true").lower() in ("true", "1", "yes")

    # 9. API Security & Trusted Proxies (F11, F12)
    ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "")
    _raw_proxies = os.environ.get("TRUSTED_PROXIES", "127.0.0.1,::1")
    TRUSTED_PROXIES = [p.strip() for p in _raw_proxies.split(",") if p.strip()]
