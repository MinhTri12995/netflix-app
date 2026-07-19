import requests
import time
import re
import proxies_list

def check_account_live(netflix_id, secure_netflix_id="", check_payment=False):
    """
    Kiểm tra cookie Netflix có còn sống không.
    Luôn vào /YourAccount để vừa check payment vừa lấy gói cước trong 1 request duy nhất.
    
    Logic:
    - Redirect đến login/clearcookies -> DIE (cookie chết)
    - Redirect đến paymentupdate/billing -> DIE (lỗi thanh toán)
    - Trang load OK nhưng KHÔNG tìm được gói cước -> DIE (acc bị lỗi payment ẩn)
    - Trang load OK VÀ tìm được gói cước -> LIVE
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
        "Accept-Encoding": "gzip, deflate"
    }

    proxy_dict = proxies_list.get_random_proxy()

    try:
        time.sleep(1)
        response = requests.get(
            url, 
            cookies=cookies, 
            headers=headers, 
            proxies=proxy_dict,
            allow_redirects=True,
            timeout=15
        )
        
        url_lower = response.url.lower()
        
        # 1. Cookie chết hẳn -> bị đá ra trang login
        if "netflix.com/login" in url_lower or "/clearcookies" in url_lower:
            return "DIE", None
        
        # 2. Bị redirect đến trang cập nhật thanh toán -> chắc chắn lỗi payment
        if "paymentupdate" in url_lower or "payment-update" in url_lower or "billing-update" in url_lower:
            return "DIE", None
            
        # 3. Trang load thành công -> phân tích HTML
        if response.status_code == 200:
            html_text = response.text.lower()
            
            # Bóc tách gói cước bằng Proximity Regex đa ngôn ngữ
            plan = detect_plan(html_text)
            
            if check_payment:
                # Nếu KHÔNG tìm được gói cước nào trên trang Account
                # -> Trang đang hiển thị lỗi payment thay vì thông tin tài khoản bình thường
                if not plan:
                    return "DIE", None
            
            return "LIVE", plan
            
        return "ERROR", None
            
    except Exception as e:
        print(f"Lỗi khi kiểm tra cookie: {e}")
        return "ERROR", None


def detect_plan(html_text):
    """
    Phát hiện gói cước Netflix từ HTML của trang /YourAccount.
    Trả về tên gói cước nếu tìm thấy, None nếu không.
    """
    premium_kws = ['premium', 'ultra', 'премиум', 'özel', 'ozel', 'cao cấp', 'พรีเมียม', 'مميز', '高級', '高级', 'プレミアム', '프리미엄']
    standard_kws = ['standard', 'tiêu chuẩn', 'стандартный', 'standart', '標準', '标准', 'estándar', 'padrão', 'มาตรฐาน', 'قياسي', 'スタンダード', '스탠다드']
    basic_kws = ['basic', 'cơ bản', 'базовый', 'temel', 'básico', 'พื้นฐาน', 'أساسي', '基本', 'ベーシック', '베이직']
    ads_kws = ['ads', 'adverts', 'anuncios', 'pub', 'werbung', 'pubblicità', 'quảng cáo', 'โฆษณา', '広告', '광고', '廣告', '广告', 'рекламо', 'reklam', 'reklamy']
    
    # Patterns tìm vùng chứa thông tin gói cước trên trang Account
    patterns = [
        r'plan-label(.{0,60})',
        r'planname(.{0,60})',
        r'plan_tier(.{0,60})',
        r'currentplan(.{0,60})'
    ]
    
    def has_any_kw(text, kws):
        for kw in kws:
            if re.match(r'^[a-z]+$', kw):
                if re.search(r'\b' + kw + r'\b', text):
                    return True
            else:
                if kw in text:
                    return True
        return False

    for pattern in patterns:
        match = re.search(pattern, html_text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            extracted = match.group(1).lower()
            if has_any_kw(extracted, premium_kws):
                return "Premium"
            elif has_any_kw(extracted, standard_kws):
                if has_any_kw(extracted, ads_kws):
                    return "Standard_Ads"
                else:
                    return "Standard"
            elif has_any_kw(extracted, basic_kws):
                return "Basic"
    
    return None
