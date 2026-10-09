# Kết quả kiểm chứng xuất link và admin — 09/10/2026

## Bản chức năng đã kiểm chứng

- Bản chức năng đã lên GitHub main và Render: `e5cea4045428cebe932ea66a3b29f8867717f28d`. Bản cập nhật tiếp theo chỉnh nhãn sức chứa, bỏ lựa chọn trộn gói trên giao diện và bổ sung báo cáo này.
- Health check HTTPS trả 200, `X-App-Revision` khớp commit trên.
- Supabase đã áp dụng migration `20261009085619_activation_recovery_admin`.
- Đối soát sau migration: 1.900 tài khoản, 631 mã. Không tự xóa hoặc sửa hàng loạt liên kết cũ.

## Kiểm chứng đạt

- 184 kiểm thử local đạt, không gọi dịch vụ thật trong bộ kiểm thử mặc định.
- PostgreSQL tách biệt: nâng cấp schema cũ, áp dụng migration lặp, hạn chế quyền RPC, giữ đúng gói, chặn cấp vượt sức chứa và gửi lại chỉ ghi một sự kiện.
- 20 thao tác khôi phục đồng thời trong SQLite chỉ tạo một sự kiện đổi.
- Portal thật: mã do người dùng cung cấp trả link PC, Mobile, TV và tài khoản có token.
- Link PC mở được màn hình chọn hồ sơ Netflix. Netflix còn hiển thị lời nhắc thành viên phụ; không coi lời nhắc này là bằng chứng payment.
- Portal vẫn trả 200 và xuất đủ link khi cùng phiên đã đăng nhập admin, có token CSRF.
- Admin thật: đăng nhập thành công; dashboard, lọc trạng thái, trang kho thứ hai và endpoint mã/lịch sử đều trả 200. Trang đầu có 50 nút xem mã/lịch sử, tải stylesheet mới.
- Endpoint mã/lịch sử trả đúng cấu trúc, không chứa cookie hoặc Netflix IDs.

## Phần chưa xác minh và dữ liệu cần xử lý

- Chưa kiểm tra trực quan/click toàn bộ giao diện admin trong trình duyệt có phiên đăng nhập; kiểm chứng admin thật ở trên thực hiện qua HTTP.
- 213 mã mất liên kết đã tồn tại trước bản sửa. Dashboard hiển thị cảnh báo; cần đối soát riêng trước khi xử lý khách bị ảnh hưởng.
- Chưa chạy kiểm tra tải đồng thời trên hai worker Render/PostgREST thực tế; kiểm thử giao dịch PostgreSQL tách biệt không thay thế kiểm tra này.
- Không quét hoặc chứng nhận toàn bộ 1.900 tài khoản. Tài khoản vẫn có thể bị Netflix thay đổi trạng thái sau lúc xác minh.
- Kiểm tra trực tiếp bằng cookie qua tham số công cụ bị bộ duyệt tự động từ chối vì nguy cơ lộ bí mật; đã thay bằng kiểm tra Portal bình thường, không ghi cookie/token ra báo cáo.

Chi tiết thay đổi và hướng dẫn vận hành: [activation-admin-hardening.md](activation-admin-hardening.md).
