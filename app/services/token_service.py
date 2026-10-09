import time
import json
import urllib.parse
import threading
from collections import defaultdict
import requests
import database
import proxies_list

NETFLIX_API_URL = "https://ios.prod.ftl.netflix.com/iosui/user/15.48"

class ProxyError(Exception): pass
class CookieError(Exception): pass

def generate_json_cookie_token(nid, snid):
    exp_time = int(time.time()) + 86400 * 365
    cookie_data = [
        {
            "domain": ".netflix.com", "expirationDate": exp_time, "hostOnly": False,
            "httpOnly": True, "name": "NetflixId", "path": "/", "sameSite": "no_restriction",
            "secure": True, "session": False, "value": nid
        }
    ]
    if snid:
        cookie_data.append({
            "domain": ".netflix.com", "expirationDate": exp_time, "hostOnly": False,
            "httpOnly": True, "name": "SecureNetflixId", "path": "/", "sameSite": "no_restriction",
            "secure": True, "session": False, "value": snid
        })
    return "FALLBACK:" + urllib.parse.quote(json.dumps(cookie_data))

def fetch_netflix_nftoken_api(netflix_id, secure_netflix_id=""):
    url = "https://ios.prod.ftl.netflix.com/nq/mobile/nqios/~15.48.0/user"
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
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Accept-Language': 'en-US;q=1',
        'Host': 'ios.prod.ftl.netflix.com',
        'User-Agent': 'Argo/15.48.1 (iPhone; iOS 15.8.5; Scale/2.00)',
        'x-netflix.client.appversion': '15.48.1',
        'x-netflix.client.type': 'argo',
        'x-netflix.context.app-version': '15.48.1',
        'x-netflix.context.ui-flavor': 'argo',
        'x-netflix.request.routing': '{"path":"/nq/mobile/nqios/~15.48.0/user","control_tag":"iosui_argo"}',
        'x-netflix.request.routing.original.path': '/nq/mobile/nqios/~15.48.0/user',
        'Cookie': cookie_str
    }

    proxy_dict = proxies_list.get_random_proxy()
    response = None

    # 1. Thử kết nối qua Proxy xoay vòng
    if proxy_dict:
        try:
            response = requests.get(
                url, params=params, headers=headers,
                proxies=proxy_dict, timeout=5.0, verify=True
            )
            # Nếu Proxy lỗi hoặc bị giới hạn (400, 402, 407, 502, 503, 504)
            if response.status_code in [400, 402, 407, 502, 503, 504]:
                print(f"[Proxy] HTTP {response.status_code} (Proxy error/limit). Fallback to direct connection...")
                proxies_list.mark_proxy_failed(f"HTTP {response.status_code}")
                response = None
        except requests.exceptions.RequestException as e:
            print(f"[Proxy] Proxy connection error ({e}). Fallback to direct connection...")
            proxies_list.mark_proxy_failed(str(e))
            response = None

    # 2. Tu dong ket noi truc tiep (Direct) neu Proxy bi loi hoac khong co proxy
    if response is None:
        try:
            response = requests.get(
                url, params=params, headers=headers,
                proxies=None, timeout=7, verify=True
            )
        except requests.exceptions.RequestException as e:
            print(f"Network error connecting to Netflix: {e}")
            raise ProxyError(f"Cannot connect to Netflix: {e}")

    if response.status_code in [403, 429]:
        raise ProxyError("IP bị Netflix giới hạn tạm thời (403/429)")

    if response.status_code >= 500:
        raise ProxyError(f"Netflix Server Error ({response.status_code})")

    if response.status_code == 404:
        raise ProxyError("Netflix API endpoint returned 404 (Endpoint route changed / temporary outage)")

    if response.status_code == 401:
        raise CookieError(f"Cookie invalid or unauthorized (HTTP {response.status_code})")

    try:
        response.raise_for_status()
        data = response.json()
        if 'value' in data and 'account' in data['value'] and 'token' in data['value']['account']:
            token_data = data['value']['account']['token']['default']
            if isinstance(token_data, dict) and 'token' in token_data:
                return token_data['token']
            elif isinstance(token_data, str):
                return token_data

        raise CookieError("Netflix token not found in response - Cookie is likely dead.")
    except (CookieError, ProxyError):
        raise
    except Exception as e:
        raise ProxyError(f"Parse/Network Error: {e}")

# --- Rate limiting logic per code ---
_rate_limit_lock = threading.Lock()
_code_last_request_time = {}
_code_attempts_history = defaultdict(list)
_code_last_live_check = {}

def check_code_rate_limit(code: str):
    now = time.time()
    with _rate_limit_lock:
        _code_attempts_history[code] = [t for t in _code_attempts_history[code] if now - t < 300]
        if len(_code_attempts_history[code]) >= 5:
            return False, "Too many requests for this access code. Please wait 5 minutes before submitting again."
        _code_attempts_history[code].append(now)

        last_req = _code_last_request_time.get(code)
        if last_req and (now - last_req < 120):
            wait_sec = int(120 - (now - last_req))
            return False, f"Please wait {wait_sec} seconds before submitting another request for this code."

    if database.has_recent_request(code, minutes=2):
        return False, "You already submitted a request recently for this code. Please wait 2 minutes before submitting another."

    today_rotations = database.get_today_rotation_count(code)
    if today_rotations >= 5:
        return False, "This access code has reached its maximum replacement limit (5 times per 24 hours). Please contact customer support for further assistance."

    return True, None

def mark_code_request_success(code: str):
    with _rate_limit_lock:
        _code_last_request_time[code] = time.time()

def check_live_rate_limit(code: str):
    now = time.time()
    with _rate_limit_lock:
        last_chk = _code_last_live_check.get(code)
        if last_chk and (now - last_chk < 20):
            wait_sec = int(20 - (now - last_chk))
            return False, f"Please wait {wait_sec} seconds before checking this code again."
        _code_last_live_check[code] = now
    return True, None
