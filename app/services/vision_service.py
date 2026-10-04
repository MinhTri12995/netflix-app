import re
import requests
import proxies_list

def extract_card_info_from_netflix_html(html_text):
    if not html_text:
        return []
    card_info = []

    # 1. mopType span (e.g. •••• 8357 or 62-857••••8357 or &bull;&bull;&bull;&bull; 2158)
    m = re.search(r'data-uia="mopType">([^<]+)</span>', html_text)
    if m:
        raw = m.group(1).replace('&bull;', '•').strip()
        digits = re.findall(r'\d+', raw)
        card_info.append({
            "source": "mopType",
            "raw": raw,
            "all_digits": "".join(digits),
            "last4": digits[-1] if digits and len(digits[-1]) >= 4 else (digits[-1] if digits else None)
        })

    # 2. growthPaymentMethods displayText
    m_growth = re.findall(r'"growthPaymentMethods":\s*\[\s*\{[^}]*"displayText":\s*"([^"]+)"', html_text)
    for g in m_growth:
        digits = re.findall(r'\d+', g)
        card_info.append({
            "source": "growthPaymentMethods",
            "raw": g,
            "all_digits": "".join(digits),
            "last4": digits[-1] if digits and len(digits[-1]) >= 4 else (digits[-1] if digits else None)
        })

    # 3. displayText fieldType
    m_field = re.findall(r'"displayText"\s*:\s*\{"fieldType":"String","value":"([^"]+)"\}', html_text)
    for f in m_field:
        digits = re.findall(r'\d+', f)
        card_info.append({
            "source": "fieldType_displayText",
            "raw": f,
            "all_digits": "".join(digits),
            "last4": digits[-1] if digits and len(digits[-1]) >= 4 else (digits[-1] if digits else None)
        })

    return card_info

def scrape_netflix_account_payment_card(netflix_id, secure_netflix_id=""):
    if not netflix_id:
        return []
    cookies = {"NetflixId": netflix_id}
    if secure_netflix_id:
        cookies["SecureNetflixId"] = secure_netflix_id

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    proxy_dict = proxies_list.get_random_proxy()
    html_text = ""
    for attempt in range(2):
        try:
            curr_proxy = proxy_dict if attempt == 0 else None
            r = requests.get(
                "https://www.netflix.com/YourAccount",
                cookies=cookies,
                headers=headers,
                proxies=curr_proxy,
                timeout=12,
                allow_redirects=True,
                verify=True
            )
            if "/login" in r.url or "/clearcookies" in r.url:
                print(f"[Card Scraper] Account redirected to login/clearcookies: {r.url}")
                return []
            html_text = r.text
            break
        except Exception as e:
            print(f"[Card Scraper] Attempt {attempt} error: {e}")
            if attempt == 0:
                proxy_dict = proxies_list.get_random_proxy()

    return extract_card_info_from_netflix_html(html_text)

def verify_payment_card_match(buyer_card_last4, buyer_card_digits, scraped_cards):
    """
    Xác minh xem thông tin thẻ trong ảnh khiếu nại của người mua có khớp với thẻ trong tài khoản Netflix hay không.
    Trả về (is_match, reason)
    """
    if not scraped_cards:
        return True, "SCRAPE_UNAVAILABLE"

    scraped_last4_set = set()
    scraped_all_digits = set()
    for c in scraped_cards:
        if c.get("last4"):
            scraped_last4_set.add(c["last4"])
        if c.get("all_digits"):
            scraped_all_digits.add(c["all_digits"])

    if not buyer_card_last4 and not buyer_card_digits:
        return True, "NO_CARD_IN_SCREENSHOT"

    clean_buyer_last4 = str(buyer_card_last4).strip() if buyer_card_last4 else ""
    clean_buyer_digits = "".join(re.findall(r'\d+', str(buyer_card_digits))) if buyer_card_digits else ""

    # Kiểm tra khớp trực tiếp 4 số cuối
    if clean_buyer_last4 and clean_buyer_last4 in scraped_last4_set:
        return True, f"MATCH_LAST4_{clean_buyer_last4}"

    # Kiểm tra chuỗi con các chữ số
    for s_dig in scraped_all_digits:
        if clean_buyer_last4 and clean_buyer_last4 in s_dig:
            return True, f"MATCH_LAST4_IN_DIGITS_{clean_buyer_last4}"
        if clean_buyer_digits and (clean_buyer_digits in s_dig or s_dig in clean_buyer_digits):
            return True, "MATCH_DIGITS_SUBSTRING"

    return False, f"MISMATCH_BUYER_{clean_buyer_last4}_VS_SCRAPED_{list(scraped_last4_set)}"
