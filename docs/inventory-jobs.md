# Kiểm tra kho và giới hạn chia sẻ

Chế độ chia sẻ: một tài khoản tối đa hai mã, mỗi mã vẫn chỉ gắn một tài khoản. Chế độ riêng: một mã. Giữ các liên kết cũ vượt giới hạn, chỉ chặn cấp thêm. Bộ đếm dashboard chuẩn hóa tên gói đã lưu; tên chưa nhận diện vào nhóm riêng, không tự tính Premium. Code đếm theo gói đã lưu, chỉ dùng độ dài cho mã cũ chưa có gói. Bộ đếm không chứng minh tài khoản còn hoạt động; xem trạng thái kiểm tra riêng.

## Các nút quản trị

- **CHECK ALL**: kiểm tra lại toàn kho, gồm gói hiện tại và lỗi thanh toán.
- **SCAN PAYMENT ERRORS**: kiểm tra trạng thái thanh toán, giữ gói đã lưu.
- **UPDATE MISSING PLANS**: chỉ kiểm tra những tài khoản chưa xác định gói.
- **FILTER DUPLICATES**: giữ tài khoản có mã tham chiếu, kể cả liên kết cũ chứa nhiều email; chỉ xóa bản trùng không được tham chiếu.
- **Recheck & dọn tài khoản lỗi**: chỉ chọn tài khoản cần kiểm tra/hết phiên. Phải xác nhận lỗi hai lần, cách nhau 5 giây, mới xóa tài khoản không còn mã tham chiếu. Tài khoản còn mã, lỗi mạng/chưa rõ, cookie đã thay hoặc trạng thái đã phục hồi được giữ. Kết quả LIVE phục hồi trạng thái và giữ gói đã lưu.
- **Nhập tệp/thư mục**: gửi danh sách lên máy chủ và theo dõi chung. Chỉ nhập khi xác minh hoạt động và nhận diện được gói; dữ liệu không rõ không tự gán Premium. Giữ thư mục gốc để nhập lại những dòng chưa xác minh.

Mỗi tác vụ có tiến trình, tổng đã xử lý, kết quả gần nhất và lịch sử. Chỉ có một tác vụ kho đang chạy; thao tác thêm được báo đang bận, không nhập âm thầm danh sách mới. Có thể tải lại hoặc rời trang sau khi danh sách được lưu thành công. Lịch sử hiển thị 10 tác vụ gần nhất, mỗi tác vụ 20 kết quả gần nhất; tất cả kết quả từng dòng vẫn được lưu trong cơ sở dữ liệu.

## Bảo vệ dữ liệu

Công tắc **Premium 15 ký tự → Standard dự phòng** chỉ áp dụng mã Premium dài đúng 15 ký tự. Ưu tiên tài khoản Premium còn chỗ trước Standard thường; không dùng Basic hoặc Standard có quảng cáo. Tắt công tắc chặn cấp/đổi mới sang Standard, giữ liên kết đã có. Gói tài khoản thực tế vẫn là Standard, gói mã vẫn là Premium. Mã mới tối thiểu 16 ký tự không thuộc công tắc này.

Gói lấy từ thông tin thành viên hiện tại, không lấy từ quảng cáo nâng cấp. Chuỗi Unicode được giữ nguyên; gói không nhận diện được giữ dữ liệu cũ. Lỗi mạng/proxy/HTTP không xác định không đổi liên kết. Tài khoản xác nhận lỗi chuyển `needs_review`; không xóa tài khoản khách đang dùng. Tài khoản admin đã ngừng cấp mới không bị tự mở lại.

`inventory_runs` và `inventory_items` là nguồn tiến trình trong Supabase, không dùng SQLite dự phòng khi dịch vụ lỗi. Cả hai bảng bật RLS và chỉ service_role có quyền. Endpoint tiến trình chỉ dành cho admin, không trả cookie hay lease token. Payload cookie nhập kho nằm trong bảng riêng có quyền hạn chế, được xóa khỏi tác vụ sau khi xử lý xong; cookie tài khoản hoạt động vẫn được lưu trong kho hiện hữu.

Worker chạy trong tiến trình ứng dụng, tối đa ba tài khoản xử lý đồng thời trên toàn bộ worker. Khóa nhận việc ở database; lease 180 giây, tối đa ba lần nhận việc. Lỗi không xác định được thử lại sau 15 giây. Worker cũ không được ghi sau khi hết lease; kết quả của cookie đã bị thay cũng không ghi đè dữ liệu mới. Ghi trạng thái, gói và hoàn tất dòng trong cùng giao dịch. Không giữ khóa database trong lúc gọi Netflix.

Khởi động lại tự nhận tác vụ còn dở; Gunicorn có hook hỗ trợ preload. `DISABLE_ADMIN_WORKER=1` chỉ dùng khi cần dừng nhận việc hoặc trong kiểm thử. Khi tắt biến này, việc chờ tiếp tục xử lý mà không cần tạo tác vụ mới.

## Triển khai và xác minh

Áp dụng migration `inventory_jobs` trước triển khai mã mới. Migration chỉ tạo cấu trúc và hàm, không tự quét hoặc sửa kho. Rollback mã ứng dụng không xóa lịch sử hay payload tác vụ; dừng nhận việc bằng biến cấu hình trước nếu cần bảo trì. Không xóa các bảng khi còn tác vụ đang chạy.

Kiểm thử: chạy `python scripts/test_local.py`; chạy hai chương trình trong `tests/migrations/` với runtime PGlite 0.5.8. Bộ kiểm thử gồm tranh nhận việc giữa hai worker, lease cũ, đổi cookie giữa lúc kiểm tra, retry hữu hạn, bảo vệ liên kết, quyền đọc tiến trình, CSRF, nhập không rõ gói và biên dịch JavaScript từ dashboard đã render.

Kiểm thử giao dịch cục bộ không thay thế kiểm tra tải trên nhiều worker Render thật. Không tự khởi động quét toàn kho sản xuất để thử triển khai; admin chủ động bấm CHECK ALL và theo dõi kết quả trên website.
