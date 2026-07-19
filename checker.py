import requests
import time
import proxies_list

def check_account_live(netflix_id, secure_netflix_id="", check_payment=False):
    """
    Kiểm tra cookie Netflix có còn sống không.
    Trả về LIVE nếu sống, DIE nếu chết. 
    Nếu check_payment=True, sẽ báo DIE nếu dính lỗi Update Payment.
    """
    if check_payment:
        # Nếu muốn check lỗi thanh toán cực kỳ chính xác: Request vào trang xem phim /browse
        # Nếu acc bị lỗi payment, Netflix sẽ tự động cấm xem và REDIRECT ép về trang /YourAccount
        url = "https://www.netflix.com/browse"
    else:
        # Nếu chỉ lấy thông tin Gói cước, vào thẳng /YourAccount
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
            allow_redirects=True, # QUAN TRỌNG: Bật theo dõi redirect
            timeout=15
        )
        
        url_lower = response.url.lower()
        
        # Nếu cookie chết hẳn, Netflix sẽ đá văng ra trang login hoặc clear cookies
        if "netflix.com/login" in url_lower or "/clearcookies" in url_lower:
            return "DIE", None
            
        if check_payment:
            # Giải pháp TỐI THƯỢNG: Nếu request vào /browse mà lại bị Netflix bếch cổ ném về /YourAccount
            # hoặc trang cập nhật thanh toán -> Chắc chắn 100% account đang bị Hold/Khóa mỏ cày!
            if "youraccount" in url_lower or "paymentupdate" in url_lower or "payment-update" in url_lower or "billing-update" in url_lower:
                return "DIE", None
            
            # Nếu vẫn trụ lại được ở trang /browse hoặc /ManageProfiles -> Account đang LIVE và SẠCH
            # Vì không vào trang YourAccount nên không bóc được tên gói cước, ta trả về None cho plan
            return "LIVE", None
        
        # Nếu KHÔNG check_payment (chỉ lấy gói cước), ta đang ở trang /YourAccount
        if response.status_code == 200:
            html_text = response.text.lower()
            import re
            plan = "Standard" 
            
            premium_kws = ['premium', 'ultra', 'премиум', 'özel', 'ozel', 'cao cấp', 'พรีเมียม', 'مميز', '高級', '高级', 'プレミアム', '프리미엄']
            standard_kws = ['standard', 'tiêu chuẩn', 'стандартный', 'standart', '標準', '标准', 'estándar', 'padrão', 'มาตรฐาน', 'قياسي', 'スタンダード', '스탠다드']
            basic_kws = ['basic', 'cơ bản', 'базовый', 'temel', 'básico', 'พื้นฐาน', 'أساسي', '基本', 'ベーシック', '베이직']
            ads_kws = ['ads', 'adverts', 'anuncios', 'pub', 'werbung', 'pubblicità', 'quảng cáo', 'โฆษณา', '広告', '광고', '廣告', '广告', 'рекламо', 'reklam', 'reklamy']
            
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
                        plan = "Premium"
                        break
                    elif has_any_kw(extracted, standard_kws):
                        if has_any_kw(extracted, ads_kws):
                            plan = "Standard_Ads"
                        else:
                            plan = "Standard"
                        break
                    elif has_any_kw(extracted, basic_kws):
                        plan = "Basic"
                        break
            
            return "LIVE", plan
            
        return "ERROR", None
            
    except Exception as e:
        print(f"Lỗi khi kiểm tra cookie: {e}")
        return "ERROR", None

