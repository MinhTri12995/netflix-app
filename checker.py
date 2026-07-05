import requests
import time
import proxies_list

def check_account_live(netflix_id, secure_netflix_id=""):
    """
    Kiểm tra cookie Netflix có còn sống không.
    Trả về True/LIVE nếu LIVE, DIE nếu chết hoặc bắt Update Payment.
    """
    url = "https://www.netflix.com/YourAccount"
    
    cookies = {
        "NetflixId": netflix_id
    }
    if secure_netflix_id:
        cookies["SecureNetflixId"] = secure_netflix_id
        
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate"  # Ép nén gzip để tiết kiệm cực độ dung lượng
    }

    # Dùng Proxy để không bị lộ IP thật và bị Block
    proxy_dict = proxies_list.get_random_proxy()

    try:
        time.sleep(1)
        response = requests.get(
            url, 
            cookies=cookies, 
            headers=headers, 
            proxies=proxy_dict,
            allow_redirects=True, # Cho phép chuyển hướng để xem có bị đá ra trang đăng nhập không
            timeout=15
        )
        
        # Nếu bị ném ra trang login hoặc các trang lỗi thanh toán
        url_lower = response.url.lower()
        if "netflix.com/login" in url_lower or "/payment" in url_lower or "/clearcookies" in url_lower or "/restart" in url_lower:
            return "DIE", None
            
        html_text = response.text.lower()
        
        # Nhận diện lỗi bằng các mã kỹ thuật (KHÔNG phụ thuộc vào ngôn ngữ)
        bad_keywords = [
            # Biến JSON hệ thống
            '"membershipstatus":"past_due"',
            '"membershipstatus":"former_member"',
            '"membershipstatus":"never_member"',
            '"status":"past_due"',
            '"status":"former_member"',
            '"status":"never_member"',
            '"ispaymentonhold":true',
            '"ispaymenthold":true',
            '"haspaymenthold":true',
            '"isactive":false',
            
            # Thuộc tính UI toàn cầu (không đổi theo ngôn ngữ)
            'data-uia="banner-payment-failure"',
            'data-uia="payment-update-button"',
            'data-uia="action_update_payment"',
            'data-uia="account-restart-membership"',
            'data-uia="finish-sign-up-button"',
            
            # Chuỗi text phổ biến (Dự phòng cho tiếng Anh và Tiếng Việt)
            "update payment",
            "cập nhật phương thức thanh toán",
            "restart membership",
            "khôi phục tư cách thành viên",
            "finish sign-up",
            "thanh toán của bạn",
            "update your payment"
        ]
        
        for kw in bad_keywords:
            if kw in html_text:
                print(f"Cookie dính lỗi thanh toán ({kw}) -> Xóa!")
                return "DIE", None
                
        # Nếu trang Account load thành công và không có từ khóa lỗi -> LIVE
        if response.status_code == 200:
            import re
            plan = "Standard" # Mặc định để tránh phát nhầm Premium
            
            # Quét các biến kỹ thuật chứa tên gói cước (hỗ trợ cả dấu cách)
            patterns = [
                r'"planname"\s*:\s*"([^"]+)"',
                r'"localizedplanname"\s*:\s*"([^"]+)"',
                r'data-uia="plan-label"[^>]*>([^<]+)<',
                r'"tier"\s*:\s*"([^"]+)"',
                r'"plan_tier"\s*:\s*"([^"]+)"'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, html_text)
                if match:
                    extracted = match.group(1).lower()
                    if 'premium' in extracted or 'ultra' in extracted:
                        plan = "Premium"
                    elif 'standard' in extracted:
                        plan = "Standard"
                    elif 'basic' in extracted or 'cơ bản' in extracted:
                        plan = "Basic"
                    break
            
            return "LIVE", plan
            
        return "ERROR", None
            
    except Exception as e:
        print(f"Lỗi khi kiểm tra cookie: {e}")
        return "ERROR", None

