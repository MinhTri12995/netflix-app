import re
import uuid
import json
import urllib.parse

def parse_lines(lines):
    accounts = []
    
    # Handle single string JSON content if passed
    if isinstance(lines, str):
        lines = lines.splitlines()
        
    full_text = "\n".join(lines).strip()
    if full_text.startswith('[') or full_text.startswith('{'):
        try:
            parsed_json = json.loads(full_text)
            # 1. JSON Array of cookies: [{"name": "NetflixId", "value": "..."}, ...]
            if isinstance(parsed_json, list):
                nid, snid = None, ""
                for c in parsed_json:
                    if isinstance(c, dict):
                        if c.get('name') == 'NetflixId':
                            nid = urllib.parse.unquote(str(c.get('value', '')))
                        elif c.get('name') == 'SecureNetflixId':
                            snid = urllib.parse.unquote(str(c.get('value', '')))
                if nid:
                    accounts.append({
                        'email': f"auto_{uuid.uuid4().hex[:8]}@netflix.com",
                        'expire': 'N/A',
                        'plan': 'Premium',
                        'netflix_id': nid,
                        'secure_netflix_id': snid
                    })
                    return accounts
            # 2. JSON Object with 'cookies' array: {"cookies": [...]}
            elif isinstance(parsed_json, dict) and 'cookies' in parsed_json and isinstance(parsed_json['cookies'], list):
                nid, snid = None, ""
                for c in parsed_json['cookies']:
                    if isinstance(c, dict):
                        if c.get('name') == 'NetflixId':
                            nid = urllib.parse.unquote(str(c.get('value', '')))
                        elif c.get('name') == 'SecureNetflixId':
                            snid = urllib.parse.unquote(str(c.get('value', '')))
                if nid:
                    accounts.append({
                        'email': f"auto_{uuid.uuid4().hex[:8]}@netflix.com",
                        'expire': 'N/A',
                        'plan': 'Premium',
                        'netflix_id': nid,
                        'secure_netflix_id': snid
                    })
                    return accounts
        except Exception:
            pass

    current_email = None
    current_expire = None
    current_plan = None
    current_netflix_id = None
    current_secure_netflix_id = ""

    def push_account():
        nonlocal current_email, current_expire, current_plan, current_netflix_id, current_secure_netflix_id
        if current_netflix_id:
            if not current_email:
                # Tạo email giả nếu định dạng không có email
                current_email = f"auto_{uuid.uuid4().hex[:8]}@netflix.com"
            clean_plan = current_plan
            if clean_plan and str(clean_plan).strip().lower() in ['none found', 'none', 'unknown', 'n/a', 'null', '']:
                clean_plan = None
            accounts.append({
                'email': current_email,
                'expire': current_expire,
                'plan': clean_plan,
                'netflix_id': current_netflix_id,
                'secure_netflix_id': current_secure_netflix_id
            })
        current_email = None
        current_expire = None
        current_plan = None
        current_netflix_id = None
        current_secure_netflix_id = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if '|' in line and ('cookies:' in line or 'cookies =' in line):
            email_part = line.split(':')[0] if ':' in line else None
            if email_part and '@' in email_part:
                current_email = email_part.strip()
            
            expire_match_single = re.search(r'(?:Nextbillingdate|nextBillingDate)\s*=\s*([^|]+)', line, re.IGNORECASE)
            if expire_match_single:
                current_expire = expire_match_single.group(1).strip()
                
            plan_match_single = re.search(r'(?:Membership|memberPlan)\s*[=:]\s*([^|]+)', line, re.IGNORECASE)
            if plan_match_single:
                current_plan = plan_match_single.group(1).strip()
                
            cookies_match = re.search(r'cookies\s*=\s*(.+?)(?: general login link|$)', line, re.IGNORECASE)
            if not cookies_match:
                cookies_match = re.search(r'cookies:\s*(.+?)(?: general login link|$)', line, re.IGNORECASE)
                
            if cookies_match:
                cookies_str = cookies_match.group(1).strip()
                n_id = re.search(r'(?<!Secure)NetflixId=([^;\s]+)', cookies_str, re.IGNORECASE)
                s_n_id = re.search(r'SecureNetflixId=([^;\s]+)', cookies_str, re.IGNORECASE)
                
                if n_id:
                    current_netflix_id = urllib.parse.unquote(n_id.group(1).strip())
                if s_n_id:
                    current_secure_netflix_id = urllib.parse.unquote(s_n_id.group(1).strip())
                    
                if current_netflix_id:
                    push_account()
            continue
            
        if line.upper().startswith("NETFLIX ACCOUNT DETAILS"):
            if current_netflix_id:
                push_account()
            continue
            
        deadflix_email_match = re.search(r'^(?:–|-|#)?\s*Email:\s*(.+)', line, re.IGNORECASE)
        if deadflix_email_match:
            # If we already have a full account ready, push it
            if current_netflix_id and current_email:
                push_account()
            current_email = deadflix_email_match.group(1).strip()
            continue

        deadflix_expire_match = re.search(r'^(?:–|-|#)?\s*(?:Next Billing|Expire):\s*(.+)', line, re.IGNORECASE)
        if deadflix_expire_match:
            current_expire = deadflix_expire_match.group(1).strip()
            continue

        deadflix_plan_match = re.search(r'^(?:–|-|#)?\s*(?:Plan|Membership):\s*(.+)', line, re.IGNORECASE)
        if deadflix_plan_match:
            current_plan = deadflix_plan_match.group(1).strip()
            continue
            
        netflixid_match = re.search(r'^NetflixId(?:=|\s*:\s*)(.+)', line, re.IGNORECASE)
        if netflixid_match:
            if current_netflix_id and current_email:
                push_account()
            current_netflix_id = urllib.parse.unquote(netflixid_match.group(1).strip())
            continue

        secure_netflixid_match = re.search(r'^SecureNetflixId(?:=|\s*:\s*)(.+)', line, re.IGNORECASE)
        if secure_netflixid_match:
            current_secure_netflix_id = urllib.parse.unquote(secure_netflixid_match.group(1).strip())
            continue

        if line.startswith("# ===") or line.startswith("===") or line.startswith("---"):
            if current_netflix_id and (current_email or current_secure_netflix_id):
                push_account()
            continue

        if '.netflix.com' in line:
            parts = line.split()
            if len(parts) >= 3:
                cookie_name = parts[-2]
                cookie_value = urllib.parse.unquote(parts[-1])
                
                if cookie_name == 'NetflixId':
                    current_netflix_id = cookie_value
                elif cookie_name == 'SecureNetflixId':
                    current_secure_netflix_id = cookie_value
                    
    push_account()

    return accounts
