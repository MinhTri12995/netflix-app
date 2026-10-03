# Kế Hoạch Nâng Cấp Toàn Diện Dự Án Netflix App (Mục Tiêu: 10/10)

## 1. Tổng Quan & Mục Tiêu Dự Án
Dự án hiện tại là hệ thống quản lý, kiểm tra sống/chết (Checker/Scraper) và tự động phân phối mã truy cập (Access Key) tài khoản Netflix tích hợp xử lý khiếu nại U7BUY.
- **Hiện trạng:** Điểm đánh giá trung bình ~6.5/10 (Nghiệp vụ thực chiến tốt nhưng bảo mật kém do lộ mật khẩu, code monolithic 3900 dòng trong 1 file `web.py`, HTML inline, nguy cơ race condition dữ liệu).
- **Mục tiêu 10/10:** Biến hệ thống thành một nền tảng **Enterprise-Ready, High Security, Modular Clean Architecture, Modern Glassmorphism UI/UX, Real-time Dashboard và Automated Reliability**.

---

## 2. Bảng Phân Tích Hiện Trạng & Tiêu Chuẩn 10/10

| Hạng mục | Điểm Hiện Tại | Điểm Mục Tiêu | Thay Đổi Cốt Lõi Cần Thực Hiện |
| :--- | :---: | :---: | :--- |
| **Bảo mật (Security)** | 4.0/10 | **10/10** | Xóa toàn bộ hardcoded password/secret, băm mật khẩu Argon2/Werkzeug, CSRF Protection, Rate Limiting, HTTPOnly/Secure cookies. |
| **Kiến trúc Code (Architecture)** | 5.5/10 | **10/10** | Tách `web.py` (3900 dòng) thành Flask Blueprints chuẩn: `auth`, `portal`, `admin`, `api`, tách rời `templates/` Jinja2 và `static/`. |
| **Trải nghiệm UI/UX (Frontend)** | 6.5/10 | **10/10** | Giao diện Dark Cyber Glassmorphism cao cấp, bảng phân trang AJAX không reload, biểu đồ Chart.js thống kê thời gian thực, 1-click copy toast notification. |
| **Xử lý Dữ liệu & Concurrency** | 6.0/10 | **10/10** | Kích hoạt SQLite WAL Mode (`journal_mode=WAL`), cơ chế Mutex/Lock an toàn chống `database is locked`, tối ưu hóa query Supabase. |
| **Tự động hóa & Kháng lỗi (Reliability)** | 7.5/10 | **10/10** | Nâng cấp AI Vision Card Matcher, bọc Error Boundary toàn diện, tích hợp cảnh báo Telegram Bot khi kho sắp hết hàng hoặc lỗi đột biến. |

---

## 3. Kiến Trúc Hệ Thống Mới (Modular Blueprint Structure)

```
d:\đtb\
├── app/
│   ├── __init__.py               # Application Factory (create_app), cấu hình Extensions
│   ├── config.py                 # Quản lý cấu hình từ biến môi trường .env chặt chẽ
│   ├── extensions.py             # Khởi tạo CSRF, Limiter, Session
│   ├── blueprints/
│   │   ├── auth/                 # Xác thực Admin (Login, Logout, Hashing session)
│   │   ├── portal/               # Portal khách hàng (Nhập key, xem cookie, tải extension, khiếu nại)
│   │   ├── admin/                # Trang quản trị (Quản lý Keys, Accounts, Requests, Settings)
│   │   └── api/                  # RESTful API (Live check, Rotate, AI Vision Verify)
│   ├── services/
│   │   ├── account_service.py    # Nghiệp vụ quản lý tài khoản & gán access key
│   │   ├── checker_service.py    # Wrapper cho checker, proxy rotation, health check
│   │   ├── vision_service.py     # AI OCR & Đối soát thẻ thanh toán chống gian lận
│   │   └── notification_service.py # Gửi cảnh báo Telegram khi hết kho / lỗi
│   ├── templates/                # Template Jinja2 tách rời, layout kế thừa
│   │   ├── base.html             # Layout chung Dark Mode Glassmorphism
│   │   ├── auth/login.html
│   │   ├── portal/index.html
│   │   └── admin/
│   │       ├── dashboard.html    # Biểu đồ KPI real-time
│   │       ├── accounts.html     # Quản lý kho phim, lọc & phân trang AJAX
│   │       ├── keys.html         # Quản lý access keys, tạo hàng loạt
│   │       └── requests.html     # Xử lý khiếu nại & ảnh bằng chứng
│   └── static/
│       ├── css/style.css         # CSS tối ưu, không nhúng raw string trong Python
│       └── js/
│           ├── portal.js         # Xử lý copy 1-click, check live code, upload khiếu nại
│           └── admin.js          # Xử lý Chart.js, lọc AJAX, realtime status
├── checker.py                    # Module checker & chuẩn hóa gói
├── database.py                   # Lớp Hybrid SQLite WAL + Supabase
├── parser.py                     # Parser đa định dạng
├── proxies_list.py               # Quản lý danh sách proxy xoay vòng
├── auto_sync.py                  # Daemon theo dõi thư mục Auto_Import
├── run.py                        # Entry point chính gọn gàng
├── .env.example                  # Template biến môi trường an toàn
└── requirements.txt
```

---

## 4. Lộ Trình Triển Khai (Vertical Slices & Checkpoints)

### Giai đoạn 1: Bảo mật cốt lõi & Cấu hình môi trường (Hardening Foundation)
- [ ] Task 1.1: Tạo file cấu hình bảo mật `app/config.py` và `.env.example`, cô lập hoàn toàn credentials (SECRET_KEY, ADMIN_PASSWORD, SUPABASE_KEY).
- [ ] Task 1.2: Triển khai mã hóa/băm mật khẩu với `werkzeug.security` (scrypt/pbkdf2), nâng cấp cơ chế cookie session bảo mật (HttpOnly, SameSite, Secure).
- [ ] Task 1.3: Cấu hình SQLite WAL Mode (`PRAGMA journal_mode=WAL; PRAGMA busy_timeout = 5000;`) trong `database.py` để tránh lỗi khóa DB khi đa luồng.
- **Checkpoint 1:** Kiểm tra đăng nhập với hash mật khẩu, kiểm tra DB không còn bị lock khi chạy nhiều request đồng thời.

### Giai đoạn 2: Tái cấu trúc Module & Templates (Refactoring Monolith)
- [ ] Task 2.1: Xây dựng Application Factory `app/__init__.py` và chuyển dịch các template HTML từ string sang `app/templates/` với `base.html`.
- [ ] Task 2.2: Tách Blueprint `portal` (giao diện khách hàng nhập key, xem thông tin tài khoản, khiếu nại).
- [ ] Task 2.3: Tách Blueprint `auth` & `admin` (dashboard, quản lý kho tài khoản, quản lý mã truy cập, xử lý duyệt/từ chối khiếu nại).
- [ ] Task 2.4: Tách Blueprint `api` (các endpoint JSON: check live code, force rotate, OCR verify).
- **Checkpoint 2:** Chạy song song kiểm tra toàn bộ các luồng: Nhập key -> Cấp cookie; Admin đăng nhập -> Duyệt khiếu nại -> Tạo key; Đảm bảo 100% chức năng cũ hoạt động ổn định.

### Giai đoạn 3: Nâng cấp Trải nghiệm Giao diện UI/UX (10/10 Glassmorphism)
- [ ] Task 3.1: Hoàn thiện giao diện Customer Portal: Thiết kế thẻ tài khoản tương tác cao, hướng dẫn copy cookie 1-click với Toast thông báo chuyên nghiệp, modal khiếu nại kéo thả ảnh mượt mà.
- [ ] Task 3.2: Hoàn thiện Admin Dashboard: Tích hợp Chart.js hiển thị tỷ lệ Live/Hold/Die, biểu đồ phân bố gói (Premium/Standard/Ads), thống kê số lượng key sử dụng theo ngày.
- [ ] Task 3.3: Thêm phân trang và tìm kiếm AJAX cho bảng tài khoản (xử lý mượt mà ngay cả khi có hàng chục nghìn accounts).
- **Checkpoint 3:** Kiểm tra hiển thị responsive trên Mobile/Tablet/Desktop, tốc độ tải trang dưới 0.8s.

### Giai đoạn 4: Độ tin cậy, AI Vision & Cảnh báo Tự động (Reliability & Automation)
- [ ] Task 4.1: Tinh chỉnh logic AI Vision Card Matcher và Scraper: Tối ưu regex trích xuất thẻ ngân hàng, timeout 8s có fallback proxy, chống false-positive.
- [ ] Task 4.2: Tích hợp dịch vụ thông báo tự động (Telegram Bot Notification): Tự động ping Telegram khi:
  - Kho tài khoản Live sắp hết (dưới ngưỡng an toàn).
  - Có khiếu nại mới từ người mua.
  - Tỉ lệ tài khoản bị Hold/Die bất thường sau phiên quét tự động.
- [ ] Task 4.3: Tối ưu hóa `auto_sync.py` và background health checker: Xử lý ngoại lệ toàn diện, ghi log có cấu trúc (structured logging).
- **Checkpoint 4:** Kiểm tra kích hoạt khiếu nại mẫu -> Kiểm tra đối soát thẻ -> Kiểm tra thông báo gửi về Telegram.

---

## 5. Rủi Ro Kỹ Thuật & Giải Pháp Giảm Thiểu (Risks & Mitigations)

| Rủi ro | Mức độ | Biện pháp kiểm soát |
| :--- | :---: | :--- |
| **Gián đoạn dữ liệu khi chuyển đổi** | Cao | Giữ nguyên nguyên vẹn `accounts.db` và schema Supabase; tự động backup trước khi chạy. |
| **Netflix thay đổi cấu trúc trang thanh toán** | Trung bình | Cơ chế đa lớp: Scraper HTML -> Regex fallback -> AI Vision Matching -> Gán cờ duyệt thủ công nếu độ tin cậy < 80%. |
| **Quá tải request khi quét hàng loạt** | Trung bình | Áp dụng Worker Pool có giới hạn (concurrency limit) kết hợp Proxy SOCKS5 xoay vòng. |
