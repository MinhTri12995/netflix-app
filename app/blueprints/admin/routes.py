import secrets
import string
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify, session

import database
import parser
import checker
from app.blueprints.auth.routes import login_required
from app.services.notification_service import send_telegram_alert

admin_bp = Blueprint("admin", __name__)

@admin_bp.route("/")
@admin_bp.route("/dashboard")
@login_required
def dashboard():
    database.init_db()

    search_email = request.args.get("search_email", "").strip().lower()
    search_code = request.args.get("search_code", "").strip().upper()

    from app.services.admin_inventory_service import inventory_page, inventory_summary
    account_status = request.args.get('account_status','')
    inventory_plan = request.args.get('inventory_plan','')
    try:
        stats = inventory_summary()
        keys_page = inventory_page('codes',request.args.get('key_page',1),search=search_code,plan=inventory_plan)
        accounts_page = inventory_page('accounts',request.args.get('acc_page',1),search=search_email,status=account_status,plan=inventory_plan)
    except Exception as exc:
        current_app.logger.warning('Admin inventory unavailable (%s)',type(exc).__name__)
        return render_template('admin/unavailable.html'),503
    accounts, access_keys = accounts_page['rows'],keys_page['rows']
    key_page, key_total_pages = keys_page['page'],keys_page['pages']
    acc_page, acc_total_pages = accounts_page['page'],accounts_page['pages']

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
        current_proxy = "p.webshare.io:9999"

    share_mode_enabled = database.get_config("SHARE_MODE_ENABLED", False)
    mix_plan_enabled = database.get_config("MIX_PREMIUM_STANDARD", False)

    return render_template(
        "admin/dashboard.html",
        accounts=accounts,
        access_keys=access_keys,
        total_accounts=stats['accounts']['total'],
        account_status=account_status,
        inventory_plan=inventory_plan,
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


@admin_bp.route('/accounts/<path:email>/details')
@login_required
def account_details_route(email):
    from app.services.admin_inventory_service import account_details
    try:
        return jsonify(account_details(email))
    except Exception:
        return jsonify({'error':'Không thể tải dữ liệu lúc này.'}),503


@admin_bp.route('/accounts/<path:email>/check',methods=['POST'])
@login_required
def check_account_route(email):
    try:
        acc = database.get_account_by_email(email)
        if not acc:
            flash('Không tìm thấy tài khoản.','error')
        else:
            status, plan = checker.check_account_live(acc[2],acc[3] or '',check_payment=True)
            if status == 'LIVE':
                saved = True if acc[6] == 'blocked_for_new_assignments' else database.mark_account_live(email)
                if not saved:
                    raise RuntimeError('Status not saved')
                if plan and plan != 'VALID':
                    database.update_plan(email,plan)
                flash('Đã xác minh tài khoản hoạt động.','success')
            elif status == 'DIE':
                if not database.update_account_status(email,'needs_review'):
                    raise RuntimeError('Status not saved')
                flash('Tài khoản cần kiểm tra. Các mã hiện tại được giữ nguyên.','warning')
            else:
                flash('Chưa xác minh được do lỗi dịch vụ hoặc mạng; giữ nguyên trạng thái.','warning')
    except Exception as exc:
        current_app.logger.warning('Account check unavailable (%s)',type(exc).__name__)
        flash('Không thể kiểm tra hoặc lưu kết quả lúc này.','error')
    return redirect(url_for('admin.dashboard',search_email=email))

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
    database.init_db()
    from app.services.allocation_service import replace
    mode = (request.form.get("mode") or request.args.get("mode") or "").strip().lower()
    delete_param = request.form.get("delete_old") or request.args.get("delete_old")
    if mode == "delete" or str(delete_param).lower() in ("1", "true", "yes"):
        delete_old = True
    elif mode == "keep" or str(delete_param).lower() in ("0", "false", "no"):
        delete_old = False
    else:
        delete_old = None

    admin_user = session.get("user", "admin")
    del_label = "xóa khỏi kho" if delete_old is True else "giữ lại trong kho" if delete_old is False else "tự động"
    res = replace(
        code=code,
        actor=f"admin:{admin_user}",
        reason=f"Admin manual rotation ({del_label})",
        delete_old_account=delete_old,
        ignore_quota=True
    )
    if res.is_success:
        flash(f"✅ {res.message}", "success")
    else:
        flash(f"❌ Lỗi đổi tài khoản: {res.message}", "error")
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/request_change", methods=["POST"])
@login_required
def admin_request_change():
    database.init_db()
    from app.services.allocation_service import replace

    code = (request.form.get("code") or (request.json.get("code") if request.is_json else "") or "").strip().upper()
    mode = (request.form.get("mode") or (request.json.get("mode") if request.is_json else "") or "keep").strip().lower()
    reason_cat = (request.form.get("reason_category") or (request.json.get("reason_category") if request.is_json else "") or "").strip()
    note = (request.form.get("note") or (request.json.get("note") if request.is_json else "") or "").strip()

    is_ajax = request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in request.headers.get("Accept", "")

    if not code:
        if is_ajax:
            return jsonify({"success": False, "error": "Vui lòng nhập Access Code!"}), 400
        flash("❌ Vui lòng nhập Access Code!", "error")
        return redirect(url_for("admin.dashboard"))

    key_row = database.get_access_key(code)
    if not key_row:
        if is_ajax:
            return jsonify({"success": False, "error": f"Không tìm thấy mã truy cập '{code}' trong hệ thống!"}), 404
        flash(f"❌ Không tìm thấy mã truy cập '{code}' trong hệ thống!", "error")
        return redirect(url_for("admin.dashboard"))

    # Mode 1: keep (đổi acc, giữ acc cũ trong kho) -> delete_old_account=False
    # Mode 2: delete (đổi acc và xóa acc cũ ra lists) -> delete_old_account=True
    delete_old = True if mode == "delete" else False

    reason_parts = []
    if reason_cat:
        reason_parts.append(f"[{reason_cat}]")
    if note:
        reason_parts.append(note)
    full_reason = "Admin Request Change: " + (" ".join(reason_parts) if reason_parts else f"Chế độ: {'Xóa acc cũ' if delete_old else 'Giữ acc cũ'}")

    admin_user = session.get("user", "admin")
    op_id = f"admin_req_change_{code}_{int(datetime.now().timestamp())}"

    res = replace(
        code=code,
        actor=f"admin:{admin_user}",
        reason=full_reason,
        delete_old_account=delete_old,
        ignore_quota=True,
        operation_id=op_id
    )

    if res.is_success:
        if is_ajax:
            return jsonify({
                "success": True,
                "message": res.message,
                "assigned_email": res.assigned_email,
                "code": code,
                "mode": mode,
                "deleted_old": delete_old
            })
        flash(f"✅ {res.message}", "success")
        return redirect(url_for("admin.dashboard"))
    else:
        err_msg = res.message or "Đổi tài khoản không thành công."
        if is_ajax:
            return jsonify({"success": False, "error": err_msg, "code": code}), 400
        flash(f"❌ Lỗi: {err_msg}", "error")
        return redirect(url_for("admin.dashboard"))

@admin_bp.route("/api/key_info/<code>", methods=["GET"])
@login_required
def api_key_info(code):
    database.init_db()
    from app.services.allocation_service import get_plan_for_code
    code_clean = (code or "").strip().upper()
    key_row = database.get_access_key(code_clean)
    if not key_row:
        return jsonify({"success": False, "error": f"Không tìm thấy Access Code: {code_clean}"}), 404

    assigned_email = key_row[1] if len(key_row) > 1 and key_row[1] else ""
    expire_at_str = key_row[2] if len(key_row) > 2 and key_row[2] else ""
    plan = get_plan_for_code(code_clean)
    rotations_today = database.get_today_rotation_count(code_clean)

    is_expired = False
    if expire_at_str and expire_at_str != "Lifetime":
        try:
            exp_dt = datetime.strptime(expire_at_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            if datetime.now() > exp_dt:
                is_expired = True
        except Exception:
            pass

    return jsonify({
        "success": True,
        "key": {
            "code": code_clean,
            "assigned_email": assigned_email or "Chưa gán tài khoản",
            "expire_at": expire_at_str or "Lifetime",
            "plan": plan,
            "today_rotations": rotations_today,
            "is_expired": is_expired
        }
    })

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
        return queue_inventory_task('import', accounts_list)
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
    new_mode = request.form.get('enabled') == 'true'
    if database.set_config("MIX_PREMIUM_STANDARD", new_mode):
        flash("Đã " + ("BẬT" if new_mode else "TẮT") + " Standard dự phòng cho code Premium 15 ký tự. Liên kết hiện hữu được giữ nguyên.", "success")
    else:
        flash("Không thể lưu công tắc. Cấu hình trên máy chủ chưa được cập nhật.", "error")
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/toggle_share_mode", methods=["POST"])
@login_required
def toggle_share_mode():
    current_mode = database.get_config("SHARE_MODE_ENABLED", False)
    new_mode = not current_mode
    database.set_config("SHARE_MODE_ENABLED", new_mode)
    status_str = "BẬT" if new_mode else "TẮT"
    flash(f"✅ Đã {status_str} chế độ chia sẻ (1 tài khoản tối đa 2 mã).", "success")
    return redirect(url_for("admin.dashboard"))

def queue_inventory_task(kind, records=None):
    from app.services.inventory_jobs import enqueue, start_worker
    try:
        job = enqueue(kind, records)
        start_worker(current_app._get_current_object())
        flash("Đã lưu tác vụ. Theo dõi tiến trình bên dưới; có thể tải lại hoặc rời trang." if not job['existing'] else "Đang có tác vụ chạy. Tiến trình hiện tại được hiển thị bên dưới.", "warning")
    except Exception as exc:
        current_app.logger.warning('Cannot queue inventory task (%s)', type(exc).__name__)
        flash("Không thể lưu tác vụ lúc này. Vui lòng thử lại.", "error")
    return redirect(url_for('admin.dashboard', _anchor='inventory-progress'))


@admin_bp.route("/check_all", methods=["POST"])
@login_required
def check_all():
    return queue_inventory_task('missing_plans')


@admin_bp.route("/force_check_all", methods=["POST"])
@login_required
def force_check_all():
    return queue_inventory_task('full_scan')


@admin_bp.route("/check_payment", methods=["POST"])
@login_required
def check_payment_route():
    return queue_inventory_task('payment_scan')


@admin_bp.route("/recheck_cleanup", methods=["POST"])
@login_required
def recheck_cleanup():
    return queue_inventory_task('cleanup')


@admin_bp.route("/filter_duplicates", methods=["POST"])
@login_required
def filter_duplicates():
    return queue_inventory_task('duplicates')


@admin_bp.route("/jobs/import", methods=['POST'])
@login_required
def queue_import():
    from app.services.inventory_jobs import enqueue, start_worker
    try:
        job = enqueue('import', (request.get_json(silent=True) or {}).get('accounts'))
        if job['existing']:
            return jsonify(error='Đang có tác vụ chạy. Đợi hoàn tất rồi nhập lại thư mục.', id=job['id']), 409
        start_worker(current_app._get_current_object())
        return jsonify(success=True, id=job['id']), 202
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except Exception as exc:
        current_app.logger.warning('Cannot queue import (%s)', type(exc).__name__)
        return jsonify(error='Không thể lưu danh sách nhập. Vui lòng giữ thư mục và thử lại.'), 503


@admin_bp.route("/jobs/progress")
@login_required
def inventory_job_progress():
    from app.services.inventory_jobs import progress
    try:
        response = jsonify(progress(request.args.get('id')) or {'run': None})
        response.headers['Cache-Control'] = 'no-store'
        return response
    except Exception as exc:
        current_app.logger.warning('Inventory progress unavailable (%s)', type(exc).__name__)
        return jsonify(error='Chưa tải được tiến trình. Kết quả đã lưu sẽ được tải lại.'), 503


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

    if req.get("status") in ["accepted", "rejected", "deleted"]:
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

