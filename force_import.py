import database
import parser

def force_import():
    try:
        # Đọc dữ liệu từ file mới, thử các bộ mã hoá
        with open('data.txt.txt', 'rb') as f:
            file_bytes = f.read()
            
        try:
            content = file_bytes.decode('utf-8-sig')
        except UnicodeDecodeError:
            try:
                content = file_bytes.decode('utf-16')
            except UnicodeDecodeError:
                content = file_bytes.decode('latin-1', errors='replace')
                
        lines = content.splitlines()
        accounts_list = parser.parse_lines(lines)
        
        if not accounts_list:
            print("Không tìm thấy account nào! Vui lòng kiểm tra lại data.txt")
            return

        from app.services.import_service import import_accounts
        result = import_accounts(accounts_list)

        if result.is_complete_success:
            print(f"SUCCESS: Đã ép thành công {result.saved_count}/{result.total} accounts vào Database!")
        else:
            print(f"WARNING: Đã lưu {result.saved_count}, thất bại {result.failure_count}, không hợp lệ {result.invalid_count}.")
        
    except Exception as e:
        print(f"Lỗi hệ thống: {e}")

if __name__ == "__main__":
    force_import()
