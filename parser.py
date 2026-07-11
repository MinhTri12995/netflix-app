import re
import uuid

def parse_lines(lines):
    accounts = []
    
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
            accounts.append({
                'email': current_email,
                'expire': current_expire,
                'plan': current_plan,
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
            
        if '|' in line and 'cookies:' in line:
            email_part = line.split(':')[0] if ':' in line else None
            if email_part and '@' in email_part:
                current_email = email_part.strip()
            
            expire_match_single = re.search(r'Nextbillingdate\s*=\s*([^|]+)', line, re.IGNORECASE)
            if expire_match_single:
                current_expire = expire_match_single.group(1).strip()
                
            plan_match_single = re.search(r'Membership:\s*([^|]+)', line, re.IGNORECASE)
            if plan_match_single:
                current_plan = plan_match_single.group(1).strip()
                
            cookies_match = re.search(r'cookies:\s*(.+?)(?: general login link|$)', line, re.IGNORECASE)
            if cookies_match:
                cookies_str = cookies_match.group(1).strip()
                
                n_id = re.search(r'NetflixId=([^;\s]+)', cookies_str, re.IGNORECASE)
                s_n_id = re.search(r'SecureNetflixId=([^;\s]+)', cookies_str, re.IGNORECASE)
                
                if n_id:
                    current_netflix_id = n_id.group(1).strip()
                if s_n_id:
                    current_secure_netflix_id = s_n_id.group(1).strip()
                    
                if current_netflix_id:
                    push_account()
            continue
            
        if line.upper().startswith("NETFLIX ACCOUNT DETAILS"):
            push_account()
            continue
            
        deadflix_email_match = re.search(r'^(?:–|-)\s*Email:\s*(.+)', line, re.IGNORECASE)
        if deadflix_email_match:
            push_account()
            current_email = deadflix_email_match.group(1).strip()
            continue

        deadflix_expire_match = re.search(r'^(?:–|-)\s*Next Billing:\s*(.+)', line, re.IGNORECASE)
        if deadflix_expire_match:
            current_expire = deadflix_expire_match.group(1).strip()
            continue

        deadflix_plan_match = re.search(r'^(?:–|-)\s*Plan:\s*(.+)', line, re.IGNORECASE)
        if deadflix_plan_match:
            current_plan = deadflix_plan_match.group(1).strip()
            continue
            
        email_match = re.search(r'^(?:#EMAIL\s*:|Email:)\s*(.+)', line, re.IGNORECASE)
        if email_match:
            push_account()
            current_email = email_match.group(1).strip()
            continue
            
        expire_match = re.search(r'^(?:#EXPIRE\s*:|Expire:)\s*(.+)', line, re.IGNORECASE)
        if expire_match:
            current_expire = expire_match.group(1).strip()
            continue
            
        netflixid_match = re.search(r'^NetflixId(?:=|\s*:\s*)(.+)', line, re.IGNORECASE)
        if netflixid_match:
            if current_netflix_id:
                push_account()
            current_netflix_id = netflixid_match.group(1).strip()
            continue

        secure_netflixid_match = re.search(r'^SecureNetflixId(?:=|\s*:\s*)(.+)', line, re.IGNORECASE)
        if secure_netflixid_match:
            current_secure_netflix_id = secure_netflixid_match.group(1).strip()
            continue

        if '.netflix.com' in line:
            parts = line.split('\t')
            if len(parts) >= 7:
                cookie_name = parts[5].strip()
                cookie_value = parts[6].strip()
                
                if cookie_name == 'NetflixId':
                    current_netflix_id = cookie_value
                elif cookie_name == 'SecureNetflixId':
                    current_secure_netflix_id = cookie_value
                    
    push_account()

    return accounts
