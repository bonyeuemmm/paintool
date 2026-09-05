import os
import sys
import time
import subprocess
import requests
import json

API_URL = "https://discord-license-bot-production.up.railway.app/api/verify"
LICENSE_FILE = os.path.join(os.path.expanduser("~"), ".pain_license")

PACKAGE_NAME = "com.roblox.client"
TARGET_LINK = ""
WEBHOOK_URL = ""
ROBLOX_CREDENTIALS = ""
AUTO_REJOIN = 1
DELAY_MINUTES = 1
WEBHOOK_INTERVAL = 1
SCREENSHOT_PATH = "/sdcard/pain_screenshot.png"

def get_hwid():
    hwid = ""
    try:
        hwid = subprocess.check_output(["settings", "get", "secure", "android_id"]).decode().strip()
    except Exception:
        pass

    if not hwid or hwid == "null":
        try:
            hwid = subprocess.check_output(["getprop", "ro.serialno"]).decode().strip()
        except Exception:
            pass

    if not hwid or hwid == "null":
        hwid = "android_default_hwid"
        
    return hwid

def check_license_online(key, hwid):
    try:
        payload = {"key": key, "hwid": hwid}
        res = requests.post(API_URL, json=payload, timeout=10)
        if res.status_code == 200:
            try:
                data = res.json()
                if isinstance(data, dict):
                    return data.get("valid") is True or data.get("status") == "success", res.text.strip()
            except Exception:
                pass
            return "valid" in res.text.lower() and "true" in res.text.lower(), res.text.strip()
        return False, f"HTTP Error {res.status_code}"
    except Exception as e:
        return False, str(e)

def authenticate():
    global LICENSE_FILE
    input_key = ""
    hwid = get_hwid()

    if os.path.exists(LICENSE_FILE):
        try:
            with open(LICENSE_FILE, "r") as f:
                input_key = f.read().strip()
            
            if input_key:
                print("\033[1;35m[*] Đang kiểm tra Key đã lưu...\033[0m")
                is_valid, _ = check_license_online(input_key, hwid)
                if is_valid:
                    print("\033[1;32m[+] Tự động xác thực bản quyền thành công!\033[0m")
                    time.sleep(1)
                    return
                else:
                    print("\033[1;33m[!] Key đã lưu không hợp lệ, hết hạn hoặc sai HWID.\033[0m")
                    if os.path.exists(LICENSE_FILE):
                        os.remove(LICENSE_FILE)
        except Exception:
            pass

    while True:
        os.system('clear')
        print("\033[1;35m==================================================\033[0m")
        print("\033[1;37m          PAIN TOOL REJOIN VIP - XÁC THỰC         \033[0m")
        print("\033[1;35m==================================================\033[0m")
        print(f"\033[1;36m HWID hiện tại: {hwid}\033[0m")
        print("\033[1;37m[!] Vui lòng nhập Tool Key (pain_key_...) để tiếp tục.\033[0m")
        print("\033[1;35m(Nhập 'exit' hoặc '0' để thoát)\033[0m")
        print("\033[1;35m==================================================\033[0m")
        input_key = input("Nhập Key: ").strip()
        
        if input_key == "exit" or input_key == "0":
            print("\033[1;31mĐã thoát chương trình. Goodbye!\033[0m")
            sys.exit(0)

        if not input_key:
            continue

        print("\033[1;35m[*] Đang kết nối máy chủ để xác minh Key...\033[0m")
        is_valid, response_text = check_license_online(input_key, hwid)

        if is_valid:
            try:
                with open(LICENSE_FILE, "w") as f:
                    f.write(input_key)
            except Exception as write_err:
                print(f"\033[1;33m[!] Cảnh báo: Không thể lưu Key vào bộ nhớ cục bộ ({write_err})\033[0m")

            print("\033[1;32m[+] Xác thực Key thành công! Đã khóa theo thiết bị.\033[0m")
            time.sleep(1.5)
            break
        else:
            print(f"\033[1;31m[!] Thất bại: Key không hợp lệ hoặc sai HWID.\033[0m")
            print(f"\033[1;33m[*] Phản hồi từ máy chủ: {response_text}\033[0m")
            time.sleep(3)

def show_banner():
    os.system('clear')
    target_display = TARGET_LINK if TARGET_LINK else "Chua dat (Rejoin thuong / Blox Fruit Lobby)"
    webhook_display = WEBHOOK_URL if WEBHOOK_URL else "Chua dat"
    creds_display = "Chua dat" if not ROBLOX_CREDENTIALS else "Da cau hinh (*)"
    auto_rejoin_display = "Bat" if AUTO_REJOIN == 1 else "Tat"
    
    print("\033[1;35m==================================================\033[0m")
    print("\033[1;37m             PAIN TOOL REJOIN VIP                 \033[0m")
    print("\033[1;35m==================================================\033[0m")
    print(f"\033[1;35m Package Name    :\033[0m \033[1;37m{PACKAGE_NAME}\033[0m")
    print(f"\033[1;35m Target ID/Link  :\033[0m \033[1;37m{target_display}\033[0m")
    print(f"\033[1;35m Webhook URL     :\033[0m \033[1;37m{webhook_display}\033[0m")
    print(f"\033[1;35m Webhook Interval:\033[0m \033[1;37mMoi {WEBHOOK_INTERVAL} phut\033[0m")
    print(f"\033[1;35m Roblox Creds    :\033[0m \033[1;37m{creds_display}\033[0m")
    print(f"\033[1;35m Auto Rejoin     :\033[0m \033[1;37m{auto_rejoin_display}\033[0m")
    print(f"\033[1;35m Delay Time      :\033[0m \033[1;37m{DELAY_MINUTES} phut\033[0m")
    print("\033[1;35m==================================================\033[0m")
    print("\033[1;35m[1]\033[0m \033[1;37mStart\033[0m")
    print("\033[1;35m[2]\033[0m \033[1;37mSet up\033[0m")
    print("\033[1;35m[3]\033[0m \033[1;37mPackage name\033[0m")
    print("\033[1;35m[4]\033[0m \033[1;37mID/Link private\033[0m")
    print("\033[1;35m[5]\033[0m \033[1;37mUrl webhook\033[0m")
    print("\033[1;35m[6]\033[0m \033[1;37mLogin cookie roblox\033[0m")
    print("\033[1;31m[7] Exit\033[0m")
    print("\033[1;35m==================================================\033[0m")

def send_webhook_with_image(message):
    if WEBHOOK_URL:
        try:
            subprocess.run(["screencap", "-p", SCREENSHOT_PATH], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(SCREENSHOT_PATH):
                with open(SCREENSHOT_PATH, "rb") as f:
                    files = {"file": f}
                    payload = {"payload_json": json.dumps({"content": message})}
                    requests.post(WEBHOOK_URL, data=payload, files=files)
            else:
                requests.post(WEBHOOK_URL, json={"content": message})
        except Exception:
            pass

def start_tool():
    if not PACKAGE_NAME:
        print("\033[1;31m[!] Loi: Chua cau hinh Package name!\033[0m")
        time.sleep(2)
        return

    if AUTO_REJOIN == 0:
        print("\033[1;31m[!] Auto Rejoin dang bi TAT trong muc [2] Set up!\033[0m")
        time.sleep(2)
        return

    os.system('clear')
    print("\033[1;37m[+] PAIN TOOL REJOIN VIP dang chay...\033[0m")
    print("\033[1;35m[*] Nhan Ctrl+C de dung va quay lai menu.\033[0m")
    
    if ROBLOX_CREDENTIALS:
        print("\033[1;37m[+] Da tai thong tin Roblox cho phien lam viec.\033[0m")

    send_webhook_with_image(f"[PAIN TOOL] Bat dau theo doi Roblox. Tan suat gui anh: {WEBHOOK_INTERVAL} phut/lan.")

    sleep_seconds = DELAY_MINUTES * 60
    interval_seconds = WEBHOOK_INTERVAL * 60
    elapsed_time = 0

    try:
        while True:
            pid_res = subprocess.run(["pidof", PACKAGE_NAME], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            pid = pid_res.stdout.decode().strip()
            
            if not pid:
                print("\033[1;31m[-] Roblox bi dong hoac vang. Dang mo lai...\033[0m")
                send_webhook_with_image("[PAIN TOOL] Roblox da bi dong hoac vang game! Dang mo lai:")
                if TARGET_LINK:
                    subprocess.run(["am", "start", "-a", "android.intent.action.VIEW", "-d", TARGET_LINK, PACKAGE_NAME])
                else:
                    subprocess.run(["am", "start", "-n", f"{PACKAGE_NAME}/.MainActivity"])
                time.sleep(10)
                elapsed_time = 0
            else:
                logcat_res = subprocess.run(["logcat", "-d", "-s", "Unity:V", "AndroidRuntime:E"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                log_output = logcat_res.stdout.decode()
                
                if any(keyword in log_output.lower() for keyword in ['disconnect', 'kicked', 'lost connection']):
                    print("\033[1;33m[-] Phat hien mat ket noi. Dang vao lai game...\033[0m")
                    send_webhook_with_image("[PAIN TOOL] Phat hien mat ket noi! Dang Rejoin game va chup man hinh:")
                    subprocess.run(["am", "force-stop", PACKAGE_NAME])
                    time.sleep(2)
                    
                    if TARGET_LINK:
                        subprocess.run(["am", "start", "-a", "android.intent.action.VIEW", "-d", TARGET_LINK, PACKAGE_NAME])
                    else:
                        subprocess.run(["am", "start", "-n", f"{PACKAGE_NAME}/.MainActivity"])
                    time.sleep(10)
                    elapsed_time = 0
            
            subprocess.run(["logcat", "-c"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            elapsed_time += sleep_seconds
            if elapsed_time >= interval_seconds:
                send_webhook_with_image(f"[PAIN TOOL] Cap nhat trang thai dinh ky ({WEBHOOK_INTERVAL} phut):")
                elapsed_time = 0

            time.sleep(sleep_seconds)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    authenticate()

    while True:
        show_banner()
        choice = input("Chon chuc nang [1-7]: ").strip()
        
        if choice == "1":
            start_tool()
        elif choice == "2":
            while True:
                os.system('clear')
                auto_status = "Bat" if AUTO_REJOIN == 1 else "Tat"
                print("\033[1;35m=== CAI DAT HE THONG ===\033[0m")
                print(f"\033[1;37m1. Auto Rejoin (Hien tai: {auto_status})\033[0m")
                print(f"\033[1;37m2. Thoi gian cho kiem tra (Hien tai: {DELAY_MINUTES} phut)\033[0m")
                print(f"\033[1;37m3. Tan suat gui Webhook (Hien tai: {WEBHOOK_INTERVAL} phut)\033[0m")
                print("\033[1;35m4. Quay lai menu chinh\033[0m")
                print("\033[1;35m==================================================\033[0m")
                sub_choice = input("Chon cai dat [1-4]: ").strip()
                
                if sub_choice == "1":
                    os.system('clear')
                    print("\033[1;35m=== CAI DAT AUTO REJOIN ===\033[0m")
                    print("\033[1;37m1. Bat Auto Rejoin\033[0m")
                    print("\033[1;37m0. Tat Auto Rejoin\033[0m")
                    toggle_val = input("Chon option [1/0]: ").strip()
                    if toggle_val in ["1", "0"]:
                        AUTO_REJOIN = int(toggle_val)
                        print("\033[1;37m[+] Cap nhat Auto Rejoin thanh cong!\033[0m")
                    else:
                        print("\033[1;31m[!] Lua chon khong hop le.\033[0m")
                    time.sleep(2)
                elif sub_choice == "2":
                    os.system('clear')
                    print("\033[1;35m=== CAI DAT THOI GIAN CHO KIEM TRA (PHUT) ===\033[0m")
                    input_min = input("Nhap thoi gian cho (phut): ").strip()
                    if input_min.isdigit() and int(input_min) > 0:
                        DELAY_MINUTES = int(input_min)
                        print(f"\033[1;37m[+] Da cap nhat thoi gian cho thanh {DELAY_MINUTES} phut!\033[0m")
                    else:
                        print("\033[1;31m[!] So khong hop le.\033[0m")
                    time.sleep(2)
                elif sub_choice == "3":
                    os.system('clear')
                    print("\033[1;35m=== CAI DAT TAN SUAT GUI WEBHOOK (PHUT) ===\033[0m")
                    input_interval = input("Nhap tan suat gui anh Webhook (phut): ").strip()
                    if input_interval.isdigit() and int(input_interval) > 0:
                        WEBHOOK_INTERVAL = int(input_interval)
                        print(f"\033[1;37m[+] Da cap nhat tan suat Webhook thanh moi {WEBHOOK_INTERVAL} phut!\033[0m")
                    else:
                        print("\033[1;31m[!] So khong hop le.\033[0m")
                    time.sleep(2)
                elif sub_choice == "4":
                    break
                else:
                    print("\033[1;31m[!] Lua chon khong hop le.\033[0m")
                    time.sleep(2)
        elif choice == "3":
            while True:
                os.system('clear')
                print("\033[1;35m=== CAI DAT PACKAGE NAME ===\033[0m")
                print(f"\033[1;37mPackage hien tai: {PACKAGE_NAME}\033[0m")
                print("\033[1;35m[1]\033[0m \033[1;37mThay doi Package name\033[0m")
                print("\033[1;35m[2]\033[0m \033[1;37mQuay lai menu chinh\033[0m")
                print("\033[1;35m==================================================\033[0m")
                pkg_choice = input("Chon [1-2]: ").strip()
                
                if pkg_choice == "1":
                    os.system('clear')
                    print("\033[1;35m=== NHAP PACKAGE NAME MOI ===\033[0m")
                    input_pkg = input("Nhap package name (Vi du: com.roblox.client): ").strip()
                    if input_pkg:
                        PACKAGE_NAME = input_pkg
                        print(f"\033[1;37m[+] Da cap nhat Package name thanh: {PACKAGE_NAME}\033[0m")
                    else:
                        print("\033[1;31m[!] Package name khong duoc de meo.\033[0m")
                    time.sleep(2)
                elif pkg_choice == "2":
                    break
                else:
                    print("\033[1;31m[!] Lua chon khong hop le.\033[0m")
                    time.sleep(2)
        elif choice == "4":
            os.system('clear')
            print("\033[1;35m=== CAI DAT ID / LINK PRIVATE ===\033[0m")
            print("\033[1;37mMau co san: Nhap 'blox' de chon Blox Fruit\033[0m")
            print(f"\033[1;37mTarget hien tai: {TARGET_LINK if TARGET_LINK else 'Khong co'}\033[0m\n")
            input_link = input("Nhap Game ID / Link Server Private (de tron de xoa): ").strip()
            
            if input_link.lower() == "blox" or input_link.lower() == "blox fruit":
                TARGET_LINK = "https://www.roblox.com/games/9968396843/Blox-Fruits"
                print("\033[1;37m[+] Da tai mau Blox Fruit thanh cong!\033[0m")
            else:
                TARGET_LINK = input_link
                if TARGET_LINK:
                    print("\033[1;37m[+] Da cap nhat ID/Link Private thanh cong!\033[0m")
                else:
                    print("\033[1;33m[-] Da xoa Target link.\033[0m")
            time.sleep(2)
        elif choice == "5":
            os.system('clear')
            print("\033[1;35m=== CAI DAT WEBHOOK URL ===\033[0m")
            print(f"\033[1;37mWebhook hien tai: {WEBHOOK_URL if WEBHOOK_URL else 'Khong co'}\033[0m\n")
            input_webhook = input("Nhap Link Discord Webhook (de tron de xoa): ").strip()
            WEBHOOK_URL = input_webhook
            if WEBHOOK_URL:
                print("\033[1;37m[+] Da cap nhat Webhook URL thanh cong!\033[0m")
            else:
                print("\033[1;33m[-] Da xoa Webhook.\033[0m")
            time.sleep(2)
        elif choice == "6":
            os.system('clear')
            print("\033[1;35m=== DANG NHAP COOKIE ROBLOX ===\033[0m")
            input_creds = input("Nhap thong tin (username|password|cookie): ").strip()
            if input_creds:
                input_custom_pkg = input("Nhap package name Roblox: ").strip()
                if not input_custom_pkg:
                    input_custom_pkg = "com.roblox.client"
                ROBLOX_CREDENTIALS = input_creds
                PACKAGE_NAME = input_custom_pkg
                print(f"\033[1;37m[+] Dang dang nhap Roblox voi package {PACKAGE_NAME}...\033[0m")
                subprocess.run(["am", "start", "-n", f"{PACKAGE_NAME}/.MainActivity"])
                time.sleep(3)
                print("\033[1;37m[+] Cau hinh va khoi chay ung dung thanh cong!\033[0m")
            else:
                ROBLOX_CREDENTIALS = ""
                print("\033[1;33m[-] Da huong cau hinh dang nhap.\033[0m")
            time.sleep(2)
        elif choice == "7":
            print("\033[1;31mDa thoat tool. Goodbye!\033[0m")
            sys.exit(0)
        else:
            print("\033[1;31m[!] Lua chon khong hop le, vui long chon tu 1 den 7.\033[0m")
            time.sleep(2)