# Data Audit & Reconciliation Runbook (Đối soát dữ liệu)

**Mục tiêu:** Phát hiện bất thường trong dữ liệu (liên kết mồ côi, tài khoản vượt sức chứa, sai lệch gói/hạn sử dụng) giữa PostgreSQL/Supabase và local SQLite trước khi tiến hành chuyển đổi.

---

## 1. Nguyên tắc An Toàn Bắt Buộc
- **Chỉ đọc (Read-Only):** Tất cả các câu lệnh kiểm tra đối soát phải là `SELECT`. Tuyệt đối không tự ý chạy `UPDATE` hoặc `DELETE` trên dữ liệu chưa xác định rõ người sở hữu.
- **Không suy đoán dữ liệu:** Nếu một mã hoặc tài khoản có trạng thái bất thường, lập danh sách riêng và chuyển cho chủ hệ thống (Admin/Owner) xem xét.
- **Sao lưu trước khi thao tác:** Bắt buộc xuất bản sao lưu (dump/export) của cả PostgreSQL và SQLite trước khi thực hiện migration.

---

## 2. Các Truy Vấn Kiểm Tra Bất Thường (Read-Only Audit)

### 2.1. Phát hiện Liên Kết Mồ Côi (Orphaned Access Keys)
*Tìm các mã Access Code đang trỏ tới email tài khoản không tồn tại trong kho:*
```sql
SELECT ak.code, ak.assigned_email, ak.created_at, ak.expire_at
FROM access_keys ak
LEFT JOIN netflix_accounts na ON ak.assigned_email = na.email
WHERE na.email IS NULL;
```
- **Hành động:** Nếu có bản ghi, đánh dấu cần cấp lại tài khoản mới (không xóa mã truy cập của khách).

---

### 2.2. Phát hiện Tài Khoản Vượt Quá Sức Chứa (Capacity Over-allocation)
*Tìm các tài khoản đang bị gán vượt quá số lượng mã cho phép (Solo Mode: >1; Shared Mode: Premium >4, các gói khác >2):*
```sql
SELECT na.email, na.plan, COUNT(ak.code) AS assigned_count
FROM netflix_accounts na
JOIN access_keys ak ON ak.assigned_email = na.email
GROUP BY na.email, na.plan
HAVING 
    (na.plan = 'Premium' AND COUNT(ak.code) > 4) OR
    (na.plan != 'Premium' AND COUNT(ak.code) > 2);
```
- **Hành động:** Lập danh sách các mã đang dùng chung để lên kế hoạch phân bổ lại sang tài khoản dự phòng trống.

---

### 2.3. Phát hiện Mã Truy Cập Thiếu Gói Hoặc Sai Định Dạng Hạn Dùng
*Tìm các mã chưa có gói hoặc ngày hết hạn sai quy chuẩn:*
```sql
SELECT code, assigned_email, plan, expire_at, created_at
FROM access_keys
WHERE plan IS NULL OR plan = '' OR expire_at NOT LIKE '____-__-__%';
```

---

### 2.4. Đối Soát Khác Biệt Giữa Supabase Và SQLite
*Nếu hệ thống từng hoạt động ở chế độ hybrid, chạy script so sánh số lượng bản ghi:*
```bash
python -c "
import database as db
db.init_db()
print('Authoritative accounts:', len(db.fetch_all_rows('netflix_accounts')))
print('Authoritative access_keys:', len(db.fetch_all_rows('access_keys')))
"
```

---

## 3. Quy Trình Chuyển Đổi Trên Môi Trường Thử Nghiệm (Staging)

1. **Bước 1: Chạy migration schema**
   - Áp dụng migration `supabase/migrations/20261005000001_authoritative_schema.sql` vào cơ sở dữ liệu Staging.
2. **Bước 2: Nâng cấp và Backfill dữ liệu**
   - Chạy lệnh backfill gói cho mã cũ.
   - Kiểm tra `COUNT(*)` trước và sau khi chạy script để đảm bảo không mất bản ghi nào.
3. **Bước 3: Chạy toàn bộ bộ kiểm thử tự động**
   - Chạy `python -m unittest discover -s tests -p "test_*.py"`.
   - Xác nhận 100% các bài test (bao gồm cả test tranh chấp tải 20 luồng) đều đạt.
4. **Bước 4: Diễn tập Rollback / Phục hồi**
   - Thử khôi phục từ file backup để đảm bảo dữ liệu toàn vẹn trong trường hợp khẩn cấp.
