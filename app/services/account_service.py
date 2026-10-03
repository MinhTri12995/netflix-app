import re
import urllib.parse
from datetime import datetime
import requests
import database
import checker
import proxies_list
from app.services.token_service import (
    fetch_netflix_nftoken_api,
    generate_json_cookie_token,
    ProxyError,
    CookieError
)

def is_date_expired(date_str):
    if not date_str or str(date_str).strip() in ['N/A', 'None', '', 'null']:
        return False

    clean_str = str(date_str).strip()

    # 1. ISO format YYYY-MM-DD
    iso_match = re.search(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', clean_str)
    if iso_match:
        try:
            dt = datetime(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))
            return dt.date() < datetime.now().date()
        except Exception:
            pass

    # 2. DMY format DD-MM-YYYY
    dmy_match = re.search(r'(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})', clean_str)
    if dmy_match:
        try:
            dt = datetime(int(dmy_match.group(3)), int(dmy_match.group(2)), int(dmy_match.group(1)))
            return dt.date() < datetime.now().date()
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

    if not year:
        year = datetime.now().year

    if month and day:
        try:
            dt = datetime(year, month, day)
            return dt.date() < datetime.now().date()
        except Exception:
            pass

    return False

def fetch_realtime_account_info(netflix_id, secure_netflix_id=""):
    cookies = {"NetflixId": netflix_id}
    if secure_netflix_id:
        cookies["SecureNetflixId"] = secure_netflix_id
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"
    }

    last_network_err = None
    for attempt in range(2):
        proxy_dict = proxies_list.get_random_proxy()
        try:
            r = requests.get(
                "https://www.netflix.com/YourAccount",
                cookies=cookies,
                headers=headers,
                proxies=proxy_dict,
                timeout=12,
                allow_redirects=True,
                verify=False
            )
            url_lower = r.url.lower()
            html = r.text
            text_lower = html.lower()

            if "netflix.com/login" in url_lower or "/clearcookies" in url_lower or "signup" in url_lower:
                raise CookieError("Cookie session expired or invalid (Redirected to login)")

            payment_urls = getattr(checker, 'PAYMENT_URL_KEYWORDS', [
                "paymentupdate", "payment-update", "billing-update", "simplemember",
                "editpayment", "managepayment", "paymenthold", "membership-paused",
                "updatepayment", "youraccountpayment"
            ])
            if any(kw in url_lower for kw in payment_urls):
                raise CookieError("Account requires Payment Update (Payment Hold URL detected)")

            die_kws = getattr(checker, 'PAYMENT_DIE_KEYWORDS', [])
            if any(kw in text_lower for kw in die_kws):
                raise CookieError("Account requires Payment Update (Payment Hold text detected)")

            expire_date = None
            date_m = re.search(r'nextBillingDate"\s*:\s*\{"fieldType":"String","value":"([^"]+)"\}', html)
            if date_m:
                expire_date = date_m.group(1).replace(r'\x20', ' ').strip()
                if is_date_expired(expire_date):
                    raise CookieError(f"Account next billing date ({expire_date}) has expired.")

            plan_raw = None
            plan_m = re.search(r'(?:localizedPlanName|planName)"\s*:\s*\{"fieldType":"String","value":"([^"]+)"\}', html)
            if plan_m:
                plan_raw = plan_m.group(1).replace(r'\x20', ' ').strip()
                import codecs
                try:
                    plan_raw = codecs.decode(plan_raw, 'unicode_escape')
                except Exception:
                    pass

            plan = checker.normalize_plan_name(plan_raw, text_lower) or "Premium"
            return plan, expire_date

        except CookieError:
            raise
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.ProxyError) as e:
            last_network_err = e
            continue
        except Exception as e:
            raise CookieError(f"Error checking account status: {e}")

    raise ProxyError(f"Network / Proxy error connecting to Netflix Account page: {last_network_err}")
