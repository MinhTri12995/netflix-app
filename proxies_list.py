import random

# AWS EC2 Free Tier Proxy Server
SINGLE_ROTATING_PROXY = "http://admin:Proxy123456@18.143.199.199:3128"

USE_DIRECT_RENDER = False  # Bật False để dùng Proxy AWS

def get_random_proxy():
    if USE_DIRECT_RENDER:
        return None
    return {
        "http": SINGLE_ROTATING_PROXY,
        "https": SINGLE_ROTATING_PROXY
    }

