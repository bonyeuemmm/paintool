import os
import sys
import time
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Địa chỉ Server Backend trên Render
SERVER_URL = "https://paintool-api.onrender.com"
LICENSE_FILE = ".pain_license"

def clear_screen():
    os.system('clear' if os.name != 'nt' else 'cls')

def license_screen():
    clear_screen()
    print("========================================")
    print("         XÁC THỰC BẢN QUYỀN PAIN TOOL   ")
    print("========================================")
    print(" Trạng thái : CHƯA KÍCH HOẠT")
    print(" Lấy key tại: https://t.me/paintool_support")
    print("========================================")

def verify_key_with_server(key):
    """Gửi Key lên Backend Render để kiểm tra"""
    try:
        response = requests.post(
            f"{SERVER_URL}/verify",
            json={"key": key},
            timeout=10,
            verify=False
        )
        if response.status_code == 200:
            data = response.json()
            return True, data.get("message", "Xác thực thành công!")
        else:
            data = response.json()
            return False, data.get("message", "Key không hợp lệ!")
    except Exception as e:
        return False, f"Không thể kết nối đến Server Backend: {e}"

def authenticate():
    # 1. Kiểm tra key lưu sẵn
    if os.path.exists(LICENSE_FILE):
        with open(LICENSE_FILE, "r") as f:
            saved_key = f.read().strip()
            if saved_key:
                success, msg = verify_key_with_server(saved_key)
                if success:
                    print(f"[✓] {msg}")
                    return saved_key

    # 2. Nếu chưa có key/key hết hạn -> Hiện màn hình nhập Key
    license_screen()
    input_key = input("\n[+] Nhập Key của bạn: ").strip()

    if not input_key:
        print("[X] Key không được để trống!")
        sys.exit(1)

    print("[*] Đang kiểm tra Key trên Server...")
    success, msg = verify_key_with_server(input_key)

    if success:
        with open(LICENSE_FILE, "w") as f:
            f.write(input_key)
        print(f"[✓] {msg}")
        time.sleep(1)
        return input_key
    else:
        print(f"[X] Lỗi: {msg}")
        if os.path.exists(LICENSE_FILE):
            os.remove(LICENSE_FILE)
        sys.exit(1)

def run_main_tool(user_key):
    """Gọi Backend thực thi tính năng sau khi xác thực thành công"""
    clear_screen()
    print("========================================")
    print("         PAIN TOOL PREMIUM v2.1.0       ")
    print("========================================")
    print(f"[*] Key hiện tại: {user_key}")
    print("[*] Đang tải cấu hình từ Backend Server...\n")
    
    # Bạn có thể gọi API Backend tại đây để chạy tính năng chính
    # response = requests.get(f"{SERVER_URL}/run-feature", headers={"Authorization": user_key})

if __name__ == "__main__":
    try:
        valid_key = authenticate()
        run_main_tool(valid_key)
    except KeyboardInterrupt:
        print("\n[-] Đã thoát chương trình.")
        sys.exit(0)
