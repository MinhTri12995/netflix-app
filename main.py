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
        database.save_account(data['email'], data['expire'], data['netflix_id'])
        
        print("\n✅ Trích xuất và lưu vào DB THÀNH CÔNG!")
        print(f"  - Email     : {data['email']}")
        print(f"  - Expire    : {data['expire']}")
        print(f"  - NetflixId : {data['netflix_id'][:20]}... (đã ẩn bớt)")
    else:
        print("\n❌ Thất bại: File không hợp lệ hoặc thiếu thông tin.")

if __name__ == "__main__":
    main()
