import os
import random
import requests
import time

from dotenv import load_dotenv

load_dotenv()

# Cấu hình Webshare Rotating Proxy (Hỗ trợ proxy xoay vòng với fallback tự động)
ENABLE_PROXY = os.environ.get("ENABLE_PROXY", "true").lower() in ["true", "1"]
WEBSHARE_USERNAME = os.environ.get("WEBSHARE_USERNAME", "qizklnon-rotate").strip()
WEBSHARE_PASSWORD = os.environ.get("WEBSHARE_PASSWORD", "e8y63lmvp8v3").strip()
WEBSHARE_HOST = os.environ.get("WEBSHARE_HOST", "p.webshare.io").strip()
WEBSHARE_PORT = os.environ.get("WEBSHARE_PORT", "80").strip()

# Tự động gắn hậu tố -rotate nếu dùng gateway p.webshare.io và người dùng chỉ điền username thường
proxy_user = WEBSHARE_USERNAME
if WEBSHARE_HOST == "p.webshare.io" and proxy_user and not proxy_user.endswith("-rotate"):
    proxy_user = f"{proxy_user}-rotate"

# Gateway xoay IP tự động của Webshare
if ENABLE_PROXY and proxy_user and WEBSHARE_PASSWORD and WEBSHARE_HOST:
    ROTATING_PROXY_URL = f"http://{proxy_user}:{WEBSHARE_PASSWORD}@{WEBSHARE_HOST}:{WEBSHARE_PORT}"
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

def get_rotating_proxy():
    """Trả về proxy rotating gateway của Webshare"""
    return ROTATING_PROXY_DICT

def get_random_proxy():
    """Lấy proxy xoay vòng Webshare"""
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
    _PROXIES_CACHE = [ROTATING_PROXY_DICT]
    _LAST_SYNC_TIME = time.time()
    return _PROXIES_CACHE

def get_proxies():
    return _PROXIES_CACHE
