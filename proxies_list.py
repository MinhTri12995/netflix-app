import os
import random
import requests
import time

# Cấu hình Webshare Proxy (Đã sửa đúng mật khẩu số 8: qov98az2o10z)
WEBSHARE_USERNAME = "cgiwagsj"
WEBSHARE_PASSWORD = "qov98az2o10z"
WEBSHARE_HOST = "p.webshare.io"
WEBSHARE_PORT = "80"

# Gateway xoay IP tự động của Webshare
ROTATING_PROXY_URL = f"http://{WEBSHARE_USERNAME}:{WEBSHARE_PASSWORD}@{WEBSHARE_HOST}:{WEBSHARE_PORT}/"

_PROXIES_CACHE = [ROTATING_PROXY_URL]
_LAST_SYNC_TIME = 0
_SYNC_INTERVAL = 600

def get_rotating_proxy():
    """Trả về proxy rotating gateway của Webshare"""
    return {
        "http": ROTATING_PROXY_URL,
        "https": ROTATING_PROXY_URL
    }

def get_random_proxy():
    """Lấy proxy xoay vòng Webshare"""
    global _PROXIES_CACHE
    if _PROXIES_CACHE:
        p = random.choice(_PROXIES_CACHE)
        return {
            "http": p,
            "https": p
        }
    return get_rotating_proxy()

def sync_webshare_proxies():
    """Khởi tạo kết nối với Webshare rotating proxy"""
    global _PROXIES_CACHE, _LAST_SYNC_TIME
    _PROXIES_CACHE = [ROTATING_PROXY_URL]
    _LAST_SYNC_TIME = time.time()
    print("[Webshare] Đã kích hoạt kết nối Webshare Rotating Proxy: p.webshare.io:80")
    return [get_rotating_proxy()]
