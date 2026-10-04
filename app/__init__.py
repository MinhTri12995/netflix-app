import os
from flask import Flask, jsonify
from app.config import Config
import database

def create_app(config_class=Config):
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static"
    )
    app.config.from_object(config_class)

    # Đảm bảo CSDL SQLite được khởi tạo và kích hoạt WAL mode
    try:
        database.init_db()
    except Exception as e:
        print(f"Warning during init_db: {e}")

    # Đăng ký Blueprints theo từng phân hệ chức năng
    from app.blueprints.portal.routes import portal_bp
    from app.blueprints.auth.routes import auth_bp
    from app.blueprints.admin.routes import admin_bp
    from app.blueprints.api.routes import api_bp
    from app.services.csrf import init_csrf

    app.register_blueprint(portal_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(api_bp)

    # Kích hoạt bảo vệ CSRF cho toàn hệ thống
    init_csrf(app)

    @app.errorhandler(403)
    def handle_forbidden_error(e):
        return jsonify({
            "success": False,
            "error": str(e.description or "Forbidden: CSRF token missing or invalid.")
        }), 403

    @app.errorhandler(413)
    def handle_file_size_error(e):
        return jsonify({
            "success": False,
            "error": "File ảnh tải lên quá lớn (>10MB). Vui lòng nén hoặc chọn ảnh chụp màn hình dung lượng nhỏ hơn."
        }), 413

    @app.errorhandler(500)
    def handle_internal_error(e):
        return jsonify({
            "success": False,
            "error": "Hệ thống gặp sự cố tạm thời. Vui lòng thử lại sau giây lát."
        }), 500

    return app
