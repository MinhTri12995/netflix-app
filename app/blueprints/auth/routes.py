from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from functools import wraps
from app.config import Config
from app.services.rate_limiter import get_client_ip, check_rate_limit, reset_rate_limit

auth_bp = Blueprint("auth", __name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("auth.login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@auth_bp.route("/login", methods=["GET", "POST"])
@auth_bp.route("/admin/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        client_ip = get_client_ip(request)
        rate_key = f"login_fail:{client_ip}"
        allowed, wait_sec = check_rate_limit(rate_key, max_requests=5, window_seconds=900)
        if not allowed:
            flash(f"Quá nhiều lần đăng nhập thất bại từ IP của bạn. Vui lòng đợi {max(1, wait_sec // 60)} phút trước khi thử lại.", "error")
            return render_template("auth/login.html"), 429

        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if Config.verify_admin(email, password):
            reset_rate_limit(rate_key)
            session.clear()
            session["logged_in"] = True
            session["admin_email"] = email
            session.permanent = True
            flash("Đăng nhập quản trị thành công!", "success")
            next_url = request.args.get("next")
            if next_url and not next_url.startswith("//") and not next_url.startswith("http"):
                return redirect(next_url)
            return redirect(url_for("admin.dashboard"))
        else:
            flash("Tên đăng nhập hoặc mật khẩu không chính xác!", "error")

    return render_template("auth/login.html")

@auth_bp.route("/logout")
@auth_bp.route("/admin/logout")
def logout():
    session.clear()
    flash("Bạn đã đăng xuất khỏi hệ thống an toàn.", "info")
    return redirect(url_for("auth.login"))
