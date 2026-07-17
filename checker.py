import requests
import time
import proxies_list

def check_account_live(netflix_id, secure_netflix_id="", check_payment=False):
    """
    Kiểm tra cookie Netflix có còn sống không.
    Trả về LIVE nếu sống, DIE nếu chết. 
    Nếu check_payment=True, sẽ báo DIE nếu dính lỗi Update Payment.
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
        
        # Nếu bị ném ra trang login hoặc trang lỗi cookie (tức là cookie thực sự đã chết/bị logout)
        url_lower = response.url.lower()
        if "netflix.com/login" in url_lower or "/clearcookies" in url_lower:
            return "DIE", None
            
        html_text = response.text.lower()
        
        # Nếu yêu cầu check Update Payment (Lỗi thanh toán đa ngôn ngữ)
        if check_payment:
            if "paymentupdate" in url_lower or "payment-update" in url_lower or "billing-update" in url_lower:
                return "DIE", None
                
            on_hold_kws = [
                'on hold', 'payment issue', 'update your payment', 'please update your',
                'tạm ngưng', 'lỗi thanh toán', 'cập nhật thanh toán',
                'en pausa', 'actualice su pago', 'actualizar el pago',
                'suspensa', 'atualize seu pagamento',
                'en attente', 'mettre à jour le paiement',
                'приостановлена', 'проблема с оплатой',
                'askıya', 'ödeme sorunu', 'ödeme yönteminizi',
                'ditangguhkan', 'perbarui pembayaran',
                'معلق', 'تحديث الدفع',
                'ausgesetzt', 'zahlungsinformationen',
                '保留中', 'お支払い方法',
                '보류', '결제 수단',
                '已暂停', '更新付款方式'
            ]
            
            error_classes = ['payment-warning', 'account-restricted', 'update-payment-container']
            
            for kw in on_hold_kws:
                if kw in html_text:
                    return "DIE", None
            for cls in error_classes:
                if cls in html_text:
                    return "DIE", None
        
        # Nếu trang Account load thành công -> LIVE
        if response.status_code == 200:
            import re
            plan = "Standard" # Mặc định để tránh phát nhầm Premium
            
            # Kỹ thuật Proximity Regex: Tìm từ khóa gói cước nằm trong bán kính 50 ký tự sau các neo kỹ thuật
            # Hỗ trợ nhận diện "Premium" từ tất cả các ngôn ngữ phổ biến trên thế giới
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

