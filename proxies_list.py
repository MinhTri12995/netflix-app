import random

# Webshare Single Backbone Rotating Proxy Endpoint
SINGLE_ROTATING_PROXY = "http://nodzxvcx:tton2hgnp5so@31.59.20.176:6754/"

USE_DIRECT_RENDER = False  # Bật False để dùng Proxy xoay vòng Webshare mới

def get_random_proxy():
    if USE_DIRECT_RENDER:
        return None
    return {
        "http": SINGLE_ROTATING_PROXY,
        "https": SINGLE_ROTATING_PROXY
    }

