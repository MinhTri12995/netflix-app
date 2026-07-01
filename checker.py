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
        
        # Nếu bị ném ra trang login
        if "netflix.com/login" in response.url:
            return "DIE"
            
        html_text = response.text.lower()
        
        # Nhận diện lỗi bằng các mã kỹ thuật (KHÔNG phụ thuộc vào ngôn ngữ)
        # Các mã này (data-uia hoặc biến React) giống nhau trên toàn cầu dù là tiếng Anh, Tây Ban Nha hay Ả Rập
        bad_keywords = [
            "update payment",
            "restart membership",
            "cập nhật phương thức thanh toán",
            "khôi phục tư cách thành viên",
            "action_update_payment",         # Nút Update Payment (Global)
            "account-restart-membership",    # Nút Restart Membership (Global)
            '"membershipstatus":"past_due"', # Biến hệ thống báo trễ hạn (Global)
            '"membershipstatus":"former_member"', # Biến hệ thống báo đã hủy (Global)
            "payment-update",
            "finish sign-up",
            "finish_sign_up"                 # Nút Finish Sign Up (Global)
        ]
        
        for kw in bad_keywords:
            if kw in html_text:
                print(f"Cookie dính lỗi thanh toán ({kw}) -> Xóa!")
                return "DIE"
                
        # Nếu trang Account load thành công và không có từ khóa lỗi -> LIVE
        if response.status_code == 200:
            return "LIVE"
            
        return "ERROR"
            
    except Exception as e:
        print(f"Lỗi khi kiểm tra cookie: {e}")
        return "ERROR"

