import re

def parse_lines(lines):
    accounts = []
    
    current_email = None
    current_expire = None
    current_plan = None
    current_netflix_id = None
    current_secure_netflix_id = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Hỗ trợ định dạng DEADFLIX CHECKER: "– Email: example@gmail.com"
        deadflix_email_match = re.search(r'^(?:–|-)\s*Email:\s*(.+)', line, re.IGNORECASE)
        if deadflix_email_match:
            if current_email and current_netflix_id:
                accounts.append({
                    'email': current_email,
                    'expire': current_expire,
                    'plan': current_plan,
                    'netflix_id': current_netflix_id,
                    'secure_netflix_id': current_secure_netflix_id
                })
            current_email = deadflix_email_match.group(1).strip()
            current_expire = None
            current_plan = None
            current_netflix_id = None
            current_secure_netflix_id = ""
            continue

        # Hỗ trợ định dạng DEADFLIX CHECKER: "– Next Billing: 2026-07-06"
        deadflix_expire_match = re.search(r'^(?:–|-)\s*Next Billing:\s*(.+)', line, re.IGNORECASE)
        if deadflix_expire_match:
            current_expire = deadflix_expire_match.group(1).strip()
            continue

        # Hỗ trợ định dạng DEADFLIX CHECKER: "– Plan: Premium"
        deadflix_plan_match = re.search(r'^(?:–|-)\s*Plan:\s*(.+)', line, re.IGNORECASE)
        if deadflix_plan_match:
            current_plan = deadflix_plan_match.group(1).strip()
            continue
            
        # Hỗ trợ cả định dạng cũ (#EMAIL) và mới (Email:)
        email_match = re.search(r'^(?:#EMAIL\s*:|Email:)\s*(.+)', line, re.IGNORECASE)
        if email_match:
            if current_email and current_netflix_id:
                accounts.append({
                    'email': current_email,
                    'expire': current_expire,
                    'plan': current_plan,
                    'netflix_id': current_netflix_id,
                    'secure_netflix_id': current_secure_netflix_id
                })
            current_email = email_match.group(1).strip()
            current_expire = None
            current_plan = None
            current_netflix_id = None
            current_secure_netflix_id = ""
            continue
            
        expire_match = re.search(r'^(?:#EXPIRE\s*:|Expire:)\s*(.+)', line, re.IGNORECASE)
        if expire_match:
            current_expire = expire_match.group(1).strip()
            continue
            
        # Hỗ trợ định dạng mới: NetflixId: <cookie>
        netflixid_match = re.search(r'^NetflixId:\s*(.+)', line, re.IGNORECASE)
        if netflixid_match:
            current_netflix_id = netflixid_match.group(1).strip()
            continue

        # Vẫn giữ hỗ trợ định dạng Netscape cũ (áp dụng cho DEADFLIX CHECKER)
        if '.netflix.com' in line:
            parts = line.split('\t')
            if len(parts) >= 7:
                cookie_name = parts[5].strip()
                cookie_value = parts[6].strip()
                
                if cookie_name == 'NetflixId':
                    current_netflix_id = cookie_value
                elif cookie_name == 'SecureNetflixId':
                    current_secure_netflix_id = cookie_value
                    
    # Push the last account
    if current_email and current_netflix_id:
        accounts.append({
            'email': current_email,
            'expire': current_expire,
            'plan': current_plan,
            'netflix_id': current_netflix_id,
            'secure_netflix_id': current_secure_netflix_id
        })

    return accounts
