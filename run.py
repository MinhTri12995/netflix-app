import os
import sys
from app import create_app
from app.config import Config

# Đảm bảo in tiếng Việt chuẩn trên Windows console
sys.stdout.reconfigure(encoding='utf-8')

app = create_app()

if __name__ == "__main__":
    port = Config.PORT
    print(f"🚀 [10/10] Netflix Access Platform is running on port {port}!")
    print(f"👉 Portal Khách Hàng: http://127.0.0.1:{port}")
    print(f"👉 Trang Quản Trị:    http://127.0.0.1:{port}/admin")
    app.run(host="0.0.0.0", port=port, debug=Config.DEBUG)
