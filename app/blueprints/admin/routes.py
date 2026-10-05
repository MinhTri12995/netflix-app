import secrets
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

_scan_lock = threading.Lock()
_is_scanning = False

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

    stats = database.get_dashboard_aggregates()

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
    from app.services.allocation_service import generate_secure_code
    plan_raw = request.form.get("plan_type", "basic").lower()
    duration = int(request.form.get("duration", "1"))

    norm_plan = {
        'premium': 'Premium',
        'standard': 'Standard',
        'standard_ads': 'Standard_Ads',
        'basic': 'Basic'
    }.get(plan_raw, 'Premium')

    code = generate_secure_code(norm_plan, length=16)
    expire_at = (datetime.now() + timedelta(days=30 * duration)).strftime("%Y-%m-%d")

    success, msg = database.create_access_key(code, expire_at, plan_type=norm_plan)
    if success:
        flash(f"Đã tạo thành công mã {norm_plan.upper()} ({duration} tháng): {code}", "success")
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
    global _is_scanning
    with _scan_lock:
        if _is_scanning:
            flash("Một tiến trình quét tài khoản đang chạy. Vui lòng đợi quét xong trước khi bắt đầu quét mới.", "warning")
            return redirect(url_for("admin.dashboard"))
        _is_scanning = True

    database.init_db()
    accounts = database.get_all_accounts()
    accounts_to_check = [acc for acc in accounts if not acc[5]]

    if not accounts_to_check:
        with _scan_lock:
            _is_scanning = False
        flash("Tất cả tài khoản trong kho đều đã có Gói cước.", "warning")
        return redirect(url_for("admin.dashboard"))

    app_ref = current_app._get_current_object()

    def run_bg():
        global _is_scanning
        try:
            with app_ref.app_context():
                with ThreadPoolExecutor(max_workers=3) as executor:
                    for acc in accounts_to_check:
                        executor.submit(check_single_account, acc, False)
        finally:
            with _scan_lock:
                _is_scanning = False

    t = threading.Thread(target=run_bg, daemon=True)
    t.start()
    flash(f"🔄 Đang quét ngầm {len(accounts_to_check)} tài khoản. Cookie chết sẽ tự động bị loại bỏ.", "warning")
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/force_check_all", methods=["POST"])
@login_required
def force_check_all():
    global _is_scanning
    with _scan_lock:
        if _is_scanning:
            flash("Một tiến trình quét tài khoản đang chạy. Vui lòng đợi quét xong trước khi bắt đầu quét mới.", "warning")
            return redirect(url_for("admin.dashboard"))
        _is_scanning = True

    database.init_db()
    accounts = database.get_all_accounts()

    if not accounts:
        with _scan_lock:
            _is_scanning = False
        flash("Kho hiện không có tài khoản nào để quét.", "warning")
        return redirect(url_for("admin.dashboard"))

    app_ref = current_app._get_current_object()

    def run_force_bg():
        global _is_scanning
        try:
            with app_ref.app_context():
                with ThreadPoolExecutor(max_workers=3) as executor:
                    for acc in accounts:
                        executor.submit(check_single_account, acc, True, False)
        finally:
            with _scan_lock:
                _is_scanning = False

    t = threading.Thread(target=run_force_bg, daemon=True)
    t.start()
    flash(f"🔥 Đang quét toàn bộ {len(accounts)} tài khoản trong kho.", "warning")
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/check_payment", methods=["POST"])
@login_required
def check_payment_route():
    global _is_scanning
    with _scan_lock:
        if _is_scanning:
            flash("Một tiến trình quét tài khoản đang chạy. Vui lòng đợi quét xong trước khi bắt đầu quét mới.", "warning")
            return redirect(url_for("admin.dashboard"))
        _is_scanning = True

    database.init_db()
    accounts = database.get_all_accounts()

    if not accounts:
        with _scan_lock:
            _is_scanning = False
        flash("Kho hiện không có tài khoản nào để quét lỗi nợ cước.", "warning")
        return redirect(url_for("admin.dashboard"))

    app_ref = current_app._get_current_object()

    def run_payment_bg():
        global _is_scanning
        try:
            with app_ref.app_context():
                with ThreadPoolExecutor(max_workers=3) as executor:
                    for acc in accounts:
                        executor.submit(check_single_account, acc, True, True)
        finally:
            with _scan_lock:
                _is_scanning = False

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
    from app.services.allocation_service import replace
    op_id = f"admin_accept_{req_id}"
    res = replace(request_id=req_id, actor="admin", operation_id=op_id)
    if res.is_success:
        flash(f"✅ Đã duyệt và đổi tài khoản mới thành công.", "success")
    elif res.status == "already_processed":
        flash(f"⚠️ Yêu cầu #{req_id} đã được xử lý trước đó.", "warning")
    elif res.status == "out_of_stock":
        flash(f"⚠️ Kho hết Cookie dự phòng cho gói của yêu cầu này. Đã giữ lại yêu cầu trong hàng chờ!", "error")
    elif res.status == "limit_exceeded":
        flash("⚠️ Mã này đã đạt giới hạn đổi trong 24 giờ (tối đa 5 lần).", "error")
    else:
        flash(f"Lỗi: {res.message}", "error")

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

@admin_bp.route("/orders", methods=["GET"])
@login_required
def orders_dashboard():
    database.init_db()
    from app.services.order_service import list_orders
    status_filter = request.args.get("status")
    orders = list_orders(status_filter=status_filter)
    csrf_token = generate_csrf_token()
    return render_template("admin/orders.html", orders=orders, csrf_token=csrf_token)

@admin_bp.route("/orders/create", methods=["POST"])
@login_required
def create_order_route():
    database.init_db()
    from app.services.order_service import create_or_update_order
    order_id = request.form.get("order_id", "").strip()
    code = request.form.get("code", "").strip()
    status = request.form.get("status", "verified").strip()
    admin_user = session.get("user", "admin")

    ok, msg = create_or_update_order(order_id=order_id, code=code, status=status, actor=f"admin:{admin_user}")
    if ok:
        flash(f"✅ Đã lưu thành công đơn hàng {order_id} cho mã {code}.", "success")
    else:
        flash(f"Lỗi: Không thể lưu đơn hàng ({msg}).", "error")

    return redirect(url_for("admin.orders_dashboard"))

@admin_bp.route("/orders/import_csv", methods=["POST"])
@login_required
def import_orders_csv_route():
    database.init_db()
    from app.services.order_service import import_orders_csv
    admin_user = session.get("user", "admin")

    csv_text = request.form.get("csv_text", "").strip()
    file = request.files.get("csv_file")

    if file and file.filename:
        try:
            csv_text = file.read().decode("utf-8-sig", errors="ignore")
        except Exception as e:
            flash(f"Lỗi đọc tệp CSV: {e}", "error")
            return redirect(url_for("admin.orders_dashboard"))

    if not csv_text:
        flash("Vui lòng tải lên tệp CSV hoặc nhập nội dung văn bản CSV.", "error")
        return redirect(url_for("admin.orders_dashboard"))

    result = import_orders_csv(csv_text, actor=f"admin:{admin_user}")
    success_count = result.get("success_count", 0)
    errors = result.get("errors", [])

    if success_count > 0:
        flash(f"✅ Đã nhập thành công {success_count} đơn hàng.", "success")
    if errors:
        err_samples = "; ".join([f"Dòng {e.get('row')}: {e.get('error')}" for e in errors[:3]])
        if len(errors) > 3:
            err_samples += f" (và {len(errors) - 3} lỗi khác)"
        flash(f"⚠️ Có {len(errors)} dòng lỗi: {err_samples}", "warning")

    return redirect(url_for("admin.orders_dashboard"))

