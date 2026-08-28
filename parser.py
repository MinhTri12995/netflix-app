import re
import uuid
import json
import urllib.parse

def parse_lines(lines):
    """
    Universally parse Netflix accounts and cookies from various formats:
    1. JSON Array: [{"name": "NetflixId", "value": "..."}, ...]
    2. JSON Object: {"cookies": [...]}
    3. Single-line Pipe formats:
       - email:pass | memberPlan = ... | NextBillingDate = ... | Cookie = NetflixId=...;SecureNetflixId=...
       - email:pass | ... | Cookie = NetflixId=... | SecureNetflixId=...
       - email:pass | cookies: NetflixId=...; SecureNetflixId=...
    4. Multi-line Account details:
       - Email: ...
       - Next Billing: ...
       - Plan: ...
       - NetflixId: ...
       - SecureNetflixId: ...
    5. Netscape cookie format:
       - .netflix.com TRUE / FALSE ... NetflixId ...
       - .netflix.com TRUE / FALSE ... SecureNetflixId ...
    6. Raw cookie header lines:
       - NetflixId=...; SecureNetflixId=...
    """
    accounts = []
    
    # Handle single string content if passed
    if isinstance(lines, str):
        lines = lines.splitlines()
        
    full_text = "\n".join(lines).strip()
    
    # 1. JSON Support
    if full_text.startswith('[') or full_text.startswith('{'):
        try:
            parsed_json = json.loads(full_text)
            cookie_array = None
            if isinstance(parsed_json, list):
                cookie_array = parsed_json
            elif isinstance(parsed_json, dict) and 'cookies' in parsed_json and isinstance(parsed_json['cookies'], list):
                cookie_array = parsed_json['cookies']
                
            if cookie_array:
                nid, snid = None, ""
                for c in cookie_array:
                    if isinstance(c, dict):
                        c_name = c.get('name') or c.get('Name')
                        c_val = c.get('value') or c.get('Value', '')
                        if c_name == 'NetflixId':
                            nid = urllib.parse.unquote(str(c_val))
                        elif c_name == 'SecureNetflixId':
                            snid = urllib.parse.unquote(str(c_val))
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
                current_email = f"auto_{uuid.uuid4().hex[:8]}@netflix.com"
            clean_plan = current_plan
            if clean_plan and str(clean_plan).strip().lower() in ['none found', 'none', 'unknown', 'n/a', 'null', '']:
                clean_plan = None
            accounts.append({
                'email': current_email,
                'expire': current_expire or 'N/A',
                'plan': clean_plan or 'Premium',
                'netflix_id': current_netflix_id,
                'secure_netflix_id': current_secure_netflix_id or ""
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
            
        lower_line = line.lower()
        
        # A. Single-line formatted accounts containing '|'
        if '|' in line:
            # 1. Check if line contains Netflix cookies
            if 'netflixid=' in lower_line or 'cookie' in lower_line or 'memberplan' in lower_line or 'membership' in lower_line:
                # If we have an unfinished account from previous lines, push it
                if current_netflix_id:
                    push_account()
                    
                # Extract Email
                email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', line)
                line_email = email_match.group(1).strip().lower() if email_match else None
                if not line_email and ':' in line:
                    part0 = line.split(':')[0].strip()
                    if '@' in part0:
                        line_email = part0.lower()
                        
                # Extract Plan
                plan_match = re.search(r'(?:memberPlan|Membership|Plan)\s*[=:]\s*([^|]+)', line, re.IGNORECASE)
                line_plan = plan_match.group(1).strip() if plan_match else None
                
                # Extract Expire
                exp_match = re.search(r'(?:NextBillingDate|Nextbillingdate|Next Billing|Expire)\s*[=:]\s*([^|]+)', line, re.IGNORECASE)
                line_expire = exp_match.group(1).strip() if exp_match else None
                
                # Extract NetflixId & SecureNetflixId
                nid_match = re.search(r'(?<!Secure)NetflixId=([^;|\s]+)', line, re.IGNORECASE)
                snid_match = re.search(r'SecureNetflixId=([^;|\s]+)', line, re.IGNORECASE)
                
                line_nid = urllib.parse.unquote(nid_match.group(1).strip()) if nid_match else None
                line_snid = urllib.parse.unquote(snid_match.group(1).strip()) if snid_match else ""
                
                if line_nid:
                    current_email = line_email
                    current_plan = line_plan
                    current_expire = line_expire
                    current_netflix_id = line_nid
                    current_secure_netflix_id = line_snid
                    push_account()
                    continue
                    
        # B. Header markers
        if line.upper().startswith("NETFLIX ACCOUNT DETAILS"):
            if current_netflix_id:
                push_account()
            continue
            
        # C. Multi-line Email
        deadflix_email_match = re.search(r'^(?:–|-|#)?\s*Email:\s*(.+)', line, re.IGNORECASE)
        if deadflix_email_match:
            if current_netflix_id and current_email:
                push_account()
            current_email = deadflix_email_match.group(1).strip().lower()
            continue

        # D. Multi-line Expire
        deadflix_expire_match = re.search(r'^(?:–|-|#)?\s*(?:Next Billing|Expire):\s*(.+)', line, re.IGNORECASE)
        if deadflix_expire_match:
            current_expire = deadflix_expire_match.group(1).strip()
            continue

        # E. Multi-line Plan
        deadflix_plan_match = re.search(r'^(?:–|-|#)?\s*(?:Plan|Membership):\s*(.+)', line, re.IGNORECASE)
        if deadflix_plan_match:
            current_plan = deadflix_plan_match.group(1).strip()
            continue
            
        # F. Multi-line NetflixId
        netflixid_match = re.search(r'^NetflixId(?:=|\s*:\s*)(.+)', line, re.IGNORECASE)
        if netflixid_match:
            if current_netflix_id and current_email:
                push_account()
            current_netflix_id = urllib.parse.unquote(netflixid_match.group(1).strip())
            continue

        # G. Multi-line SecureNetflixId
        secure_netflixid_match = re.search(r'^SecureNetflixId(?:=|\s*:\s*)(.+)', line, re.IGNORECASE)
        if secure_netflixid_match:
            current_secure_netflix_id = urllib.parse.unquote(secure_netflixid_match.group(1).strip())
            continue

        # H. Separator lines
        if line.startswith("# ===") or line.startswith("===") or line.startswith("---") or line.startswith("___"):
            if current_netflix_id and (current_email or current_secure_netflix_id):
                push_account()
            continue

        # I. Netscape tab-separated format
        if '.netflix.com' in line:
            parts = line.split()
            if len(parts) >= 3:
                cookie_name = parts[-2]
                cookie_value = urllib.parse.unquote(parts[-1])
                
                if cookie_name == 'NetflixId':
                    current_netflix_id = cookie_value
                elif cookie_name == 'SecureNetflixId':
                    current_secure_netflix_id = cookie_value
            continue
            
        # J. Raw Cookie String line (e.g. NetflixId=...; SecureNetflixId=...)
        if 'netflixid=' in lower_line:
            nid_match = re.search(r'(?<!Secure)NetflixId=([^;|\s]+)', line, re.IGNORECASE)
            snid_match = re.search(r'SecureNetflixId=([^;|\s]+)', line, re.IGNORECASE)
            if nid_match:
                if current_netflix_id and current_email:
                    push_account()
                current_netflix_id = urllib.parse.unquote(nid_match.group(1).strip())
                if snid_match:
                    current_secure_netflix_id = urllib.parse.unquote(snid_match.group(1).strip())
                continue

    push_account()
    return accounts
