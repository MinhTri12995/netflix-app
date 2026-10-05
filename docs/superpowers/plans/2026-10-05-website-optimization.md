# Website Optimization Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking. Tài liệu này là đề xuất triển khai; phiên đánh giá hiện tại chỉ bàn giao báo cáo và kế hoạch.

**Goal:** Cấp/đổi đúng dữ liệu và đúng hạn mức, kiểm soát tự duyệt, hoàn thiện trải nghiệm và có bằng chứng nghiệm thu vận hành.

**Architecture:** Giữ Flask, blueprint và Jinja. Supabase/PostgreSQL là nguồn dữ liệu nghiệp vụ; giao dịch DB giải quyết sức chứa, đổi và chống trùng. AI/Netflix chạy trước bước commit, thông báo chạy sau commit qua outbox; tác vụ nền có lease dùng chung.

**Tech Stack:** Python, Flask, Supabase/PostgreSQL, Jinja/CSS/JavaScript; SQLite chỉ dev/test; thư viện giải mã ảnh được khóa phiên bản khi triển khai.

**Spec:** [Báo cáo và yêu cầu mục tiêu](D:/đtb/project-review-comprehensive-2026-10-05.md), đối chiếu kế hoạch người dùng đã chốt trong hội thoại. Baseline: `e4b8085`.

## Global Constraints

- Không push, không tạo PR hoặc tự triển khai production. Khi thực thi, thay đổi giữ cục bộ để kiểm tra.
- Supabase là nguồn chính; mất kết nối dừng cấp, đổi và nhập. Không fallback SQLite ở production.
- Chế độ riêng: một mã/tài khoản. Chia sẻ: tối đa bốn mã Premium, hai mã gói khác. Chuyển sang riêng giữ khách cũ, chặn cấp thêm tài khoản đã vượt giới hạn.
- Mã mới ít nhất 16 ký tự, dùng CSPRNG; gói lưu riêng. Mã cũ còn hiệu lực tiếp tục sử dụng.
- Chỉ tự duyệt screen-limit khi có đơn đã xác minh, ảnh hợp lệ/khớp tài khoản và đủ điều kiện giao dịch. Payment/OTHER chuyển admin.
- Giữ ngưỡng hiện có: tối đa năm lần đổi trong 24 giờ; các giới hạn gửi/kiểm tra hiện hành giữ giá trị, chuyển sang kho dùng chung. Không để đường admin/activation bypass hạn mức đổi.
- Không giữ khóa DB khi gọi Netflix/AI/Telegram. Không xóa tài khoản còn liên kết.
- Không sử dụng dữ liệu khách hoặc dịch vụ thật trong test mặc định. Kiểm thử PostgreSQL/tích hợp thật phải dùng môi trường riêng.
- Không tự sửa lịch sử Git hoặc tuyên bố bí mật đã thu hồi; chủ hệ thống xác nhận bước này.

## Review Focus

1. Timeout sau commit: cùng operation ID trả kết quả đã lưu, không đổi thêm lần nữa — Task 3/4.
2. AI kiểm tra ảnh của liên kết cũ nhưng liên kết đổi trước commit: đưa yêu cầu về xác minh lại — Task 4/5.
3. Kho có tài khoản đang bị khóa giao dịch: không kết luận mất kho vĩnh viễn hoặc xóa liên kết — Task 3.
4. Import chỉ ghi được một phần và gửi lại: giữ dòng lỗi, không ghi trùng hay ghi đè verified bằng UNKNOWN — Task 6.
5. Admin session, nhiều worker và restart xảy ra trong một luồng khách: giữ CSRF, hạn mức và trạng thái đúng — Task 2/7/8.

## Cấu trúc file và giao diện dùng chung

Các file hiện có được sửa trong từng task bên dưới. Tạo các đơn vị nhỏ theo trách nhiệm:

- `app/services/business_result.py`: `OperationResult(status, operation_id, request_id, assigned_email, retryable, detail_code)`; status ∈ `success`, `out_of_stock`, `already_processed`, `limit_exceeded`, `temporarily_unavailable`, `needs_review`, `invalid_input`.
- `app/services/allocation_service.py`: `allocate(code, plan, expire_at, operation_id) -> OperationResult`; `replace(request_id, actor, operation_id, expected_assignment_version=None) -> OperationResult`; `lookup_operation(operation_id) -> OperationResult | None`.
- `app/services/order_service.py`: `verify_order(order_id, code, verified_at, actor) -> OperationResult`; `can_auto_approve(order_id, code) -> bool`. Không biến lỗi DB thành False rồi vẫn tự duyệt.
- `app/services/evidence_service.py`: `validate_image(blob) -> ValidatedImage`; `evaluate_evidence(ai_payload, assigned_email) -> EvidenceDecision`; schema sai hoặc thiếu liên hệ tài khoản → needs_review.
- `app/services/import_service.py`: `import_accounts(records, import_id) -> ImportResult`, gồm tổng và kết quả từng dòng.
- `app/services/job_service.py` và `app/services/outbox_service.py`: nhận việc có lease, hoàn tất/retry và gửi thông báo sau commit.
- `tests/`: pytest fixture, hồi quy offline; `tests/integration/`: PostgreSQL riêng; `tests/browser/`: kịch bản toàn luồng; `.github/workflows/tests.yml`: chạy từ clone sạch.
- `supabase/migrations/`: migration do CLI sinh tên bằng `supabase migration new`; không tạo bảng bằng script startup làm thay migration.
- `docs/operations/`: cấu hình, đối soát, backup/restore và nghiệm thu.

## Task 1: Khoanh vùng tự duyệt và hàng chờ

**Files:** sửa `app/blueprints/portal/routes.py`, `app/blueprints/admin/routes.py`, `database.py`, `app/config.py`; tạo `tests/test_approval_guards.py`.

**Interfaces:** chưa cần API mới; chuẩn hóa request `status=pending/accepted/rejected`, thêm `blocked_reason` để phân biệt out_of_stock/card_mismatch/insufficient_evidence. Dữ liệu trạng thái cũ được giữ/đọc tương thích tới Task 3.

- [x] Viết test: AI OTHER + khách chọn TOO_MANY_PEOPLE không gọi rotate; PAYMENT_ERROR thiếu bằng chứng không tự đổi; tất cả trạng thái pending_* cũ hiện trong hàng chờ.
- [x] Chạy từng test, xác nhận thất bại đúng lỗi và handler được gọi.
- [x] Loại bỏ điều kiện tự duyệt từ reason_category; dùng cờ tắt auto-approval mặc định tới khi Task 5 đạt. Đưa payment về manual; không trả “đã đổi” khi save False.
- [x] Sửa truy vấn/guard cho dữ liệu chờ cũ; hiển thị lý do chặn. Bỏ xóa tài khoản cũ trong đường đổi một khách, kể cả activation/live-check.
- [x] Chạy lại guard và shared-account regression; bàn giao thay đổi cục bộ. Giai đoạn này là khoanh vùng, chưa chứng nhận giao dịch an toàn.

## Task 2: Bộ kiểm thử có thể tái lập

**Files:** tạo `tests/conftest.py`, `tests/test_regression_safety.py`, `pytest.ini`, `.github/workflows/tests.yml`, phụ thuộc kiểm thử có phiên bản; chuyển các bài giữ lại từ scratch vào tests.

**Interfaces:** fixture `app`, `client`, `admin_client` sử dụng `logged_in`, CSRF hợp lệ, DB tạm và cấu hình test; mặc định từ chối network.

- [x] Viết kiểm tra chứng minh accept handler được gọi với auth/CSRF đúng; auth sai/token sai bị chặn. Giữ positive regression Portal có admin session.
- [x] Chuyển 15 phép tái hiện bất an toàn sang assert hành vi an toàn, nhóm theo service. Không dùng assertion “bad behavior exists” làm nghiệm thu.
- [x] Chuyển Phase A về pytest/unittest discover; bỏ fixture bảo vệ sai ở Phase B; các bài giữ lại phải được Git theo dõi.
- [x] Chạy `python -m pytest tests -q` / `python -m unittest discover tests`; ban đầu ghi danh sách fail. Sau các task, tất cả bài bắt buộc đạt; integration chỉ skip khi không có DB test và phải chạy trong cửa staging riêng.
- [x] CI cài từ clone sạch, không cần scratch/ hoặc .env cá nhân, không tiếp xúc dịch vụ thật. Phân biệt test đơn vị, DB integration và browser trong báo cáo.

## Task 3: Nguồn dữ liệu, migration và cấp nguyên tử

**Files:** sửa `database.py`, `init_supabase.py`, `app/config.py`, `app/blueprints/admin/routes.py`; tạo `business_result.py`, `allocation_service.py`, migration, `tests/test_authoritative_store.py`, `tests/integration/test_capacity.py`, `docs/operations/reconciliation.md`.

**Consumes/produces:** tạo OperationResult và `allocate`, `lookup_operation`; replace được hoàn tất Task 4. Legacy wrapper trong database chuyển sang service, không ghi hai nguồn.

- [x] Test cloud save thất bại → temporarily_unavailable, không ghi SQLite; timeout tra cùng operation ID. Test mã legacy và mã mới có explicit plan.
- [x] Lập báo cáo read-only liên kết mồ côi, tài khoản vượt sức chứa, mã/gói/expiry không hợp lệ và khác biệt giữa hai nguồn. Không tự sửa dòng chưa xác định.
- [x] Tạo migration versioned: plan, account status, assignment version, operation record, request blocked_reason, events/outbox/orders/jobs/limits; khóa ngoại bảo vệ liên kết. Backfill gói mã cũ theo quy tắc hiện hành, giữ nguyên code; expiry bất thường báo để đối soát.
- [x] Cấp trong một transaction với khóa tài khoản và kiểm tra liên kết đang hiệu lực; không chỉ SELECT đếm rồi INSERT rời. Cùng operation ID ràng buộc với cùng payload; khác payload bị từ chối.
- [x] Tạo mã mới CSPRNG ít nhất 16 ký tự, cập nhật mọi đường đọc/generate để dùng plan. Chuyển share→solo chặn cấp thêm mà giữ khách đang dùng.
- [x] Chạy capacity integration: 20 request sức chứa 1/2/4 chỉ thành công 1/2/4; còn một chỗ chỉ một thành công. Kiểm tra khóa tạm thời và retry, không báo hết kho sai do tranh khóa.
- [x] Nâng dữ liệu legacy trên staging, đối soát trước/sau và thử rollback/restore trước khi cho phép ghi production.

## Task 4: Đổi đúng một lần và bảo vệ mọi đường đổi

**Files:** hoàn thiện `allocation_service.py`, sửa admin/portal routes và `token_service.py`; tạo `outbox_service.py`, `tests/integration/test_replacement.py`, `tests/test_replacement_paths.py`.

**Interfaces:** `replace(request_id, actor, operation_id, expected_assignment_version)` kiểm tra request, expiry, hạn mức, sức chứa và phiên bản liên kết rồi commit một lần; mọi đường admin/AI/activation/live-check gọi chung.

- [x] Test 20 lần accept cùng request tạo một event/một lần đổi; lần sau trả same result. Hết kho/lỗi ghi giữ link cũ và trạng thái pending.
- [x] Gộp khóa request và mã, hạn mức năm lần/24h, chọn replacement, cập nhật link, event, request và outbox trong một transaction. Kiểm tra AI evidence chưa bị cũ so với assignment_version.
- [x] Không DELETE toàn tài khoản khi đổi một khách; đánh dấu needs_review khi chưa rõ, blocked_for_new_assignments khi có bằng chứng hỏng và liệt kê khách bị ảnh hưởng.
- [x] Activation/live-check phát hiện lỗi phải tạo yêu cầu/thao tác ổn định trước khi gọi replace; phân biệt lỗi proxy/mạng với CookieError. Không xóa trước khi tìm kho.
- [x] Gửi notification ngoài transaction; lỗi Telegram retry từ outbox, không đảo link. Mỗi event chỉ có một outbox entry tương ứng.
- [x] Chạy shared-account, admin quota, AI quota, timeout-after-commit và notification failure regression trên DB riêng.

## Task 5: Checker, đơn verified và bằng chứng AI

**Files:** sửa `checker.py`, `token_service.py`, `portal/routes.py`, `admin/routes.py`, `vision_service.py`; tạo `order_service.py`, `evidence_service.py`, `app/templates/admin/orders.html`, `tests/test_checker.py`, `tests/test_evidence.py`, `tests/test_orders.py`.

**Interfaces:** checker trả LIVE/DIE/UNKNOWN với plan có thể null; evidence payload phải có error_type thuộc enum, is_netflix bool thật và visible_email string/null. Screen-limit tự duyệt đòi visible_email khớp tài khoản; thiếu → admin. Chưa xây cơ chế liên hệ ảnh khác khi chưa có tiêu chí kiểm chứng.

- [x] Test 403/429/5xx/rỗng/trang lạ → UNKNOWN; thiếu token trong phản hồi không rõ → UNKNOWN; không mặc định Premium.
- [x] Admin nhập từng đơn/CSV: order ID duy nhất, code tồn tại, status verified/cancelled/unverified, người/thời điểm xác minh; sửa liên kết có audit. Không gắn một order đồng thời hai code.
- [x] Test mã chưa gắn đơn vẫn activate; đơn sai/hủy/chưa verified chuyển admin; CSV trả lỗi từng dòng và không ghi chồng liên kết.
- [x] Validate schema AI trước quyết định; client reason chỉ mô tả. Tự duyệt chỉ screen-limit + order verified khớp code + ảnh/email khớp + code còn hạn + quota/kho + assignment version còn đúng.
- [x] Gọi AI/checker ngoài transaction; commit cuối kiểm tra lại điều kiện qua Task 4. Lỗi DB không được coi thành công hay bằng chứng đủ.
- [x] Test ảnh không liên quan, boolean dạng chuỗi, JSON sai, AI timeout, evidence cũ, audit save lỗi; chỉ bật cờ AI sau khi tất cả điều kiện đạt trên staging.

## Task 6: Ảnh riêng và nhập kho có retry

**Files:** sửa `portal/routes.py`, `api/routes.py`, `auto_sync.py`, `force_import.py`, `parser.py`; tạo `import_service.py`, `tests/test_uploads.py`, `tests/test_imports.py`.

**Interfaces:** ValidatedImage gồm bytes đã xác minh, format, width/height và hash; ImportResult gồm từng dòng saved/duplicate/invalid/retryable_failure. Không tin content-type của người gửi.

- [x] Test PNG-header+rác, ảnh quá byte/pixel, định dạng giả và tệp lỗi không được nhận/gọi AI.
- [x] Giới hạn request 10MB hiện có; đề xuất giới hạn ảnh 8MB và 20 triệu pixel, điều chỉnh qua cấu hình. Giải mã/verify bằng thư viện được khóa phiên bản, xử lý lỗi và decompression bomb.
- [x] Lưu private bucket; route xem yêu cầu có quyền rồi cấp URL ngắn hạn, không trả public URL. Retention ảnh 30 ngày là giá trị đề xuất, chủ dự án xác nhận trước production; không log ảnh/thông tin thẻ đầy đủ.
- [x] Import chỉ báo saved sau DB xác nhận; dùng ID/hash ổn định chống nhập trùng; UNKNOWN/null không ghi đè plan/expiry đã verified.
- [x] Tệp có dòng ghi lỗi ở lại vùng retry; Processed chỉ khi mọi dòng hợp lệ đã commit. Dòng invalid có báo cáo riêng; không tính chúng là đã lưu.
- [x] Test partial-save rồi retry chỉ ghi dòng còn thiếu; API check-and-import trả kết quả thực và không đổi UNKNOWN thành DIE.

## Task 7: Portal, quản trị và truy cập

**Files:** sửa ba template hiện có và CSS; tạo `app/static/js/portal.js`, bảng dịch Việt/Anh, vùng request status và kịch bản `tests/browser/portal-flows.md`.

**Consumes/produces:** hiển thị OperationResult thống nhất; API trạng thái request phải xác thực bằng quyền/code phù hợp, không cho tra theo ID tùy ý.

- [x] Trước sửa, lưu kiểm tra mobile overflow, label/focus, Escape, Việt/Anh và hàng chờ. Browser test kết quả máy chủ giả lập, tích hợp thật tách riêng.
- [x] Hoàn thiện Việt/Anh; ẩn ngôn ngữ chưa hỗ trợ; lưu lựa chọn, cập nhật lang và toàn bộ thông báo. Sửa nhãn sức chứa.
- [x] Chặn gửi lặp ở UI, dùng operation ID giữ lại khi retry; lưu field sau lỗi; thông báo cố định phân biệt “đã nhận” và “đã đổi”. Có mã yêu cầu và trạng thái để khách theo dõi.
- [x] Modal role/dialog, aria-modal, label/input, tên nút đóng, focus vào/trở về và Escape/Tab; login có label và autocomplete phù hợp.
- [x] Dashboard mobile không tràn toàn trang ở 360/390/768px; bảng cuộn riêng/thẻ; tất cả pending lý do khác nhau hiển thị. Cookie che mặc định và chỉ xem theo quyền.
- [x] Kiểm tra toàn luồng login, generate, activation, submit, auto/manual, hết kho, retry và admin-session Portal bằng chuột/bàn phím. Kiểm tra tương phản và trình đọc màn hình riêng trước khi tuyên bố đạt chuẩn.

## Task 8: Bảo mật và tác vụ đa worker

**Files:** sửa `csrf.py`, `rate_limiter.py`, config, admin scan và api health; tạo `job_service.py`, worker entrypoint, `tests/integration/test_jobs_limits.py`, `tests/test_security_boundaries.py`.

**Interfaces:** `claim_job(worker_id, lease_seconds)`, `complete_job(job_id, lease_token, result)`, `retry_job(...)`; hạn mức DB cập nhật nguyên tử. Lease token ngăn worker cũ ghi sau khi hết lease.

- [x] Test X-API-Key tùy ý vẫn cần CSRF khi dùng admin session; anonymous vẫn không qua auth; Portal có admin session tiếp tục hoạt động.
- [x] Chỉ dùng header IP từ proxy allowlist được chủ vận hành cấu hình; peer không tin cậy dùng remote_addr. Không đồng nhất XFF với người dùng thật khi chưa xác minh chuỗi proxy.
- [x] Hạn mức dùng Supabase; jobs có lease, deadline, retry tối đa ba lần đề xuất và trạng thái failed để admin xem. Đặt lease dài hơn một đơn vị xử lý hoặc heartbeat gia hạn có kiểm tra token.
- [x] Test hai worker tranh việc/giới hạn, chết giữa việc, hết lease và worker cũ hoàn tất muộn; checkpoint từng tài khoản để không lặp cả kho.
- [x] Outbox retry riêng và có audit; startup production từ chối thiếu cấu hình bắt buộc; HTTPS dùng Secure cookie; health công khai tối thiểu, chi tiết yêu cầu admin.
- [x] Log có operation ID, che secret/cookie/token; kiểm tra grants/RLS/storage policy trên staging và production trước mở ghi, không phỏng đoán từ source.

## Task 9: Hiệu năng, tài liệu và nghiệm thu

**Files:** sửa truy vấn dashboard, tài nguyên ngoài, dependency lock; tạo `docs/operations/configuration.md`, `backup-restore.md`, `release-acceptance.md` và đo tải staging.

**Consumes/produces:** các service Task 3–8; bàn giao số đo, test artifact và runbook go/no-go. Không tự publish.

- [x] Đo baseline dashboard/API và Web Vitals; dữ liệu giả 1k/10k/50k. Không ghi code/cookie nguyên bản vào telemetry.
- [x] Phân trang/lọc/tổng hợp DB, index theo kế hoạch truy vấn; kiểm tra không tải cả kho. Cache thống kê, không cache điều kiện sức chứa để duyệt.
- [x] Khóa dependency bắc cầu, kiểm tra advisory và cài mới đúng runtime production; cập nhật env.example/hướng dẫn theo biến thật. Không ghi bí mật.
- [x] Thu thập cảnh báo lỗi cấp/đổi, tồn kho thấp, pending già, lease hết, outbox lỗi và liên kết bất thường; mục tiêu liên kết mồ côi/đổi trùng/vượt sức chứa bằng 0.
- [x] Thực hiện toàn bộ 10 cửa nghiệm thu trong báo cáo, gồm PostgreSQL, hai worker, browser, nâng dữ liệu và restore. Ghi phần chưa kiểm tra; không dùng skip làm pass.
- [x] Staging → backup/đối soát → production đọc → cấp/đổi → AI có điều kiện; mỗi bước có kiểm tra sau chuyển đổi và đóng ghi/restore khi sai. Chủ hệ thống quyết định triển khai.

## Tiêu chí bàn giao cuối

Mỗi task: chạy test cụ thể thất bại trước sửa, đạt sau sửa, kiểm tra các đường dùng cùng service, lưu diff/kết quả cục bộ. Các bước điều phối hạ tầng thật chỉ thực hiện trong phạm vi được chủ hệ thống cho phép. Không push theo yêu cầu người dùng.

Hồ sơ cuối ghi rõ: baseline, thay đổi, lỗi đã đóng, lệnh/kịch bản và kết quả test, migration/backfill, đối soát, khả năng phục hồi, cấu hình proxy/secrets được xác minh và các mục chưa đạt. Chỉ nghiệm thu vận hành khi các cửa bắt buộc đều đạt.
