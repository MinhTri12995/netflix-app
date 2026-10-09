# Sửa lỗi Portal không tạo được link — bàn giao local 09/10/2026

Nền mã: `b98aa31900a45af97556fc1376dd87009ebebf4f`. Phạm vi được duyệt: sửa luồng tạo token, kiểm thử, cập nhật Supabase và push bản sửa để Render triển khai. Cookie, mã truy cập và các tệp kiểm tra live không đưa vào commit.

## Kết quả sửa

- Phản hồi thiếu token, token rỗng/sai kiểu, URL gốc Netflix hoặc nội dung không phải JSON trả HTTP 503 với `error_code=TOKEN_RESPONSE_UNVERIFIED`, `retryable=true`. Giữ nguyên liên kết và trạng thái tài khoản; không suy ra cookie hỏng từ việc thiếu token.
- HTTP 401 tiếp tục thuộc `CookieError`, cho phép luồng tìm tài khoản thay thế. Lỗi mạng, 403/429/5xx giữ phân loại dịch vụ/proxy, không gây đổi tài khoản vì thiếu token.
- Danh sách loại trừ tài khoản vừa lỗi áp dụng vào mọi nhánh tìm tài khoản thay thế, kể cả nhánh khác gói, ở cả SQLite và Supabase. Trong một yêu cầu không quay lại A sau khi A đã thất bại; hết ngân sách bốn lần thử không đổi tiếp sang tài khoản thứ năm chưa được thử.
- Bỏ việc ép các email cố định thành `live`/`needs_review` khi khởi tạo ứng dụng. Trạng thái hiện hữu không bị ghi đè bởi danh sách seed.
- Mã hóa giá trị token trong query của cả bốn loại link để giữ đúng các ký tự `+`, `/`, `=`, `&`. Log token không in nội dung phản hồi, cookie, token hoặc mật khẩu proxy.
- Thêm migration `supabase/migrations/20261009052917_portal_activation_schema.sql`: bổ sung trạng thái khi thiếu; thay đúng ràng buộc ba trạng thái của migration cũ để chấp nhận các trạng thái đang dùng; tạo outbox phù hợp với ứng dụng; giới hạn outbox cho backend `service_role`; yêu cầu PostgREST tải lại schema sau commit. Phiên bản tệp khớp lịch sử migration đã áp dụng qua API Supabase.

## Bằng chứng kiểm thử

| Kiểm tra | Kết quả |
| --- | --- |
| Toàn bộ bộ kiểm thử trước sửa | 119 đạt, 1 thất bại |
| 23 tình huống mới chạy trên mã HEAD cũ | 22 thất bại đúng hành vi cần sửa, 1 đạt (HTTP 401 tương thích) |
| Toàn bộ bộ kiểm thử sau sửa | 143 đạt |
| Sau bổ sung header nhận diện bản Render | 147 đạt |
| Migration trên PostgreSQL nhúng PGlite 0.5.8 | 7 tình huống đạt |

Bài thất bại sẵn là `tests/test_phase_c.py::TestPhaseC::test_submit_request_too_many_people_auto_rotate`: bài kiểm thử mock phản hồi AI nhưng không cấp `Config.MISTRAL_API_KEY` giả, khiến handler bỏ qua AI. Đã thêm khóa chỉ dùng trong kiểm thử; không thay đổi quy tắc AI của ứng dụng.

Các tình huống migration gồm: schema cũ thiếu trạng thái/outbox; chạy lại không mất dữ liệu; ràng buộc cũ chấp nhận `live` sau nâng cấp; giữ nguyên các trạng thái đã có; giữ payload/số lần retry outbox; chặn trạng thái hoặc ràng buộc tùy chỉnh chưa đối soát; rollback toàn bộ khi outbox không tương thích. Đã kiểm tra `anon`/`authenticated` bị từ chối đọc outbox và `service_role` tạo/đọc/cập nhật được sự kiện.

Kiểm thử Python dùng database tạm và chặn kết nối dịch vụ thật. Kiểm thử Supabase dùng mô hình API giả có trạng thái, tái hiện cả PGRST204 và PGRST205. Không dùng tài khoản Netflix thật trong bộ kiểm thử. CI đã được chỉnh để cài phụ thuộc kiểm thử và chạy cùng trình chạy cô lập.

Website trả header `X-App-Revision` khi Render cung cấp `RENDER_GIT_COMMIT` hợp lệ. Header chỉ chứa commit SHA công khai; không thêm chi tiết dữ liệu vào health check. Đối chiếu header với commit đã push để xác nhận bản đang chạy.

## Chạy lại local

Trong PowerShell tại thư mục dự án, dùng môi trường Python riêng:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
.\.venv\Scripts\python.exe scripts/test_local.py
```

Trong workspace hiện tại cũng có thể dùng Python đã chuẩn bị tại `scratch/hardening-venv/Scripts/python.exe`. Trình chạy nằm trong `scripts/`, không phụ thuộc runner cũ trong `scratch/`. Không chạy script kiểm tra live để thay cho kiểm thử này: thao tác kích hoạt có thể đổi liên kết trên production.

Kiểm tra migration không cần máy chủ hoặc tài khoản Supabase:

```powershell
npm install --prefix scratch/activation-postgres --save-exact @electric-sql/pglite@0.5.8
node tests/migrations/portal_activation_schema.mjs scratch/activation-postgres
```

Log/XML local của lần kiểm tra được lưu trong `scratch/activation-baseline.*`, `scratch/activation-red.*`, `scratch/activation-after.*`. Các tệp scratch không đưa vào Git.

## Trước khi áp dụng trên Supabase

PGRST204/PGRST205 chứng minh Data API chưa thấy cột/bảng, chưa đủ để phân biệt thiếu cấu trúc thật với schema cache cũ. Chạy các truy vấn chỉ đọc sau trong SQL Editor của đúng dự án và sao lưu trước khi thay đổi:

```sql
SELECT table_schema, table_name, column_name, udt_name, column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('netflix_accounts', 'access_keys', 'events_outbox')
ORDER BY table_name, ordinal_position;

SELECT conname, pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = to_regclass('public.netflix_accounts');

SELECT count(*) AS dangling_assignments
FROM public.access_keys k
LEFT JOIN public.netflix_accounts a ON a.email = k.assigned_email
WHERE k.assigned_email IS NOT NULL AND a.email IS NULL;
```

Nếu cột `status` đã tồn tại, đối soát trước bằng:

```sql
SELECT status, count(*) FROM public.netflix_accounts GROUP BY status;
```

Đối chiếu `events_outbox` nếu đã tồn tại: `id` phải có cơ chế sinh tự động khi insert không truyền id; `event_type` là text/varchar; `payload` là json/jsonb. Backend phải dùng khóa `service_role`/secret phù hợp, không dùng khóa anon cho outbox. Ràng buộc riêng, kiểu dữ liệu khác hoặc trạng thái lạ cần được xem xét trước; migration sẽ dừng thay vì tự sửa dữ liệu đó.

Migration này là bản bổ sung giới hạn, chạy được trực tiếp trên schema legacy, không cần chạy lại toàn bộ migration `20261005000001_authoritative_schema.sql`. Nếu triển khai qua CLI, đối chiếu lịch sử migration của dự án trước; không dùng `db push` một cách mù quáng để chạy cả migration cũ.

Sau khi được duyệt triển khai: chạy migration trong giao dịch, kiểm tra quyền outbox bằng backend, xác nhận Data API đã thấy schema, triển khai mã nguồn đã bỏ seed và thử kích hoạt có kiểm soát. [PostgREST hỗ trợ tải lại schema qua NOTIFY](https://docs.postgrest.org/en/stable/references/schema_cache.html); tải lại cache không tạo được cột/bảng đang thiếu.

## Giới hạn chưa xác minh trên production

- Chưa xác định vì sao phản hồi Netflix thật thiếu token: cookie hết hiệu lực, dịch vụ thay đổi hoặc lỗi mạng/proxy đều cần thêm bằng chứng. Bản sửa xử lý an toàn các phản hồi đó, không bảo đảm Netflix sẽ cấp token trở lại.
- Migration đã áp dụng qua Supabase API và kiểm tra lại cột trạng thái, outbox, quyền truy cập và số lượng bản ghi. Việc website đã chạy commit mới phải được xác minh riêng qua trạng thái triển khai Render.
- PGlite xác minh giao dịch/DDL/quyền và bảo toàn dữ liệu giả; chưa xác minh PostgREST schema cache, chính sách/quyền tùy chỉnh hoặc dữ liệu production thực tế.
- Danh sách loại trừ chỉ tồn tại trong một yêu cầu. Cần sửa schema và lưu trạng thái thành công để các yêu cầu sau cùng loại trừ tài khoản đã lỗi.
- Bản sửa này không chuyển luồng đổi Supabase hiện có thành một giao dịch PostgreSQL nguyên tử và không nghiệm thu lại toàn bộ hệ thống vận hành.

## Phục hồi

Nếu SQL lỗi, rollback giao dịch và kiểm tra nguyên nhân trước khi chạy lại. Nếu đã commit rồi cần phục hồi, dùng bản sao lưu và đối soát sự kiện/liên kết phát sinh; không tự xóa cột trạng thái hoặc bảng outbox để hạ phiên bản. Có thể dừng luồng kích hoạt trong lúc phục hồi. Mã nguồn nền chứa seed ép trạng thái nên không nên khôi phục vận hành nguyên trạng mà chưa đánh giá tác động.
