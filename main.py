import sys
import os
import database
import parser

# Đảm bảo in tiếng Việt trên console Windows không bị lỗi
sys.stdout.reconfigure(encoding='utf-8')

def main():
    if len(sys.argv) < 2:
        print("Sử dụng: python main.py <đường_dẫn_tới_file_txt>")
        print("Ví dụ: python main.py sample.txt")
        sys.exit(1)
        
    file_path = sys.argv[1]
    
    if not os.path.exists(file_path):
        print(f"Lỗi: Không tìm thấy file '{file_path}'")
        sys.exit(1)
        
    print(f"Đang xử lý file: {file_path}")
    
    # 1. Parse file
    data = parser.parse_netflix_file(file_path)
    
    if data:
        # 2. Lưu vào DB
        database.init_db()
        accounts_to_save = data if isinstance(data, list) else [data]
        saved_count = 0
        for acc in accounts_to_save:
            email = acc.get('email', '')
            expire = acc.get('expire', 'N/A')
            netflix_id = acc.get('netflix_id', '')
            secure_netflix_id = acc.get('secure_netflix_id', '')
            plan = acc.get('plan')
            if netflix_id:
                database.save_account(email, expire, netflix_id, secure_netflix_id=secure_netflix_id, plan=plan)
                saved_count += 1
                print(f"  - Email     : {email}")
                print(f"  - Expire    : {expire}")
                print(f"  - NetflixId : {netflix_id[:20]}... (đã ẩn bớt)")
        
        print(f"\n✅ Trích xuất và lưu vào DB THÀNH CÔNG {saved_count} tài khoản!")
    else:
        print("\n❌ Thất bại: File không hợp lệ hoặc thiếu thông tin.")

if __name__ == "__main__":
    main()
