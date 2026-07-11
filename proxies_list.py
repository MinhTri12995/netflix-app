import random

# Danh sách các tài khoản Webshare (Rotating Proxy)
# Code sẽ bốc ngẫu nhiên 1 tài khoản để sử dụng cho mỗi lượt khách lấy Link
ROTATING_PROXIES = [
    # Nhóm 1: fgdhvjbc
    "http://fgdhvjbc:husxe5amjib9@31.59.20.176:6754/",
    "http://fgdhvjbc:husxe5amjib9@31.56.127.193:7684/",
    "http://fgdhvjbc:husxe5amjib9@45.38.107.97:6014/",
    "http://fgdhvjbc:husxe5amjib9@198.105.121.200:6462/",
    "http://fgdhvjbc:husxe5amjib9@64.137.96.74:6641/",
    "http://fgdhvjbc:husxe5amjib9@198.23.243.226:6361/",
    "http://fgdhvjbc:husxe5amjib9@38.154.185.97:6370/",
    "http://fgdhvjbc:husxe5amjib9@84.247.60.125:6095/",
    "http://fgdhvjbc:husxe5amjib9@142.111.67.146:5611/",
    "http://fgdhvjbc:husxe5amjib9@191.96.254.138:6185/",

    # Nhóm 2: gvxrfmsr
    "http://gvxrfmsr:cfd5ym3vkh1h@31.59.20.176:6754/",
    "http://gvxrfmsr:cfd5ym3vkh1h@31.56.127.193:7684/",
    "http://gvxrfmsr:cfd5ym3vkh1h@45.38.107.97:6014/",
    "http://gvxrfmsr:cfd5ym3vkh1h@198.105.121.200:6462/",
    "http://gvxrfmsr:cfd5ym3vkh1h@64.137.96.74:6641/",
    "http://gvxrfmsr:cfd5ym3vkh1h@198.23.243.226:6361/",
    "http://gvxrfmsr:cfd5ym3vkh1h@38.154.185.97:6370/",
    "http://gvxrfmsr:cfd5ym3vkh1h@84.247.60.125:6095/",
    "http://gvxrfmsr:cfd5ym3vkh1h@142.111.67.146:5611/",
    "http://gvxrfmsr:cfd5ym3vkh1h@191.96.254.138:6185/"
]

def get_random_proxy():
    proxy = random.choice(ROTATING_PROXIES)
    return {
        "http": proxy,
        "https": proxy
    }
