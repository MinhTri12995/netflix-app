# Củng cố xuất link và quản trị kho — 2026-10-09

## Thay đổi vận hành

- Xác minh trang tài khoản/payment trước khi xin token. Token hợp lệ chưa đủ để bỏ qua payment.
- HTTP lỗi, trang rỗng, host lạ, lỗi mạng và nội dung không nhận diện được là chưa xác minh; không tự đánh dấu hỏng hay đổi liên kết.
- Không dùng chuỗi cảnh báo trong script dịch thuật để kết luận payment. Không suy ra gói từ quảng cáo gói trong toàn bộ HTML hoặc mặc định Premium khi thiếu bằng chứng.
- Không coi ngày thanh toán cũ là bằng chứng tài khoản hỏng. Portal hiển thị hạn sử dụng của mã.
- Kiểm tra ứng viên trước khi đổi liên kết; chỉ commit khi có phiên và token hợp lệ, gói phù hợp. Hết kho hoặc ứng viên đều lỗi giữ liên kết ban đầu. Tài khoản dùng chung không bị xóa.
- Giao dịch khôi phục khóa và kiểm tra lại mã, trạng thái, gói, hạn và sức chứa; ghi sự kiện outbox trong cùng giao dịch. Timeout không tạo thêm lần đổi mù quáng.
- Trigger kiểm soát cấp mới/đổi liên kết bảo vệ sức chứa cả với các writer cũ. Chuyển sang chế độ riêng không ngắt mã hiện hữu.
- Tạo mã lưu trực tiếp gói đã chọn, gồm Standard/Ads/Basic với mã mới 16 ký tự.
- Đọc mã/tài khoản và lưu trạng thái Supabase thất bại không chuyển sang SQLite. Trang admin báo gián đoạn khi không tải được dữ liệu nguồn chính.

## Admin

Tổng quan phân biệt đã xác minh, chờ xác minh, cần xử lý và liên kết mất tài khoản. Kho/mã được lọc và phân trang ở database với thứ tự ổn định. Bộ lọc được giữ khi chuyển trang. Có kiểm tra từng tài khoản và cửa sổ mã bị ảnh hưởng/lịch sử 20 sự kiện gần nhất. Trạng thái ngừng cấp mới được giữ khi kiểm tra tài khoản đang hoạt động. Không thêm quản lý đơn hàng hoặc thay đổi tích hợp U7BUY.

## Migration và triển khai

1. Đối chiếu schema và tổng bản ghi. Giữ bản sao lưu vận hành hiện hữu; bản đối soát của đợt này chỉ chứa metadata, không lưu cookie.
2. Áp dụng `portal_activation_schema` trước, rồi `activation_recovery_admin`; migration trước mở rộng CHECK trạng thái legacy để chấp nhận `live`.
3. Migration mới thêm gói/version vào mã, backfill mã cũ theo quy tắc chiều dài cũ và gói tài khoản cho các mã không theo quy tắc đó. Không thu hồi mã cũ hoặc tự sửa liên kết mất tài khoản.
4. `system_config` lưu chế độ dùng chung tại Supabase. Giá trị khởi tạo True khớp cấu hình đã đối soát; triển khai nơi khác phải kiểm tra chế độ thực tế trước migration.
5. RPC và cấu hình chỉ cấp quyền backend `service_role`, SECURITY INVOKER với search_path cố định; frontend không gọi Supabase trực tiếp. Backend cần secret/service-role key đúng.
6. Cập nhật code, xác minh `X-App-Revision`, rồi thử code trên Portal và mở link trong trình duyệt. Kiểm tra admin với session thật.

## Bằng chứng kiểm thử và giới hạn

Kiểm thử hermetic bao gồm payment dù có token, lỗi mạng/HTTP, host giả, dịch thuật gây nhận diện nhầm, giữ liên kết khi hết kho, gói mã mới, không mở lại tài khoản ngừng cấp mới, 20 commit khôi phục đồng thời chỉ một sự kiện, phân trang/lọc admin và lỗi database.

PGlite chạy PostgreSQL thật trong môi trường tách biệt: kiểm tra chuỗi migration trạng thái legacy, áp dụng lặp lại, RPC không cho anon/authenticated, giới hạn sức chứa, giữ gói, gửi lại chỉ một sự kiện và trigger từ chối writer cũ cấp vượt giới hạn. PGlite không thay thế kiểm tra nhiều worker Render/PostgREST thực tế.

Tài khoản có thể phát sinh payment sau lúc xác minh; không thể cam kết không bao giờ có lỗi từ Netflix. Không quét toàn bộ kho trong đợt này. Các liên kết mất tài khoản đã có trước cần đối soát riêng. Lịch sử hiển thị chỉ gồm sự kiện đã lưu; không tái dựng các lần đổi cũ thiếu sự kiện.

Nếu kiểm tra sau triển khai thất bại, dừng mở cấp mới và xử lý nguyên nhân. Không xóa cột/bảng mới để hạ phiên bản. Bản trước chưa ghi plan khi tạo mã; hạ phiên bản cần giữ migration/trigger tương thích và đối soát cấu hình, dữ liệu phát sinh.
