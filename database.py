import os
from supabase import create_client, Client

import threading

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://zzdlmwhmhjofqmhfknbv.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SECRET_KEY", "")

_local = threading.local()

def get_supabase() -> Client:
    if not hasattr(_local, "client"):
        _local.client = create_client(SUPABASE_URL, SUPABASE_KEY)
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
    # Bảng sẽ được tạo bằng tay trên giao diện Supabase
    print("Sử dụng Supabase REST API (Không cần init local)")

def save_account(email, expire_date, netflix_id, secure_netflix_id="", plan=None):
    data = {
        "email": email,
        "expire_date": expire_date,
        "netflix_id": netflix_id,
        "secure_netflix_id": secure_netflix_id
    }
    if plan:
        data["plan"] = plan
    get_supabase().table("netflix_accounts").upsert(data).execute()
    
def delete_account(email):
    get_supabase().table("netflix_accounts").delete().eq("email", email).execute()

def update_plan(email, plan):
    data = {"plan": plan}
    get_supabase().table("netflix_accounts").update(data).eq("email", email).execute()

def fetch_all_rows(table_name, columns="*"):
    all_data = []
    limit = 1000
    offset = 0
    while True:
        response = get_supabase().table(table_name).select(columns).range(offset, offset + limit - 1).execute()
        data = response.data
        if not data:
            break
        all_data.extend(data)
        if len(data) < limit:
            break
        offset += limit
    return all_data

def get_all_accounts():
    data = fetch_all_rows("netflix_accounts")
    # Chuyển đổi list of dicts thành list of tuples cho code cũ tương thích
    rows = []
    for r in data:
        rows.append((r["email"], r["expire_date"], r["netflix_id"], r["secure_netflix_id"], r.get("created_at"), r.get("plan")))
    return rows

def get_account_by_email(email):
    response = get_supabase().table("netflix_accounts").select("*").eq("email", email).execute()
    if response.data:
        r = response.data[0]
        return (r["email"], r["expire_date"], r["netflix_id"], r["secure_netflix_id"], r.get("created_at"), r.get("plan"))
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
        
    # 2. CHỈ KHI HẾT tài khoản mới (count == 0) VÀ Share Mode BẬT: mới bắt đầu gán chung tài khoản (tối đa 2 code / 1 acc)
    share_mode = get_config("SHARE_MODE_ENABLED", False)
    if share_mode and available_emails_1:
        return random.choice(available_emails_1)
        
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
