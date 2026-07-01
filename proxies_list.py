import random

# Danh sách các tài khoản Webshare (Rotating Proxy)
# Code sẽ bốc ngẫu nhiên 1 tài khoản để sử dụng cho mỗi lượt khách lấy Link
ROTATING_PROXIES = [
    # Tài khoản 1
    "http://nodzxvcx-rotate:tton2hgnp5so@p.webshare.io:80",
    
    # Tài khoản 2 (Mới thêm)
    # Vì Webshare hỗ trợ cả HTTP và SOCKS5 trên cùng 1 port, dùng http cho ổn định thư viện requests
    "http://nsbwpxnr-rotate:07dg8zrp2h74@p.webshare.io:80"
]

def get_random_proxy():
    proxy = random.choice(ROTATING_PROXIES)
    return {
        "http": proxy,
        "https": proxy
    }
