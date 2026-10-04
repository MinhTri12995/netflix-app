import random
import string
import threading
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app

import database
import parser
import checker
from app.blueprints.auth.routes import login_required
from app.services.notification_service import send_telegram_alert

admin_bp = Blueprint("admin", __name__)

def check_single_account(acc, force=False, check_payment=False):
    email = acc[0]
    current_plan = acc[5] if len(acc) > 5 else None

    if not force and current_plan:
        return

    netflix_id = acc[2]
    secure_netflix_id = acc[3] if len(acc) > 3 else ""
    status, plan = checker.check_account_live(netflix_id, secure_netflix_id, check_payment)

    if status == "LIVE":
        if plan and plan != "VALID":
            database.update_plan(email, plan)
    elif status == "DIE":
        database.delete_account(email)

@admin_bp.route("/")
@admin_bp.route("/dashboard")
@login_required
def dashboard():
    database.init_db()

    search_email = request.args.get("search_email", "").strip().lower()
    search_code = request.args.get("search_code", "").strip().upper()

    all_accounts = database.get_all_accounts()
    all_access_keys = database.get_all_access_keys()

    stats = {
        'accounts': {'total': len(all_accounts), 'Premium': 0, 'Standard': 0, 'Standard_Ads': 0, 'Basic': 0},
        'codes': {'total': len(all_access_keys), 'Premium': 0, 'Standard': 0, 'Standard_Ads': 0, 'Basic': 0}
    }

    for code in all_access_keys:
        length = len(code[0])
        if length == 15: stats['codes']['Premium'] += 1
        elif length == 10: stats['codes']['Standard'] += 1
        elif length == 8: stats['codes']['Standard_Ads'] += 1
        elif length == 5: stats['codes']['Basic'] += 1
        else: stats['codes']['Premium'] += 1

    for acc in all_accounts:
        plan = str(acc[5]).strip() if len(acc) > 5 and acc[5] else "Premium"
        if plan in stats['accounts']:
            stats['accounts'][plan] += 1
        else:
            stats['accounts']['Premium'] += 1

    # Filter keys
    if search_code:
        access_keys = [k for k in all_access_keys if search_code in k[0].upper()]
    else:
        access_keys = all_access_keys

    # Filter accounts
    if search_email:
        accounts = [a for a in all_accounts if search_email in a[0].lower()]
    else:
        accounts = all_accounts

    # Pagination
    try:
        key_page = int(request.args.get("key_page", 1))
    except ValueError:
        key_page = 1

    try:
        acc_page = int(request.args.get("acc_page", 1))
    except ValueError:
        acc_page = 1

    PER_PAGE = 50

    total_keys_filtered = len(access_keys)
    key_start = (key_page - 1) * PER_PAGE
    access_keys = access_keys[key_start:key_start + PER_PAGE]
    key_total_pages = max(1, (total_keys_filtered + PER_PAGE - 1) // PER_PAGE)

    total_acc_filtered = len(accounts)
    acc_start = (acc_page - 1) * PER_PAGE
    accounts = accounts[acc_start:acc_start + PER_PAGE]
    acc_total_pages = max(1, (total_acc_filtered + PER_PAGE - 1) // PER_PAGE)

    database.cleanup_old_requests()
    pending_requests = database.get_pending_requests()

    try:
        import proxies_list
        if hasattr(proxies_list, 'PROXIES') and proxies_list.PROXIES:
            current_proxy_url = proxies_list.PROXIES[0]
        elif hasattr(proxies_list, 'ROTATING_PROXY_URL'):
            current_proxy_url = proxies_list.ROTATING_PROXY_URL
        else:
            current_proxy_url = "Webshare Proxy"
        current_proxy = current_proxy_url.split('@')[-1] if '@' in current_proxy_url else current_proxy_url
    except Exception:
        current_proxy = "p.webshare.io:80"

    share_mode_enabled = database.get_config("SHARE_MODE_ENABLED", False)
    mix_plan_enabled = database.get_config("MIX_PREMIUM_STANDARD", False)

    return render_template(
        "admin/dashboard.html",
        accounts=accounts,
        access_keys=access_keys,
        total_accounts=len(all_accounts),
        search_email=search_email,
        search_code=search_code,
        key_page=key_page,
        key_total_pages=key_total_pages,
        acc_page=acc_page,
        acc_total_pages=acc_total_pages,
        pending_requests=pending_requests,
        stats=stats,
        current_proxy=current_proxy,
        share_mode_enabled=share_mode_enabled,
        mix_plan_enabled=mix_plan_enabled
    )

@admin_bp.route("/generate_key", methods=["POST"])
@login_required
def generate_key():
    database.init_db()
    plan_type = request.form.get("plan_type", "basic")
    duration = int(request.form.get("duration", "1"))

    if plan_type == 'premium':
        length = 15
    elif plan_type == 'standard':
        length = 10
    elif plan_type == 'standard_ads':
        length = 8
    else:
        length = 5
        plan_type = 'basic'

    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
    expire_at = (datetime.now() + timedelta(days=30 * duration)).strftime("%Y-%m-%d")

    success, msg = database.create_access_key(code, expire_at)
    if success:
        flash(f"Đã tạo thành công mã {plan_type.upper()} ({duration} tháng): {code}", "success")
    else:
        flash(f"Lỗi tạo mã: {msg}", "error")
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/rotate_key/<code>", methods=["POST"])
@admin_bp.route("/keys/<code>/rotate", methods=["POST"])
@login_required
def rotate_key(code):
    success = database.rotate_access_key(code)
    if success:
        flash(f"Đã đổi tài khoản mới cho mã: {code}", "success")
    else:
        flash("Lỗi: Không còn tài khoản khả dụng trong kho để thay thế.", "error")
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/delete_key/<code>", methods=["POST"])
@admin_bp.route("/keys/<code>/delete", methods=["POST"])
@login_required
def delete_key(code):
    database.delete_access_key(code)
    flash(f"Đã xóa mã truy cập: {code}", "success")
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    if "account_file" not in request.files:
        flash("Lỗi: Không tìm thấy file tải lên.", "error")
        return redirect(url_for("admin.dashboard"))

    file = request.files["account_file"]
    if file.filename == "":
        flash("Lỗi: Bạn chưa chọn file nào.", "error")
        return redirect(url_for("admin.dashboard"))

    file_bytes = file.read()
    try:
        content = file_bytes.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            content = file_bytes.decode('utf-16')
        except UnicodeDecodeError:
            content = file_bytes.decode('latin-1', errors='replace')

    lines = content.splitlines()
    accounts_list = parser.parse_lines(lines)

    if accounts_list:
        database.init_db()
        count = 0
        for acc in accounts_list:
            database.save_account(acc['email'], acc['expire'], acc['netflix_id'], acc['secure_netflix_id'], acc.get('plan'))
            count += 1
        flash(f"🎉 Đã trích xuất và lưu thành công {count} tài khoản vào kho!", "success")
    else:
        flash("❌ Thất bại: Không tìm thấy tài khoản hợp lệ trong file.", "error")

    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/delete/<path:email>", methods=["POST"])
@admin_bp.route("/accounts/<path:email>/delete", methods=["POST"])
@login_required
def delete_acc(email):
    database.delete_account(email)
    flash(f"Đã xóa tài khoản: {email}", "success")
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/toggle_mix_plan", methods=["POST"])
@login_required
def toggle_mix_plan():
    current_mode = database.get_config("MIX_PREMIUM_STANDARD", False)
    new_mode = not current_mode
    database.set_config("MIX_PREMIUM_STANDARD", new_mode)
    status_str = "BẬT" if new_mode else "TẮT"
    flash(f"✅ Đã {status_str} chế độ Mix Plan (Premium + Standard không ads).", "success")
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/toggle_share_mode", methods=["POST"])
@login_required
def toggle_share_mode():
    current_mode = database.get_config("SHARE_MODE_ENABLED", False)
    new_mode = not current_mode
    database.set_config("SHARE_MODE_ENABLED", new_mode)
    status_str = "BẬT" if new_mode else "TẮT"
    flash(f"✅ Đã {status_str} chế độ Share Mode (1 Code = 2 Accounts).", "success")
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/check_all", methods=["POST"])
@login_required
def check_all():
    database.init_db()
    accounts = database.get_all_accounts()
    accounts_to_check = [acc for acc in accounts if not acc[5]]

    if not accounts_to_check:
        flash("Tất cả tài khoản trong kho đều đã có Gói cước.", "warning")
        return redirect(url_for("admin.dashboard"))

    app_ref = current_app._get_current_object()

    def run_bg():
        with app_ref.app_context():
            with ThreadPoolExecutor(max_workers=3) as executor:
                for acc in accounts_to_check:
                    executor.submit(check_single_account, acc, False)

    t = threading.Thread(target=run_bg, daemon=True)
    t.start()
    flash(f"🔄 Đang quét ngầm {len(accounts_to_check)} tài khoản. Cookie chết sẽ tự động bị loại bỏ.", "warning")
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/force_check_all", methods=["POST"])
@login_required
def force_check_all():
    database.init_db()
    accounts = database.get_all_accounts()

    if not accounts:
        flash("Kho hiện không có tài khoản nào để quét.", "warning")
        return redirect(url_for("admin.dashboard"))

    app_ref = current_app._get_current_object()

    def run_force_bg():
        with app_ref.app_context():
            with ThreadPoolExecutor(max_workers=3) as executor:
                for acc in accounts:
                    executor.submit(check_single_account, acc, True, False)

    t = threading.Thread(target=run_force_bg, daemon=True)
    t.start()
    flash(f"🔥 Đang quét toàn bộ {len(accounts)} tài khoản trong kho.", "warning")
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/check_payment", methods=["POST"])
@login_required
def check_payment_route():
    database.init_db()
    accounts = database.get_all_accounts()

    if not accounts:
        flash("Kho hiện không có tài khoản nào để quét lỗi nợ cước.", "warning")
        return redirect(url_for("admin.dashboard"))

    app_ref = current_app._get_current_object()

    def run_payment_bg():
        with app_ref.app_context():
            with ThreadPoolExecutor(max_workers=3) as executor:
                for acc in accounts:
                    executor.submit(check_single_account, acc, True, True)

    t = threading.Thread(target=run_payment_bg, daemon=True)
    t.start()
    flash(f"🚫 Đang quét LỖI THANH TOÁN / NỢ CƯỚC cho {len(accounts)} tài khoản.", "warning")
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/filter_duplicates", methods=["POST"])
@login_required
def filter_duplicates():
    database.init_db()
    accounts = database.get_all_accounts()

    seen_netflix_ids = {}
    duplicates_to_delete = []

    access_keys = database.get_all_access_keys()
    assigned_emails_set = set()
    for k in access_keys:
        if len(k) > 1 and k[1]:
            for e in k[1].split(","):
                if e.strip():
                    assigned_emails_set.add(e.strip())

    for acc in accounts:
        email = acc[0]
        netflix_id = acc[2]
        plan = acc[5]

        if not netflix_id:
            continue

        if netflix_id in seen_netflix_ids:
            existing_email = seen_netflix_ids[netflix_id]['email']
            existing_plan = seen_netflix_ids[netflix_id]['plan']

            if existing_email in assigned_emails_set and email not in assigned_emails_set:
                duplicates_to_delete.append(email)
            elif email in assigned_emails_set and existing_email not in assigned_emails_set:
                duplicates_to_delete.append(existing_email)
                seen_netflix_ids[netflix_id] = {'email': email, 'plan': plan}
            elif plan and not existing_plan:
                duplicates_to_delete.append(existing_email)
                seen_netflix_ids[netflix_id] = {'email': email, 'plan': plan}
            else:
                duplicates_to_delete.append(email)
        else:
            seen_netflix_ids[netflix_id] = {'email': email, 'plan': plan}

    for email in duplicates_to_delete:
        database.delete_account(email)

    if duplicates_to_delete:
        flash(f"🧹 Đã lọc và xóa {len(duplicates_to_delete)} tài khoản trùng NetflixId.", "success")
    else:
        flash("Kho sạch sẽ, không có NetflixId nào bị trùng lặp!", "success")

    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/request/<req_id>/accept", methods=["POST"])
@login_required
def accept_request(req_id):
    database.init_db()
    req = database.get_request_by_id(req_id)
    if not req:
        flash("Lỗi: Không tìm thấy yêu cầu khiếu nại này.", "error")
        return redirect(url_for("admin.dashboard"))

    if req.get("status") != "pending":
        flash(f"⚠️ Yêu cầu #{req_id} đã được xử lý trước đó (Trạng thái: {req.get('status')}).", "warning")
        return redirect(url_for("admin.dashboard"))

    code = (req.get("code") or "").strip()
    if not code:
        flash("Lỗi: Yêu cầu không có mã Access Code hợp lệ.", "error")
        return redirect(url_for("admin.dashboard"))

    acc_key_row = database.get_access_key(code)
    if not acc_key_row:
        flash(f"Lỗi: Không tìm thấy Access Code {code} trong cơ sở dữ liệu.", "error")
        return redirect(url_for("admin.dashboard"))

    old_email = acc_key_row[1] if len(acc_key_row) > 1 else ""

    # BƯỚC 1: Xoay sang tài khoản dự phòng mới TRƯỚC
    rotated = database.rotate_access_key(code)
    if rotated:
        # BƯỚC 2: Xoay thành công mới xóa tài khoản lỗi cũ
        if old_email:
            database.delete_account(old_email)
        # BƯỚC 3: Cập nhật duy nhất yêu cầu này
        database.update_request_status(req_id, "accepted")
        flash(f"✅ Đã duyệt và đổi tài khoản mới thành công cho code {code}.", "success")
    else:
        # Kho hết tài khoản dự phòng -> Giữ nguyên trạng thái pending, KHÔNG xóa tài khoản cũ!
        flash(f"⚠️ Kho hết Cookie dự phòng cho gói của mã {code}. Không thể đổi tài khoản lúc này!", "error")

    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/request/<req_id>/reject", methods=["POST"])
@login_required
def reject_request(req_id):
    database.init_db()
    req = database.get_request_by_id(req_id)
    if not req:
        flash("Lỗi: Không tìm thấy yêu cầu này.", "error")
        return redirect(url_for("admin.dashboard"))

    if req.get("status") != "pending":
        flash(f"⚠️ Yêu cầu #{req_id} đã được xử lý trước đó (Trạng thái: {req.get('status')}).", "warning")
        return redirect(url_for("admin.dashboard"))

    database.update_request_status(req_id, "rejected")
    flash("Đã từ chối yêu cầu đổi tài khoản.", "warning")
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/request/<req_id>/delete", methods=["POST"])
@login_required
def delete_request_route(req_id):
    database.init_db()
    database.delete_request(req_id)
    flash("Đã xóa yêu cầu khỏi danh sách.", "success")
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/keys/delete_lifetime", methods=["POST"])
@login_required
def delete_lifetime_keys():
    database.init_db()
    deleted = database.delete_all_lifetime_keys()
    flash(f"Đã xóa toàn bộ mã vĩnh viễn (Tổng cộng: {deleted}).", "success")
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/keys/cleanup_expired", methods=["POST"])
@login_required
def cleanup_expired_keys_route():
    database.init_db()
    deleted = database.cleanup_expired_keys()
    if deleted > 0:
        flash(f"✅ Đã dọn dẹp và xóa thành công {deleted} mã Access Code đã hết hạn!", "success")
    else:
        flash("ℹ️ Không có mã Access Code nào đã hết hạn cần dọn dẹp.", "info")
    return redirect(url_for("admin.dashboard"))
