import requests
import time

def check_account_live(netflix_id, secure_netflix_id=""):
    """
    Kiểm tra cookie Netflix có còn sống không.
    Trả về True nếu LIVE, False nếu DIE.
    """
    url = "https://www.netflix.com/YourAccount"
    
    cookies = {
        "NetflixId": netflix_id
    }
    if secure_netflix_id:
        cookies["SecureNetflixId"] = secure_netflix_id
        
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"
    }

    try:
        # Tạm nghỉ 1s tránh bị lock IP
        time.sleep(1)
        
        # Đặt allow_redirects=False để bắt các lệnh chuyển hướng
        response = requests.get(url, cookies=cookies, headers=headers, allow_redirects=False, timeout=10)
        
        # Nếu mã trả về là 200 OK -> Trang Account load thành công -> LIVE
        if response.status_code == 200:
            return "LIVE"
        # Nếu bị redirect (302, 301) thường là do bắt đăng nhập lại -> DIE
        elif response.status_code in [301, 302]:
            return "DIE"
        # Mã lỗi 403, 429, v.v.. do Netflix chặn IP VPN -> ERROR (không xóa)
        else:
            print(f"Bị chặn bởi Netflix (Status {response.status_code})")
            return "ERROR"
            
    except Exception as e:
        print(f"Lỗi khi kiểm tra cookie: {e}")
        # Lỗi mạng, VPN đứt... -> ERROR
        return "ERROR"
