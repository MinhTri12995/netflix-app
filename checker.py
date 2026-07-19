import requests
import time
import re
import json
import proxies_list

# Netflix iOS API - dùng chung config với web.py
NETFLIX_API_URL = "https://ios.prod.ftl.netflix.com/iosui/user/15.48"

def check_account_live(netflix_id, secure_netflix_id="", check_payment=False):
    """
    Kiểm tra cookie Netflix bằng chính Netflix iOS API (không parse HTML).
    
    Cách hoạt động:
    - Request API với path ["account","membershipStatus"] để lấy trạng thái membership
    - Request API với path ["account","token","default"] để lấy token + kiểm tra acc sống
    - Nếu membershipStatus chứa dấu hiệu lỗi payment -> DIE
    - Nếu token không có -> DIE
    - Nếu tất cả OK -> LIVE
    """
    
    cookies = {
        "NetflixId": netflix_id
    }
    if secure_netflix_id:
        cookies["SecureNetflixId"] = secure_netflix_id
    
    proxy_dict = proxies_list.get_random_proxy()
    
    # ===== BƯỚC 1: Check trạng thái membership qua API =====
    if check_payment:
        try:
            status_result = _check_membership_status(netflix_id, proxy_dict)
            if status_result == "DIE":
                return "DIE", None
        except Exception as e:
            print(f"Membership status check error: {e}")
            # Nếu API lỗi, fallback sang bước 2
    
    # ===== BƯỚC 2: Check acc sống bằng cách lấy token =====
    try:
        time.sleep(0.5)
        plan = _check_token_and_plan(netflix_id, proxy_dict)
        if plan is None and check_payment:
            # Không lấy được token -> acc chết hoặc bị lỗi
            return "DIE", None
        elif plan is None:
            return "DIE", None
        elif plan == "ERROR":
            return "ERROR", None
        else:
            return "LIVE", plan if plan != "VALID" else None
    except Exception as e:
        print(f"Token check error: {e}")
        return "ERROR", None


def _check_membership_status(netflix_id, proxy_dict):
    """
    Gọi Netflix iOS API để kiểm tra trạng thái membership.
    Trả về "DIE" nếu acc bị lỗi, "LIVE" nếu OK, "UNKNOWN" nếu không xác định.
    """
    params = {
        "appVersion": "15.48.1",
        "config": '{"gamesInTrailersEnabled":"false"}',
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
        "path": '["account","membershipStatus"]',
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
        
        if response.status_code in [403, 429]:
            return "UNKNOWN"
        
        if not response.ok:
            return "UNKNOWN"
        
        data = response.json()
        data_str = json.dumps(data).lower()
        
        # Tìm dấu hiệu lỗi payment/hold trong response
        die_indicators = [
            '"on_hold"', '"canceled"', '"former_member"', '"never_member"',
            '"cancelled"', '"delinquent"', '"pending_cancellation"',
            '"status":"hold"', '"status":"inactive"', '"suspended"'
        ]
        
        for indicator in die_indicators:
            if indicator in data_str:
                print(f"Payment issue detected: found '{indicator}' in API response")
                return "DIE"
        
        return "LIVE"
        
    except Exception as e:
        print(f"Membership API error: {e}")
        return "UNKNOWN"


def _check_token_and_plan(netflix_id, proxy_dict):
    """
    Gọi Netflix iOS API để lấy token.
    Trả về tên gói cước nếu thành công, None nếu acc chết, "ERROR" nếu lỗi mạng.
    """
    params = {
        "appVersion": "15.48.1",
        "config": '{"gamesInTrailersEnabled":"false","isTrailersEvidenceEnabled":"false","cdsMyListSortEnabled":"true","kidsBillboardEnabled":"true","addHorizontalBoxArtToVideoSummariesEnabled":"false","skOverlayTestEnabled":"false","homeFeedTestTVMovieListsEnabled":"false","baselineOnIpadEnabled":"true","trailersVideoIdLoggingFixEnabled":"true","postPlayPreviewsEnabled":"false","bypassContextualAssetsEnabled":"false","roarEnabled":"false","useSeason1AltLabelEnabled":"false","disableCDSSearchPaginationSectionKinds":["searchVideoCarousel"],"cdsSearchHorizontalPaginationEnabled":"true","searchPreQueryGamesEnabled":"true","kidsMyListEnabled":"true","billboardEnabled":"true","useCDSGalleryEnabled":"true","contentWarningEnabled":"true","videosInPopularGamesEnabled":"true","avifFormatEnabled":"false","sharksEnabled":"true"}',
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
        "path": '["account","token","default"]',
        "pathFormat": "graph",
        "pixelDensity": "2.0",
        "progressive": "false",
        "responseFormat": "json",
    }
    
    headers = {
        "User-Agent": "Argo/15.48.1 (iPhone; iOS 15.8.5; Scale/2.00)",
        "Cookie": f"NetflixId={netflix_id}",
        "x-netflix.request.attempt": "1",
        "x-netflix.request.client.user.guid": "A4CS633D7VCBPE2GPK2HL4EKOE",
        "x-netflix.context.profile-guid": "A4CS633D7VCBPE2GPK2HL4EKOE",
        "x-netflix.request.routing": '{"path":"/nq/mobile/nqios/~15.48.0/user","control_tag":"iosui_argo"}',
        "x-netflix.context.app-version": "15.48.1",
        "x-netflix.argo.translated": "true",
        "x-netflix.context.form-factor": "phone",
        "x-netflix.context.sdk-version": "2012.4",
        "x-netflix.client.appversion": "15.48.1",
        "x-netflix.context.max-device-width": "375",
        "x-netflix.tracing.cl.useractionid": "4DC655F2-9C3C-4343-8229-CA1B003C3053",
        "x-netflix.client.type": "argo",
        "x-netflix.client.ftl.esn": "NFAPPL-02-IPHONE8=1-PXA-02026U9VV5O8AUKEAEO8PUJETCGDD4PQRI9DEB3MDLEMD0EACM4CS78LMD334MN3MQ3NMJ8SU9O9MVGS6BJCURM1PH1MUTGDPF4S4200",
        "x-netflix.context.locales": "en-US",
        "x-netflix.context.top-level-uuid": "90AFE39F-ADF1-4D8A-B33E-528730990FE3",
        "x-netflix.client.iosversion": "15.8.5",
        "accept-language": "en-US;q=1",
        "x-netflix.context.os-version": "15.8.5",
        "x-netflix.request.client.context": '{"appState":"foreground"}',
        "x-netflix.context.ui-flavor": "argo",
        "x-netflix.argo.nfnsm": "9",
        "x-netflix.context.pixel-density": "2.0",
        "x-netflix.request.toplevel.uuid": "90AFE39F-ADF1-4D8A-B33E-528730990FE3",
        "x-netflix.request.client.timezoneid": "Asia/Dhaka",
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
        
        if response.status_code in [403, 429]:
            return "ERROR"
        
        if not response.ok:
            return None
        
        data = response.json()
        
        # Kiểm tra toàn bộ response cho dấu hiệu lỗi payment
        data_str = json.dumps(data).lower()
        die_indicators = [
            '"on_hold"', '"canceled"', '"former_member"', '"never_member"',
            '"cancelled"', '"delinquent"', '"status":"hold"', '"status":"inactive"'
        ]
        for indicator in die_indicators:
            if indicator in data_str:
                print(f"Payment issue in token response: found '{indicator}'")
                return None
        
        # Lấy token
        token_data = ((((data.get("value") or {}).get("account") or {}).get("token") or {}).get("default") or {})
        token = token_data.get("token")
        
        if not token:
            return None
        
        # Tìm gói cước trong response
        plan = _detect_plan_from_api(data_str)
        
        return plan if plan else "VALID"
        
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.ProxyError):
        return "ERROR"
    except Exception as e:
        print(f"Token API error: {e}")
        return "ERROR"


def _detect_plan_from_api(data_str):
    """Phát hiện gói cước từ API response JSON string."""
    data_lower = data_str.lower()
    
    if '"premium"' in data_lower or '"ultra"' in data_lower:
        return "Premium"
    elif '"standard with ads"' in data_lower or '"standard_ads"' in data_lower:
        return "Standard_Ads"
    elif '"standard"' in data_lower:
        return "Standard"
    elif '"basic"' in data_lower:
        return "Basic"
    
    return None
