import os
import random

# Danh sách Proxy Mỹ (SOCKS5 hoặc HTTP)
PROXIES = [
    "socks5://nodzxvcx:tton2hgnp5so@67.227.14.235:6827/"
]

USE_DIRECT_RENDER = False

def get_random_proxy():
    if USE_DIRECT_RENDER or not PROXIES:
        return None
    proxy_url = random.choice(PROXIES)
    return {
        "http": proxy_url,
        "https": proxy_url
    }
