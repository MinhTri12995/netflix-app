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
            
        database.init_db()
        count = 0
        for acc in accounts_list:
            database.save_account(acc['email'], acc['expire'], acc['netflix_id'], acc['secure_netflix_id'])
            count += 1
            
        print(f"SUCCESS: Đã ép thành công {count} accounts vào Database!")
        
    except Exception as e:
        print(f"Lỗi hệ thống: {e}")

if __name__ == "__main__":
    force_import()
