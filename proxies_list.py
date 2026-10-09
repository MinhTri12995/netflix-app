import os
import random
import requests
import time
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv()

# Cấu hình Webshare Rotating Proxy (Hỗ trợ proxy xoay vòng với fallback tự động)
ENABLE_PROXY = os.environ.get("ENABLE_PROXY", "true").lower() in ["true", "1"]
WEBSHARE_USERNAME = os.environ.get("WEBSHARE_USERNAME", "").strip()
WEBSHARE_PASSWORD = os.environ.get("WEBSHARE_PASSWORD", "").strip()
WEBSHARE_HOST = os.environ.get("WEBSHARE_HOST", "p.webshare.io").strip()
WEBSHARE_PORT = os.environ.get("WEBSHARE_PORT", "9999").strip()
WEBSHARE_PROTOCOL = os.environ.get("WEBSHARE_PROTOCOL", "http").strip().lower()
if WEBSHARE_PROTOCOL == "socks5":
    WEBSHARE_PROTOCOL = "socks5h"
if WEBSHARE_PROTOCOL not in ("http", "https", "socks5h"):
    raise ValueError("Unsupported proxy protocol")

# Tự động gắn hậu tố -rotate nếu dùng gateway p.webshare.io và người dùng chỉ điền username thường
proxy_user = WEBSHARE_USERNAME
if WEBSHARE_HOST == "p.webshare.io" and proxy_user and not proxy_user.endswith("-rotate"):
    proxy_user = f"{proxy_user}-rotate"

# Gateway xoay IP tự động của Webshare
if ENABLE_PROXY and proxy_user and WEBSHARE_PASSWORD and WEBSHARE_HOST:
    ROTATING_PROXY_URL = f"{WEBSHARE_PROTOCOL}://{quote(proxy_user, safe='')}:{quote(WEBSHARE_PASSWORD, safe='')}@{WEBSHARE_HOST}:{WEBSHARE_PORT}"
    ROTATING_PROXY_DICT = {
        "http": ROTATING_PROXY_URL,
        "https": ROTATING_PROXY_URL
    }
    PROXIES = [ROTATING_PROXY_URL]
    _PROXIES_CACHE = [ROTATING_PROXY_DICT]
else:
    ROTATING_PROXY_URL = ""
    ROTATING_PROXY_DICT = None
    PROXIES = []
    _PROXIES_CACHE = []

_LAST_SYNC_TIME = time.time()
_SYNC_INTERVAL = 600
_PROXY_DISABLED_UNTIL = 0

def mark_proxy_failed(reason=""):
    """Tạm ngưng proxy trong 60s khi phát hiện lỗi (400 Bad Request / 407 / timeout) để không làm chậm luồng xuất acc"""
    global _PROXY_DISABLED_UNTIL
    _PROXY_DISABLED_UNTIL = time.time() + 60
    print(f"[Proxy CircuitBreaker] Tam dung Proxy 60s - Fallback to direct network (Reason: {reason})")

def is_proxy_available():
    """Kiểm tra proxy có được bật và đang sẵn sàng không"""
    if not ENABLE_PROXY:
        return False
    if time.time() < _PROXY_DISABLED_UNTIL:
        return False
    return bool(ROTATING_PROXY_DICT or _PROXIES_CACHE)

def get_rotating_proxy():
    """Trả về proxy rotating gateway của Webshare"""
    if not is_proxy_available():
        return None
    return ROTATING_PROXY_DICT

def get_random_proxy():
    """Lấy proxy xoay vòng Webshare"""
    if not is_proxy_available():
        return None
    global _PROXIES_CACHE
    if _PROXIES_CACHE:
        p = random.choice(_PROXIES_CACHE)
        if isinstance(p, dict):
            return p
        return {"http": p, "https": p}
    return ROTATING_PROXY_DICT

def sync_webshare_proxies():
    """Khởi tạo kết nối với Webshare rotating proxy"""
    global _PROXIES_CACHE, _LAST_SYNC_TIME
    if is_proxy_available():
        _PROXIES_CACHE = [ROTATING_PROXY_DICT]
    else:
        _PROXIES_CACHE = []
    _LAST_SYNC_TIME = time.time()
    return _PROXIES_CACHE

def get_proxies():
    if not is_proxy_available():
        return []
    return _PROXIES_CACHE
