import os
import random
import requests
import time

from dotenv import load_dotenv

load_dotenv()

# Cấu hình Webshare Rotating Proxy chuẩn từ Dashboard / Environment (.env)
WEBSHARE_USERNAME = os.environ.get("WEBSHARE_USERNAME", "").strip()
WEBSHARE_PASSWORD = os.environ.get("WEBSHARE_PASSWORD", "").strip()
WEBSHARE_HOST = os.environ.get("WEBSHARE_HOST", "p.webshare.io").strip()
WEBSHARE_PORT = os.environ.get("WEBSHARE_PORT", "80").strip()

# Gateway xoay IP tự động của Webshare
if WEBSHARE_USERNAME and WEBSHARE_PASSWORD and WEBSHARE_HOST:
    ROTATING_PROXY_URL = f"http://{WEBSHARE_USERNAME}:{WEBSHARE_PASSWORD}@{WEBSHARE_HOST}:{WEBSHARE_PORT}"
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
