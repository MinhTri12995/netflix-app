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

class TokenResponseError(ProxyError):
    """Unverified upstream response; does not prove an account is unusable."""
    def __init__(self, status_code, shape):
        self.status_code = status_code
        self.shape = shape
        super().__init__(f"Token response unverified (HTTP {status_code}; shape={shape})")

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
            print(f"[Proxy] Connection error ({type(e).__name__}). Fallback to direct connection...")
            proxies_list.mark_proxy_failed(type(e).__name__)
            response = None

    # 2. Tu dong ket noi truc tiep (Direct) neu Proxy bi loi hoac khong co proxy
    if response is None:
        try:
            response = requests.get(
                url, params=params, headers=headers,
                proxies=None, timeout=7, verify=True
            )
        except requests.exceptions.RequestException as e:
            print(f"Network error connecting to Netflix: {type(e).__name__}")
            raise ProxyError(f"Cannot connect to Netflix ({type(e).__name__})") from None

    if response.status_code in [403, 429]:
        raise ProxyError("IP bị Netflix giới hạn tạm thời (403/429)")

    if response.status_code >= 500:
        raise ProxyError(f"Netflix Server Error ({response.status_code})")

    if response.status_code == 404:
        raise ProxyError("Netflix API endpoint returned 404 (Endpoint route changed / temporary outage)")

    if response.status_code == 401:
        raise CookieError(f"Cookie invalid or unauthorized (HTTP {response.status_code})")

    if not 200 <= response.status_code < 300:
        raise ProxyError(f"Netflix API HTTP {response.status_code}")
    try:
        data = response.json()
    except ValueError:
        raise TokenResponseError(response.status_code, "non_json") from None

    # Inspect only the supported envelope; diagnostics never include response values.
    token_data = data
    for field in ('value', 'account', 'token', 'default'):
        if not isinstance(token_data, dict) or field not in token_data:
            raise TokenResponseError(response.status_code, f"missing_{field}")
        token_data = token_data[field]
    if isinstance(token_data, dict):
        token_data = token_data.get('token')
    if not isinstance(token_data, str):
        raise TokenResponseError(response.status_code, "invalid_token_type")
    token = token_data.strip()
    if (not token or any(c.isspace() for c in token)
            or token.lower().startswith(('http:', 'https:', 'fallback:'))
            or token.lower().rstrip('/') in ('netflix.com', 'www.netflix.com')):
        raise TokenResponseError(response.status_code, "invalid_token_value")
    return token

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
