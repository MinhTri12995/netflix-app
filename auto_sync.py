import os
import time
import shutil
from datetime import datetime
import database
import parser

# Đảm bảo in tiếng Việt không lỗi trên Windows
import sys
sys.stdout.reconfigure(encoding='utf-8')

WATCH_DIR = os.environ.get("AUTO_IMPORT_DIR", r"D:\đtb\Auto_Import")
PROCESSED_DIR = os.path.join(WATCH_DIR, "Processed")
ERRORS_DIR = os.path.join(WATCH_DIR, "Errors")

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

        from app.services.import_service import import_accounts
        result = import_accounts(accounts_list)

        if result.is_complete_success:
            print(f"  -> ✅ Đã đồng bộ thành công {result.saved_count}/{result.total} account vào Web!")
            return True
        else:
            print(f"  -> ⚠️ Đồng bộ chưa hoàn tất: {result.saved_count} đã lưu, {result.failure_count} lỗi ghi database, {result.invalid_count} không hợp lệ.")
            return False
        
    except Exception as e:
        print(f"  -> ❌ Lỗi xử lý file: {e}")
        return False

def main():
    print(f"🔄 Đang theo dõi thư mục: {WATCH_DIR}")
    print("Mọi file .txt ném vào đây sẽ tự động được đưa lên Web (Ctrl+C để thoát)\n")
    
    os.makedirs(WATCH_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    os.makedirs(ERRORS_DIR, exist_ok=True)

    while True:
        try:
            # Quét các file .txt trong thư mục
            for filename in os.listdir(WATCH_DIR):
                if filename.lower().endswith(".txt"):
                    filepath = os.path.join(WATCH_DIR, filename)
                    
                    # Tránh bị lỗi "file đang bị tiến trình khác khóa" bằng cách đợi file ghi xong
                    time.sleep(1) 
                    
                    success = process_file(filepath)
                    
                    # Chuyển file vào thư mục Processed hoặc Errors để không quét lại
                    target_dir = PROCESSED_DIR if success else ERRORS_DIR
                    os.makedirs(target_dir, exist_ok=True)
                    dest = os.path.join(target_dir, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}")
                    try:
                        shutil.move(filepath, dest)
                        folder_name = "Processed" if success else "Errors"
                        print(f"  -> Đã di chuyển vào thư mục {folder_name}.\n")
                    except Exception as e:
                        print(f"  -> ❌ Không thể di chuyển file: {e}")
                        
        except Exception as e:
            print(f"Lỗi: {e}")
            
        # Nghỉ 3 giây rồi quét tiếp
        time.sleep(3)

if __name__ == "__main__":
    os.makedirs(WATCH_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    os.makedirs(ERRORS_DIR, exist_ok=True)
    main()
