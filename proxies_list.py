import os
import random
import time
import requests

WEBSHARE_API_KEY = os.environ.get("WEBSHARE_API_KEY", "g181iqc71hmr2r84ztbds6iebvn0n89yv0qlok2v")
WEBSHARE_USERNAME = os.environ.get("WEBSHARE_USERNAME", "qfcfflym")
WEBSHARE_PASSWORD = os.environ.get("WEBSHARE_PASSWORD", "bnfu8ype49yu")

# Webshare Rotating Backbone Gateway (Auto rotates IP on each request)
ROTATING_GATEWAY = f"http://{WEBSHARE_USERNAME}-rotate:{WEBSHARE_PASSWORD}@p.webshare.io:80"

# Danh sách 20 Proxy Webshare US Active mới (Chỉ lấy IP Mỹ)
STATIC_PROXIES = [
    f"http://{WEBSHARE_USERNAME}:{WEBSHARE_PASSWORD}@104.233.12.92:6643/",
    f"http://{WEBSHARE_USERNAME}:{WEBSHARE_PASSWORD}@142.111.44.190:5902/",
    f"http://{WEBSHARE_USERNAME}:{WEBSHARE_PASSWORD}@23.236.196.234:6324/",
    f"http://{WEBSHARE_USERNAME}:{WEBSHARE_PASSWORD}@82.27.240.155:6963/",
    f"http://{WEBSHARE_USERNAME}:{WEBSHARE_PASSWORD}@104.239.104.170:6394/",
    f"http://{WEBSHARE_USERNAME}:{WEBSHARE_PASSWORD}@173.244.41.151:6335/",
    f"http://{WEBSHARE_USERNAME}:{WEBSHARE_PASSWORD}@154.12.142.91:6260/",
    f"http://{WEBSHARE_USERNAME}:{WEBSHARE_PASSWORD}@107.173.150.99:6553/",
    f"http://{WEBSHARE_USERNAME}:{WEBSHARE_PASSWORD}@206.206.119.102:6013/",
    f"http://{WEBSHARE_USERNAME}:{WEBSHARE_PASSWORD}@154.6.87.75:6545/",
    f"http://{WEBSHARE_USERNAME}:{WEBSHARE_PASSWORD}@107.173.132.249:7203/",
    f"http://{WEBSHARE_USERNAME}:{WEBSHARE_PASSWORD}@152.232.15.121:8289/",
    f"http://{WEBSHARE_USERNAME}:{WEBSHARE_PASSWORD}@136.0.120.132:6150/",
    f"http://{WEBSHARE_USERNAME}:{WEBSHARE_PASSWORD}@46.202.78.210:8472/",
    f"http://{WEBSHARE_USERNAME}:{WEBSHARE_PASSWORD}@23.26.68.58:6041/",
    f"http://{WEBSHARE_USERNAME}:{WEBSHARE_PASSWORD}@166.88.169.159:6766/",
    f"http://{WEBSHARE_USERNAME}:{WEBSHARE_PASSWORD}@152.232.15.194:8362/",
    f"http://{WEBSHARE_USERNAME}:{WEBSHARE_PASSWORD}@82.108.66.185:5824/",
    f"http://{WEBSHARE_USERNAME}:{WEBSHARE_PASSWORD}@23.95.150.140:6109/",
    f"http://{WEBSHARE_USERNAME}:{WEBSHARE_PASSWORD}@38.154.205.35:5303/"
]

PROXIES = list(STATIC_PROXIES)
ROTATING_PROXIES = [ROTATING_GATEWAY] + list(STATIC_PROXIES)
_last_fetch_time = 0
CACHE_TTL = 3600 # 1 hour

def fetch_latest_webshare_proxies(api_key=None):
    global PROXIES, ROTATING_PROXIES, _last_fetch_time
    token = api_key or os.environ.get("WEBSHARE_API_KEY", WEBSHARE_API_KEY)
    if not token:
        return PROXIES

    try:
        headers = {"Authorization": f"Token {token}"}
        url = "https://proxy.webshare.io/api/v2/proxy/list/?mode=direct&page=1&page_size=100&countries=US"
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            new_list = []
            for p in data.get("results", []):
                # Chỉ lấy proxy có country_code là US và còn valid
                if p.get("country_code") == "US" and p.get("valid", True):
                    u = p.get("username", WEBSHARE_USERNAME)
                    pw = p.get("password", WEBSHARE_PASSWORD)
                    ip = p.get("proxy_address")
                    port = p.get("port")
                    new_list.append(f"http://{u}:{pw}@{ip}:{port}/")
            if new_list:
                PROXIES = new_list
                ROTATING_PROXIES = [ROTATING_GATEWAY] + new_list
                _last_fetch_time = time.time()
                print(f"[Webshare] Successfully synchronized {len(new_list)} active US proxies!")
                return PROXIES
    except Exception as e:
        print(f"[Webshare] Auto-fetch error: {e}, using static backup US proxies.")
    return PROXIES

USE_DIRECT_RENDER = False

def get_random_proxy():
    global _last_fetch_time
    if USE_DIRECT_RENDER:
        return None
        
    # Check if custom single PROXY_URL is set in env
    env_proxy = os.environ.get("PROXY_URL")
    if env_proxy:
        return {"http": env_proxy, "https": env_proxy}

    # Auto refresh every 1 hour
    if time.time() - _last_fetch_time > CACHE_TTL:
        try:
            fetch_latest_webshare_proxies()
        except Exception:
            pass

    proxy_list = PROXIES if PROXIES else STATIC_PROXIES
    if not proxy_list:
        return {"http": ROTATING_GATEWAY, "https": ROTATING_GATEWAY}
        
    proxy_url = random.choice(proxy_list)
    return {
        "http": proxy_url,
        "https": proxy_url
    }

def get_rotating_gateway():
    return {
        "http": ROTATING_GATEWAY,
        "https": ROTATING_GATEWAY
    }

