import os
import time
import shutil
from datetime import datetime
import database
import parser

# Đảm bảo in tiếng Việt không lỗi trên Windows
import sys
sys.stdout.reconfigure(encoding='utf-8')

WATCH_DIR = r"D:\đtb\Auto_Import"
PROCESSED_DIR = os.path.join(WATCH_DIR, "Processed")

def process_file(filepath):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Phát hiện file mới: {os.path.basename(filepath)}")
    try:
        # Đọc dữ liệu
        with open(filepath, 'rb') as f:
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
            print(f"  -> File trống hoặc không đúng định dạng.")
            return False
            
        database.init_db()
        count = 0
        for acc in accounts_list:
            database.save_account(acc['email'], acc['expire'], acc['netflix_id'], acc['secure_netflix_id'])
            count += 1
            
        print(f"  -> ✅ Đã đồng bộ thành công {count} account vào Web!")
        return True
        
    except Exception as e:
        print(f"  -> ❌ Lỗi xử lý file: {e}")
        return False

def main():
    print(f"🔄 Đang theo dõi thư mục: {WATCH_DIR}")
    print("Mọi file .txt ném vào đây sẽ tự động được đưa lên Web (Ctrl+C để thoát)\n")
    
    while True:
        try:
            # Quét các file .txt trong thư mục
            for filename in os.listdir(WATCH_DIR):
                if filename.lower().endswith(".txt"):
                    filepath = os.path.join(WATCH_DIR, filename)
                    
                    # Tránh bị lỗi "file đang bị tiến trình khác khóa" bằng cách đợi file ghi xong
                    time.sleep(1) 
                    
                    success = process_file(filepath)
                    
                    # Chuyển file vào thư mục Processed để không quét lại
                    dest = os.path.join(PROCESSED_DIR, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}")
                    try:
                        shutil.move(filepath, dest)
                        print(f"  -> Đã di chuyển vào thư mục Processed.\n")
                    except Exception as e:
                        print(f"  -> ❌ Không thể di chuyển file: {e}")
                        
        except Exception as e:
            print(f"Lỗi: {e}")
            
        # Nghỉ 3 giây rồi quét tiếp
        time.sleep(3)

if __name__ == "__main__":
    # Đảm bảo thư mục tồn tại
    if not os.path.exists(PROCESSED_DIR):
        os.makedirs(PROCESSED_DIR)
    main()
