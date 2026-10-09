import requests
import time
import json
import re
from urllib.parse import urlsplit
from html.parser import HTMLParser
from datetime import datetime
import proxies_list

NETFLIX_API_URL = "https://ios.prod.ftl.netflix.com/nq/mobile/nqios/~15.48.0/user"

# Global flag: once we know API is dead, skip it entirely to save time
_api_is_dead = False

PAYMENT_URL_KEYWORDS = [
    "/simplemember/editpayment",
    "/simplemember/managepayment",
    "/simplemember/paymenthold",
    "/paymentupdate",
    "/payment-update",
    "/billing-update",
    "/membership-paused",
]

PAYMENT_FLAG_PATTERNS = [
    re.compile(r'ispaymentfailure"\s*:\s*true', re.IGNORECASE),
    re.compile(r'warnuserofpaymentfailure"\s*:\s*true', re.IGNORECASE),
    re.compile(r'haspausedmembership"\s*:\s*true', re.IGNORECASE),
    re.compile(r'membershipstatus"\s*:\s*"(?:rejoin|former_member|never_member|hold|canceled|cancelled|anonymous)"', re.IGNORECASE),
    re.compile(r'ismembershipactive"\s*:\s*false', re.IGNORECASE),
]

PAYMENT_DIE_KEYWORDS = [
    # English Error Banners & Alerts (only appear when account is blocked/paused)
    "your account is on hold", "membership is on hold", "account is on hold", "account on hold",
    "membership is paused", "membership paused", "your membership is paused",
    "we were unable to process your payment", "unable to process your payment",
    "payment was declined", "card was declined",
    "restart your membership", "reactivate your membership",

    # Vietnamese (Tiếng Việt) - Các câu cảnh báo lỗi/tạm dừng thực tế
    "tài khoản của bạn bị tạm hoãn", "tài khoản bị tạm hoãn",
    "tài khoản của bạn bị tạm dừng", "tài khoản bị tạm dừng",
    "tư cách thành viên bị tạm dừng", "không thể xử lý khoản thanh toán",
    "khởi động lại tư cách thành viên", "tài khoản của bạn bị tạm giữ",

    # Spanish (Tây Ban Nha)
    "tu cuenta está en pausa", "membresía en pausa", "cuenta en pausa",
    "no pudimos procesar tu pago", "cuenta suspendida", "reiniciar membresía", "reiniciar tu membresía",
    "reactivar tu suscripción",

    # Portuguese (Bồ Đào Nha)
    "sua assinatura está pausada", "assinatura pausada", "não foi possível processar seu pagamento",
    "suspensão de sua conta", "conta suspensa", "reiniciar assinatura", "reiniciar sua assinatura",

    # Polish (Ba Lan)
    "twoje członkostwo zostało wstrzymane", "członkostwo wstrzymane",
    "nie mogliśmy zrealizować płatności", "wznów członkostwo",

    # Turkish, French, German, Italian
    "üyeliğiniz askıya alındı", "ödemenizi işleme koyamadık", "üyeliğinizi yeniden başlatın",
    "votre abonnement est suspendu", "suspension de votre compte", "nous n'avons pas pu traiter votre paiement", "réactiver votre abonnement",
    "ihre mitgliedschaft pausiert", "ihr konto ist gesperrt", "wir konnten ihre zahlung nicht verarbeiten", "mitgliedschaft reaktivieren",
    "il tuo abbonamento è in pausa", "non siamo riusciti a elaborare il pagamento", "riattiva abbonamento",
    "reaktivera ditt medlemskap"
]


def visible_account_text(html):
    """Ignore bundled translations and scripts when matching payment banners."""
    class VisibleText(HTMLParser):
        def __init__(self):
            super().__init__(); self.hidden = 0; self.parts = []
        def handle_starttag(self, tag, attrs):
            if tag in ('script','style'):
                self.hidden += 1
        def handle_endtag(self, tag):
            if tag in ('script','style'):
                self.hidden = max(0,self.hidden-1)
        def handle_data(self, data):
            if not self.hidden:
                self.parts.append(data)
    parser = VisibleText()
    parser.feed(html)
    return ' '.join(parser.parts).lower()

def normalize_plan_name(raw_plan_name, fallback_text=""):
    from app.services.plan_parser import normalize_plan
    return normalize_plan(raw_plan_name)

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
            verify=True
        )
        if response.status_code in [403, 429] or response.status_code >= 500:
            return "ERROR", None
        if not response.ok:
            return "ERROR", None

        url_lower = response.url.lower()
        html = response.text or ""
        if not html.strip():
            return "ERROR", None
        text_lower = html.lower()

        # 0. Kiểm tra trang lạ / ISP block / Captive portal
        target = urlsplit(response.url)
        host = (target.hostname or '').lower()
        if target.scheme != 'https' or not (host == 'netflix.com' or host.endswith('.netflix.com')):
            return "ERROR", None

        # 1. Chuyển hướng về Login, ClearCookies, hoặc Signup -> DIE (Cookie hết hạn)
        if "netflix.com/login" in url_lower or "/clearcookies" in url_lower or "/signup" in url_lower:
            return "DIE", None

        # 2. URL chứa trang cập nhật thanh toán -> DIE (Lỗi Payment)
        if any(kw in url_lower for kw in PAYMENT_URL_KEYWORDS):
            return "DIE", None

        # 3. Flags thanh toán / cấu trúc cờ nợ cước -> DIE
        if any(p.search(html) for p in PAYMENT_FLAG_PATTERNS):
            return "DIE", None

        # 4. Nội dung HTML chứa thông báo lỗi thanh toán / tạm hoãn / hết hạn -> DIE
        if any(kw in visible_account_text(html) for kw in PAYMENT_DIE_KEYWORDS):
            return "DIE", None

        # 5. Kiểm tra ngày hết hạn
        date_m = re.search(r'nextBillingDate"\s*:\s*\{"fieldType":"String","value":"([^"]+)"\}', html)
        if date_m:
            expire_date = date_m.group(1).replace(r'\x20', ' ').strip()

        # Xác nhận có dấu hiệu trang Account thực sự của Netflix
        has_account_markers = (
            "nextbillingdate" in text_lower or
            "membershipstatus" in text_lower or
            "localizedplanname" in text_lower or
            "planname" in text_lower or
            "membership" in text_lower or
            "plan:" in text_lower
        )
        if not has_account_markers:
            return "ERROR", None

        # 6. Kiểm tra gói cước nếu còn sống (LIVE)
        from app.services.plan_parser import html_plan
        final_plan = html_plan(html)
        return "LIVE", final_plan

    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.ProxyError):
        return "ERROR", None
    except Exception as e:
        print(f"Web Check Error ({type(e).__name__})")
        return "ERROR", None

def _is_dict_dead(obj):
    """Đệ quy kiểm tra cấu trúc JSON từ Netflix để phát hiện lỗi nợ cước / hủy thành viên."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            if kl == "ispaymentfailure" and v is True:
                return True
            if kl == "warnuserofpaymentfailure" and v is True:
                return True
            if kl == "haspausedmembership" and v is True:
                return True
            if kl == "ismembershipactive" and v is False:
                return True
            if kl == "membershipstatus" and str(v).lower() in ["former_member", "never_member", "rejoin", "anonymous", "hold", "canceled", "cancelled"]:
                return True
            if isinstance(v, (dict, list)):
                if _is_dict_dead(v):
                    return True
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                if _is_dict_dead(item):
                    return True
    return False

def check_account_live(netflix_id, secure_netflix_id="", check_payment=True):
    """
    Kiem tra toan dien ca Token API va Web HTML.
    Tra ve (status, plan) trong do status la 1 trong 3 trang thai: 'LIVE', 'DIE', 'UNKNOWN'.
    Tuyet doi khong gan 'LIVE' khi gap loi mang/timeout/proxy/5xx.
    """
    cookies = {"NetflixId": netflix_id}
    if secure_netflix_id:
        cookies["SecureNetflixId"] = secure_netflix_id

    proxy_dict = proxies_list.get_random_proxy()

    # 1. Kiem tra kha nang tao Token dang nhap truc tiep
    plan_api = _get_token_and_plan_api(netflix_id, secure_netflix_id, proxy_dict)

    # Retry voi ket noi truc tiep (Direct) neu proxy bi loi
    if plan_api == "ERROR":
        plan_api = _get_token_and_plan_api(netflix_id, secure_netflix_id, None)

    if plan_api is None:
        return "DIE", None
    elif plan_api == "API_DEAD":
        web_status, web_plan = check_web_account_status_and_plan(cookies, proxy_dict)
        if web_status == "ERROR":
            web_status, web_plan = check_web_account_status_and_plan(cookies, None)
        if web_status == "ERROR":
            return "UNKNOWN", None
        return web_status, web_plan
    elif plan_api == "ERROR":
        web_status, web_plan = check_web_account_status_and_plan(cookies, proxy_dict)
        if web_status == "ERROR":
            web_status, web_plan = check_web_account_status_and_plan(cookies, None)
        if web_status == "DIE":
            return "DIE", None
        elif web_status == "LIVE":
            return "LIVE", web_plan
        else:
            return "UNKNOWN", None

    # 2. Kiem tra trang Web YourAccount de tranh loi Payment Hold
    if check_payment:
        web_status, web_plan = check_web_account_status_and_plan(cookies, proxy_dict)
        if web_status == "ERROR":
            web_status, web_plan = check_web_account_status_and_plan(cookies, None)

        if web_status == "DIE":
            return "DIE", None
        elif web_status == "LIVE":
            final_plan = web_plan if web_plan else (plan_api if plan_api != "VALID" else None)
            return "LIVE", final_plan
        elif web_status == "ERROR":
            # Khi web check YourAccount gặp lỗi 500/403/timeout -> UNKNOWN, không tự động đoán LIVE/Premium!
            return "UNKNOWN", None

    final_plan = plan_api if plan_api != "VALID" else None
    return "LIVE", final_plan


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
            verify=True
        )
        if response.status_code == 404:
            return "API_DEAD"
        if response.status_code in [403, 429] or response.status_code >= 500:
            return "ERROR"
        if not response.ok:
            return "ERROR"
        try:
            data = response.json()
        except Exception:
            return "ERROR"

        # 1. Kiem tra cau truc dict truc tiep
        if _is_dict_dead(data):
            return None

        token_data = ((((data.get("value") or {}).get("account") or {}).get("token") or {}).get("default") or {})
        if isinstance(token_data, dict):
            token = token_data.get("token")
        elif isinstance(token_data, str):
            token = token_data
        else:
            token = None
            
        if not token:
            return "ERROR"

        from app.services.plan_parser import current_plan
        return current_plan(data) or "VALID"
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.ProxyError):
        return "ERROR"
    except Exception as e:
        print(f"Token API error ({type(e).__name__})")
        return "ERROR"
