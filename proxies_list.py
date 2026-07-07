import random

# Danh sách các tài khoản Webshare (Rotating Proxy)
# Code sẽ bốc ngẫu nhiên 1 tài khoản để sử dụng cho mỗi lượt khách lấy Link
ROTATING_PROXIES = [
    # Tài khoản 1
    "http://nodzxvcx-rotate:tton2hgnp5so@p.webshare.io:80",
    
    # Tài khoản 2
    "http://nsbwpxnr-rotate:07dg8zrp2h74@p.webshare.io:80",
    
    # Tài khoản 3
    "http://skzzzhhr-rotate:hu333jds9h3a@p.webshare.io:80",
    
    # Tài khoản 4
    "http://qfcfflym-rotate:bnfu8ype49yu@p.webshare.io:80",
    
    # Tài khoản 5 (Mới thêm)
    "http://xktamdun-rotate:985qtdjr7nnw@p.webshare.io:80",
    
    # Tài khoản 6 (Vừa thêm)
    "http://qlmzdjzk:f7dovz8t49tz@p.webshare.io:80",
    
    # Tài khoản 7 (Bổ sung mới)
    "http://bqpboosr:0qfqi02vzpuq@p.webshare.io:80",
    
    # Tài khoản 8 (Bổ sung mới)
    "http://tryatpyy:cbeedsg7d0lb@p.webshare.io:80",
    
    # Tài khoản 9 (Từ mã Token Webshare)
    "http://ojuhhlkl:ot76anl6o2ig@p.webshare.io:80"
]

def get_random_proxy():
    proxy = random.choice(ROTATING_PROXIES)
    return {
        "http": proxy,
        "https": proxy
    }
