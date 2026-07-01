# Cấu hình Rotating Proxy (Cung cấp bởi Webshare)
# Endpoint này sẽ tự động xoay IP ở phía Server mỗi khi có Request

ROTATING_PROXY_URL = "http://nodzxvcx-rotate:tton2hgnp5so@p.webshare.io:80"

def get_random_proxy():
    # Vì Webshare đã tự động xoay IP, ta chỉ cần trả về đúng 1 đường link này
    return {
        "http": ROTATING_PROXY_URL,
        "https": ROTATING_PROXY_URL
    }
