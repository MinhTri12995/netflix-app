import os
import threading
from dotenv import load_dotenv

load_dotenv()

from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://zzdlmwhmhjofqmhfknbv.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_KEY") or ""

_local = threading.local()

def get_supabase() -> Client:
    if not hasattr(_local, "client"):
        key = SUPABASE_KEY or "dummy_key_to_prevent_startup_crash"
        _local.client = create_client(SUPABASE_URL, key)
    return _local.client

import json

CONFIG_FILE = "config.json"

def get_config(key, default=None):
    # 1. Thử lấy từ Supabase DB để lưu vĩnh viễn (không bị mất khi Render khởi động lại/ngủ)
    try:
        res = get_supabase().table("system_config").select("value").eq("key", key).limit(1).execute()
        if res.data and len(res.data) > 0:
            val = res.data[0].get("value")
            if val is not None:
                if str(val).lower() == 'true': return True
                if str(val).lower() == 'false': return False
                return val
    except Exception:
        pass

    # 2. Fallback lấy từ config.json local
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f).get(key, default)
    except:
        return default

def set_config(key, value):
    # 1. Lưu vào local config.json
    try:
        data = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
        data[key] = value
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f)
    except:
        pass
        
    # 2. Lưu vào Supabase DB (nếu có bảng system_config) để giữ cấu hình vĩnh viễn
    try:
        get_supabase().table("system_config").upsert({"key": key, "value": str(value)}).execute()
    except Exception as e:
        print(f"Supabase set_config notice: {e}")

def init_db():
    try:
        import sqlite3
        conn = sqlite3.connect("accounts.db")
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS netflix_accounts (
            email TEXT PRIMARY KEY,
            expire_date TEXT,
            netflix_id TEXT,
            secure_netflix_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            plan TEXT
        )""")
        try:
            c.execute("ALTER TABLE netflix_accounts ADD COLUMN plan TEXT")
        except Exception:
            pass
        c.execute("""CREATE TABLE IF NOT EXISTS access_keys (
            code TEXT PRIMARY KEY,
            assigned_email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expire_at TEXT
        )""")
        try:
            c.execute("ALTER TABLE access_keys ADD COLUMN expire_at TEXT")
        except Exception:
            pass
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"init_db local SQLite notice: {e}")

def save_account(email, expire_date, netflix_id, secure_netflix_id="", plan=None):
    data = {
        "email": email,
        "expire_date": expire_date,
        "netflix_id": netflix_id,
        "secure_netflix_id": secure_netflix_id
    }
    if plan:
        data["plan"] = plan
    try:
        if SUPABASE_KEY:
            get_supabase().table("netflix_accounts").upsert(data).execute()
            return
    except Exception as e:
        print(f"Supabase save_account error: {e}")
    try:
        import sqlite3
        conn = sqlite3.connect("accounts.db")
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS netflix_accounts (
            email TEXT PRIMARY KEY,
            expire_date TEXT,
            netflix_id TEXT,
            secure_netflix_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            plan TEXT
        )""")
        try:
            c.execute("ALTER TABLE netflix_accounts ADD COLUMN plan TEXT")
        except Exception:
            pass
        c.execute("INSERT OR REPLACE INTO netflix_accounts (email, expire_date, netflix_id, secure_netflix_id, plan) VALUES (?, ?, ?, ?, ?)",
                  (email, expire_date, netflix_id, secure_netflix_id, plan or "Premium"))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"SQLite save_account error: {e}")
    
def delete_account(email):
    try:
        if SUPABASE_KEY:
            get_supabase().table("netflix_accounts").delete().eq("email", email).execute()
    except Exception as e:
        print(f"Supabase delete error: {e}")
    try:
        import sqlite3
        if os.path.exists("accounts.db"):
            conn = sqlite3.connect("accounts.db")
            c = conn.cursor()
            c.execute("DELETE FROM netflix_accounts WHERE email = ?", (email,))
            conn.commit()
            conn.close()
    except Exception:
        pass

def update_plan(email, plan):
    data = {"plan": plan}
    try:
        if SUPABASE_KEY:
            get_supabase().table("netflix_accounts").update(data).eq("email", email).execute()
    except Exception as e:
        print(f"Supabase update_plan error: {e}")
    try:
        import sqlite3
        if os.path.exists("accounts.db"):
            conn = sqlite3.connect("accounts.db")
            c = conn.cursor()
            c.execute("UPDATE netflix_accounts SET plan = ? WHERE email = ?", (plan, email))
            conn.commit()
            conn.close()
    except Exception:
        pass

def fetch_all_rows(table_name, columns="*"):
    all_data = []
    limit = 1000
    offset = 0
    try:
        if SUPABASE_KEY:
            while True:
                response = get_supabase().table(table_name).select(columns).range(offset, offset + limit - 1).execute()
                data = response.data
                if not data:
                    break
                all_data.extend(data)
                if len(data) < limit:
                    break
                offset += limit
            if all_data:
                return all_data
    except Exception as e:
        print(f"Supabase fetch error for {table_name}: {e}")

    # Fallback to local SQLite if Supabase credentials are missing or API fails
    try:
        import sqlite3
        db_path = "accounts.db" if os.path.exists("accounts.db") else ("netflix.db" if os.path.exists("netflix.db") else None)
        if db_path:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            if table_name == "netflix_accounts":
                c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='netflix_accounts'")
                if c.fetchone():
                    c.execute("SELECT * FROM netflix_accounts")
                    rows = c.fetchall()
                    conn.close()
                    result = []
                    for r in rows:
                        result.append({
                            "email": r[0] if len(r) > 0 else "",
                            "expire_date": r[1] if len(r) > 1 else "",
                            "netflix_id": r[2] if len(r) > 2 else "",
                            "secure_netflix_id": r[3] if len(r) > 3 else "",
                            "created_at": r[4] if len(r) > 4 else "",
                            "plan": r[5] if len(r) > 5 else "Premium",
                        })
                    return result
            elif table_name == "access_keys":
                c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='access_keys'")
                if c.fetchone():
                    c.execute("SELECT * FROM access_keys")
                    rows = c.fetchall()
                    conn.close()
                    result = []
                    for r in rows:
                        result.append({
                            "code": r[0] if len(r) > 0 else "",
                            "assigned_email": r[1] if len(r) > 1 else "",
                            "created_at": r[2] if len(r) > 2 else "",
                            "expire_at": r[3] if len(r) > 3 else None,
                        })
                    return result
            conn.close()
    except Exception as e:
        print(f"SQLite fallback error: {e}")
    return all_data

def get_all_accounts():
    data = fetch_all_rows("netflix_accounts")
    # Chuyển đổi list of dicts thành list of tuples cho code cũ tương thích
    rows = []
    for r in data:
        rows.append((r.get("email"), r.get("expire_date"), r.get("netflix_id"), r.get("secure_netflix_id"), r.get("created_at"), r.get("plan", "Premium")))
    return rows

def get_account_by_email(email):
    try:
        if SUPABASE_KEY:
            response = get_supabase().table("netflix_accounts").select("*").eq("email", email).execute()
            if response.data:
                r = response.data[0]
                return (r["email"], r["expire_date"], r["netflix_id"], r["secure_netflix_id"], r.get("created_at"), r.get("plan"))
    except Exception:
        pass
    try:
        import sqlite3
        if os.path.exists("accounts.db"):
            conn = sqlite3.connect("accounts.db")
            c = conn.cursor()
            c.execute("SELECT email, expire_date, netflix_id, secure_netflix_id, created_at, plan FROM netflix_accounts WHERE email = ?", (email,))
            r = c.fetchone()
            conn.close()
            if r:
                return (r[0], r[1], r[2], r[3], r[4], r[5] if len(r)>5 else "Premium")
    except Exception:
        pass
    return None

def get_random_available_account(plan_type=None):
    import random
    
    # Lấy toàn bộ account có trong kho
    acc_data = fetch_all_rows("netflix_accounts", "email, plan")
    if not acc_data:
        return None
        
    # Lọc tài khoản theo gói cước nếu có yêu cầu
    if plan_type:
        premium_kws = ['premium', 'ultra', 'премиум', 'özel', 'ozel', 'cao cấp', 'พรีเมียม', 'مميز', '高級', '高级', 'プレミアム', '프리미엄']
        standard_kws = ['standard', 'tiêu chuẩn', 'стандартный', 'standart', '標準', '标准', 'estándar', 'padrão', 'มาตรฐาน', 'قياسي', 'スタンダード', '스탠다드']
        basic_kws = ['basic', 'cơ bản', 'базовый', 'temel', 'básico', 'พื้นฐาน', 'أساسي', '基本', 'ベーシック', '베이직']
        ads_kws = ['ads', 'adverts', 'anuncios', 'pub', 'werbung', 'pubblicità', 'quảng cáo', 'โฆษณา', '広告', '광고', '廣告', '广告', 'рекламо', 'reklam', 'reklamy']

        import re
        def has_any_kw(text, kws):
            for kw in kws:
                if re.match(r'^[a-z_]+$', kw):
                    if re.search(r'\b' + kw + r'\b', text):
                        return True
                else:
                    if kw in text:
                        return True
            return False

        all_emails = []
        for r in acc_data:
            raw_plan = r.get("plan")
            plan_str = str(raw_plan).lower() if raw_plan else ""
            
            # Nếu chưa có thông tin gói (plan rỗng/None/N/A), mặc định coi là Premium (giống như thống kê ngoài Dashboard)
            if not plan_str or plan_str == "none" or plan_str == "n/a":
                if plan_type == "Premium":
                    all_emails.append(r["email"])
                continue
                
            is_match = False
            if plan_type == "Premium":
                if has_any_kw(plan_str, premium_kws):
                    is_match = True
            elif plan_type == "Standard_Ads":
                if has_any_kw(plan_str, standard_kws) and has_any_kw(plan_str, ads_kws):
                    is_match = True
                elif "standard_ads" in plan_str:
                    is_match = True
            elif plan_type == "Standard":
                if has_any_kw(plan_str, standard_kws) and not has_any_kw(plan_str, ads_kws):
                    is_match = True
            elif plan_type == "Basic":
                if has_any_kw(plan_str, basic_kws):
                    is_match = True
                    
            if is_match or plan_type.lower() == plan_str:
                all_emails.append(r["email"])
                
        # Nếu không tìm thấy acc khớp gói chính xác, dùng toàn bộ acc trong kho làm fallback
        if not all_emails:
            all_emails = [r["email"] for r in acc_data]
    else:
        all_emails = [r["email"] for r in acc_data]
    
    keys_data = fetch_all_rows("access_keys", "assigned_email")
    from collections import Counter
    email_counts = Counter()
    for r in keys_data:
        if r.get("assigned_email"):
            # Tách bằng dấu phẩy trong trường hợp DB cũ còn lưu nhiều email
            for e in r["assigned_email"].split(","):
                email = e.strip()
                if email:
                    email_counts[email] += 1
    
    available_emails_0 = []
    available_emails_1 = []
    
    for email in all_emails:
        count = email_counts.get(email, 0)
        if count == 0:
            available_emails_0.append(email)
        elif count == 1:
            available_emails_1.append(email)
            
    # 1. Luôn ưu tiên dùng tài khoản mới tinh chưa gán cho code nào (1 code = 1 acc riêng biệt)
    if available_emails_0:
        return random.choice(available_emails_0)
        
    # 2. Khi hết tài khoản mới, gán vào tài khoản có 1 code
    if available_emails_1:
        return random.choice(available_emails_1)
        
    # 3. Fallback cuối: Chọn tài khoản có số lượng code gán ít nhất
    if all_emails:
        return min(all_emails, key=lambda e: email_counts.get(e, 0))
        
    all_all = [r["email"] for r in acc_data]
    if all_all:
        return min(all_all, key=lambda e: email_counts.get(e, 0))
        
    return None

def create_request(code, image_url, status="pending"):
    data = {
        "code": code,
        "image_url": image_url,
        "status": status
    }
    # created_at is automatically handled by Supabase
    get_supabase().table("requests").insert(data).execute()

def has_recent_request(code, minutes=5):
    import datetime
    try:
        time_ago = (datetime.datetime.utcnow() - datetime.timedelta(minutes=minutes)).isoformat()
        response = get_supabase().table("requests").select("id").eq("code", code).gt("created_at", time_ago).limit(1).execute()
        return len(response.data) > 0
    except Exception as e:
        print(f"Lỗi check_rate_limit: {e}")
        return False

def get_today_rotation_count(code):
    import datetime
    try:
        twenty_four_hours_ago = (datetime.datetime.utcnow() - datetime.timedelta(hours=24)).isoformat()
        response = get_supabase().table("requests") \
            .select("id, status") \
            .eq("code", code) \
            .gt("created_at", twenty_four_hours_ago) \
            .execute()
        rows = response.data if response.data else []
        accepted_count = sum(1 for r in rows if str(r.get("status", "")).startswith("accepted"))
        return accepted_count
    except Exception as e:
        print(f"Lỗi get_today_rotation_count: {e}")
        return 0

def get_pending_requests():
    try:
        response = get_supabase().table("requests").select("*").eq("status", "pending").order("created_at", desc=True).execute()
        return response.data if response.data else []
    except Exception as e:
        print(f"Lỗi get_pending_requests (Có thể chưa tạo bảng requests): {e}")
        return []

def update_request_status(req_id, status):
    data = {"status": status}
    get_supabase().table("requests").update(data).eq("id", req_id).execute()

def get_request_by_id(req_id):
    response = get_supabase().table("requests").select("*").eq("id", req_id).execute()
    return response.data[0] if response.data else None

def cleanup_old_requests():
    import datetime
    try:
        # Tìm các request cũ hơn 24 giờ
        yesterday = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).isoformat()
        response = get_supabase().table("requests").select("*").lt("created_at", yesterday).execute()
        old_requests = response.data if response.data else []
        
        for req in old_requests:
            # Xóa ảnh trên storage nếu là ảnh lưu trên Supabase
            if req.get("image_url") and "supabase.co/storage/v1/object/public/requests/" in req["image_url"]:
                try:
                    filename = req["image_url"].split("/")[-1]
                    get_supabase().storage.from_("requests").remove([filename])
                except Exception as e:
                    print(f"Lỗi xóa ảnh cũ: {e}")
            
            # Xóa row trong DB
            get_supabase().table("requests").delete().eq("id", req["id"]).execute()
    except Exception as e:
        print(f"Lỗi cleanup requests: {e}")

def create_access_key(code, expire_at=None):
    # Xác định gói cước dựa trên độ dài mã
    if len(code) == 15:
        plan_type = "Premium"
    elif len(code) == 10:
        plan_type = "Standard"
    elif len(code) == 8:
        plan_type = "Standard_Ads"
    elif len(code) == 5:
        plan_type = "Basic"
    else:
        plan_type = "Premium"
    
    email1 = get_random_available_account(plan_type)
    if not email1:
        return False, f"No available {plan_type} cookies left in the vault."
        
    email = email1
    if get_access_key(code):
        return False, "This access key already exists."
        
    try:
        data = {
            "code": code,
            "assigned_email": email
        }
        if expire_at:
            data["expire_at"] = expire_at
            
        get_supabase().table("access_keys").insert(data).execute()
        return True, "Success"
    except Exception as e:
        return False, f"Database error: {e}"

def get_access_key(code):
    response = get_supabase().table("access_keys").select("*").eq("code", code).execute()
    if response.data:
        r = response.data[0]
        return (r["code"], r["assigned_email"], r.get("expire_at"))
    return None

def get_all_access_keys():
    # Fetch all data manually to bypass 1000 limit, then sort
    data = fetch_all_rows("access_keys")
    data.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    
    rows = []
    for r in data:
        rows.append((r["code"], r["assigned_email"], r.get("created_at"), r.get("expire_at")))
    return rows

def rotate_access_key(code):
    # Xác định gói cước dựa trên độ dài mã
    if len(code) == 15:
        plan_type = "Premium"
    elif len(code) == 10:
        plan_type = "Standard"
    elif len(code) == 8:
        plan_type = "Standard_Ads"
    elif len(code) == 5:
        plan_type = "Basic"
    else:
        plan_type = "Premium"
    
    new_email = get_random_available_account(plan_type)
    if not new_email:
        return False
        
    data = {"assigned_email": new_email}
    try:
        get_supabase().table("access_keys").update(data).eq("code", code).execute()
        return True
    except Exception as e:
        print(f"Lỗi Rotate DB: {e}")
        return False

def delete_access_key(code):
    get_supabase().table("access_keys").delete().eq("code", code).execute()
