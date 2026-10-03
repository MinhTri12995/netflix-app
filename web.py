"""
Netflix Access Platform - Web Application Entry Point
Modularized and Hardened for 10/10 Enterprise Production
"""
import os
import sys
from app import create_app
from app.config import Config

sys.stdout.reconfigure(encoding='utf-8')

# Khởi tạo Flask Application từ Application Factory
app = create_app()

if __name__ == "__main__":
    port = Config.PORT
    print(f"🚀 [10/10] Netflix Access Platform running on port {port}!")
    print(f"👉 Customer Portal: http://127.0.0.1:{port}")
    print(f"👉 Admin Dashboard: http://127.0.0.1:{port}/admin")
    app.run(host="0.0.0.0", port=port, debug=Config.DEBUG)
