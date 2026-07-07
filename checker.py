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
        
        # Làm sạch HTML: Xóa hết khoảng trắng, ngoặc kép, dấu hai chấm, gạch ngang để chống nhiễu JSON/HTML Format
        import re
        html_clean = re.sub(r'[\s"\'\-:]', '', html_text)
        
        # Nhận diện lỗi bằng các mã kỹ thuật cực mạnh (Đã loại bỏ khoảng trắng)
        bad_keywords_clean = [
            # Các trạng thái lỗi chắc chắn 100% (Enum nội bộ của Netflix)
            "past_due",
            "former_member",
            "never_member",
            
            # Các cờ báo lỗi thanh toán (Bắt bất chấp JSON có khoảng trắng hay không)
            "ispaymentonholdtrue",
            "haspaymentholdtrue",
            "isactivefalse",
            
            # Thuộc tính UI toàn cầu
            "bannerpaymentfailure",
            "paymentupdatebutton",
            "actionupdatepayment",
            "accountrestartmembership",
            "finishsignupbutton",
            
            # Chuỗi text phổ biến
            "updatepayment",
            "paymentupdate",
            "cậpnhậtphươngthứcthanhtoán",
            "restartmembership",
            "khôiphụctưcáchthànhviên",
            "finishsignup"
        ]
        
        for kw in bad_keywords_clean:
            if kw in html_clean:
                print(f"Cookie dính lỗi thanh toán ({kw}) -> Xóa!")
                return "DIE", None
                
        # Nếu trang Account load thành công và không có từ khóa lỗi -> LIVE
        if response.status_code == 200:
            import re
            plan = "Standard" # Mặc định để tránh phát nhầm Premium
            
            # Kỹ thuật Proximity Regex: Tìm từ khóa gói cước nằm trong bán kính 50 ký tự sau các neo kỹ thuật
            # Cực kỳ mạnh mẽ: xuyên thủng cả thẻ HTML, khoảng trắng, và HTML Entity (&quot;)
            patterns = [
                r'plan-label.{0,50}?(premium|ultra|standard|basic|cơ bản)',
                r'planname.{0,50}?(premium|ultra|standard|basic|cơ bản)',
                r'plan_tier.{0,50}?(premium|ultra|standard|basic|cơ bản)',
                r'currentplan.{0,50}?(premium|ultra|standard|basic|cơ bản)'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, html_text, flags=re.DOTALL)
                if match:
                    extracted = match.group(1).lower()
                    if 'premium' in extracted or 'ultra' in extracted:
                        plan = "Premium"
                        break
                    elif 'standard' in extracted:
                        plan = "Standard"
                        break
                    elif 'basic' in extracted or 'cơ bản' in extracted:
                        plan = "Basic"
                        break
            
            return "LIVE", plan
            
        return "ERROR", None
            
    except Exception as e:
        print(f"Lỗi khi kiểm tra cookie: {e}")
        return "ERROR", None

