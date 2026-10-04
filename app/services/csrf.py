import os
import hmac
import secrets
from flask import session, request, abort, render_template

CSRF_SESSION_KEY = "_csrf_token"

def generate_csrf_token() -> str:
    """Tạo hoặc lấy CSRF token gắn liền với session hiện tại."""
    if CSRF_SESSION_KEY not in session:
        session[CSRF_SESSION_KEY] = secrets.token_hex(32)
    return session[CSRF_SESSION_KEY]

def validate_csrf_token(token: str) -> bool:
    """Xác thực token nhận được từ request so với token trong session."""
    session_token = session.get(CSRF_SESSION_KEY) or session.get("csrf_token")
    if not session_token or not token:
        return False
    return hmac.compare_digest(session_token, token)

def init_csrf(app):
    """
    Kích hoạt bảo vệ CSRF cho toàn bộ ứng dụng Flask.
    - Tự động inject biến csrf_token() vào Jinja2 template context.
    - Kiểm tra CSRF cho mọi request POST/PUT/DELETE/PATCH trên các route yêu cầu xác thực Admin.
    """
    @app.context_processor
    def inject_csrf_token():
        return dict(csrf_token=generate_csrf_token)

    @app.before_request
    def check_csrf():
        # Chỉ kiểm tra trên các HTTP method thay đổi trạng thái
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return

        # Chỉ áp dụng kiểm tra bắt buộc CSRF cho các route Admin hoặc khi gọi các API quản trị
        # Các API công khai của người dùng (kích hoạt mã, chat AI, báo cáo đổi mã) dùng rate-limit riêng
        is_admin_route = (
            request.path.startswith("/admin")
            or request.path in ("/login", "/logout")
            or request.path.startswith("/api/check_and_import")
        )
        if not is_admin_route:
            return

        # Trừ route API check_and_import nếu dùng token xác thực riêng (nếu có)
        if request.path.endswith("/check_and_import") and request.headers.get("X-API-Key"):
            return

        # Lấy token từ form data hoặc request header
        token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")

        if not token or not validate_csrf_token(token):
            abort(403, description="CSRF token missing or invalid. Please refresh the page and try again.")
