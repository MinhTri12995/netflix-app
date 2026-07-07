import random

# Danh sách các tài khoản Webshare (Rotating Proxy)
# Code sẽ bốc ngẫu nhiên 1 tài khoản để sử dụng cho mỗi lượt khách lấy Link
ROTATING_PROXIES = [
    "http://xktamdun:985qtdjr7nnw@31.59.20.176:6754/",
    "http://xktamdun:985qtdjr7nnw@31.56.127.193:7684/",
    "http://xktamdun:985qtdjr7nnw@45.38.107.97:6014/",
    "http://xktamdun:985qtdjr7nnw@198.105.121.200:6462/",
    "http://xktamdun:985qtdjr7nnw@64.137.96.74:6641/",
    "http://xktamdun:985qtdjr7nnw@198.23.243.226:6361/",
    "http://xktamdun:985qtdjr7nnw@2.57.21.2:7239/",
    "http://xktamdun:985qtdjr7nnw@38.154.185.97:6370/",
    "http://xktamdun:985qtdjr7nnw@142.111.67.146:5611/",
    "http://xktamdun:985qtdjr7nnw@191.96.254.138:6185/"
]

def get_random_proxy():
    proxy = random.choice(ROTATING_PROXIES)
    return {
        "http": proxy,
        "https": proxy
    }
