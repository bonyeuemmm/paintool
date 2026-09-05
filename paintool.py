import os
import sys
import time
import subprocess
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

def run_cmd(cmd_list):
    """Chạy lệnh hệ thống an toàn không gây crash C-level"""
    try:
        res = subprocess.run(cmd_list, capture_output=True, text=True, timeout=10)
        return res.stdout.strip()
    except Exception:
        return ""

def get_hwid():
    hwid = run_cmd(["settings", "get", "secure", "android_id"])
    if not hwid or hwid == "null":
        hwid = run_cmd(["getprop", "ro.serialno"])
    if not hwid or hwid == "null":
        hwid = "android_default_hwid"
    return hwid

def check_license_curl(key, hwid):
    try:
        payload = json.dumps({"key": key, "hwid": hwid})
        res_text = run_cmd([
            "curl", "-s", "-X", "POST", API_URL,
            "-H", "Content-Type: application/json",
            "-d", payload,
            "--connect-timeout", "10"
        ])
        
        if not res_text:
            return False, "Khong ket noi duoc den server (Curl Error)"

        try:
            data = json.loads(res_text)
            if isinstance(data, dict):
                is_valid = data.get("valid") is True or data.get("status") == "success"
                return is_valid, res_text
        except Exception:
            pass
            
        is_valid = ("valid" in res_text.lower() and "true" in res_text.lower()) or "success" in res_text.lower()
        return is_valid, res_text
    except Exception as e:
        return False, str(e)

def authenticate():
    global LICENSE_FILE
    hwid = get_hwid()

    if os.path.exists(LICENSE_FILE):
        try:
            with open(LICENSE_FILE, "r") as f:
                input_key = f.read().strip()
            
            if input_key:
                print("\033[1;35m[*] Dang kiem tra Key da luu...\033[0m")
                is_valid, _ = check_license_curl(input_key, hwid)
                if is_valid:
                    print("\033[1;32m[+] Tu dong xac thuc ban quyen thanh cong!\033[0m")
                    time.sleep(1)
                    return
                else:
                    print("\033[1;33m[!] Key luu khong hop le hoac sai HWID. Xoa key cu...\033[0m")
                    if os.path.exists(LICENSE_FILE):
                        os.remove(LICENSE_FILE)
        except Exception:
            pass

    while True:
        os.system('clear')
        print("\033[1;35m==================================================\033[0m")
        print("\033[1;37m          PAIN TOOL REJOIN VIP - XAC THUC         \033[0m")
        print("\033[1;35m==================================================\033[0m")
        print(f"\033[1;36m HWID hien tai: {hwid}\033[0m")
        print("\033[1;37m[!] Vui long nhap Tool Key (pain_key_...) de tiep tuc.\033[0m")
        print("\033[1;35m(Nhap 'exit' hoac '0' de thoat)\033[0m")
        print("\033[1;35m==================================================\033[0m")
        input_key = input("Nhap Key: ").strip()
        
        if input_key in ["exit", "0"]:
            print("\033[1;31mDa thoat chuong trinh. Goodbye!\033[0m")
            sys.exit(0)

        if not input_key:
            continue

        print("\033[1;35m[*] Dang ket noi may chu de xac minh Key...\033[0m")
        is_valid, response_text = check_license_curl(input_key, hwid)

        if is_valid:
            try:
                with open(LICENSE_FILE, "w") as f:
                    f.write(input_key)
            except Exception as write_err:
                print(f"\033[1;33m[!] Canh bao: Khong the luu Key ({write_err})\033[0m")

            print("\033[1;32m[+] Xac thuc Key thanh cong!\033[0m")
            time.sleep(1.5)
            break
        else:
            print("\033[1;31m[!] That bai: Key khong hop le hoac sai HWID.\033[0m")
            print(f"\033[1;33m[*] Phan hoi tu server: {response_text}\033[0m")
            time.sleep(3)

def show_banner():
    os.system('clear')
    target_display = TARGET_LINK if TARGET_LINK else "Chua dat (Rejoin thuong)"
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
            run_cmd(["screencap", "-p", SCREENSHOT_PATH])
            payload_json = json.dumps({"content": message})
            
            if os.path.exists(SCREENSHOT_PATH):
                run_cmd([
                    "curl", "-s", "-X", "POST", WEBHOOK_URL,
                    "-F", f"payload_json={payload_json}",
                    "-F", f"file=@{SCREENSHOT_PATH}"
                ])
            else:
                run_cmd([
                    "curl", "-s", "-X", "POST", WEBHOOK_URL,
                    "-H", "Content-Type: application/json",
                    "-d", payload_json
                ])
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

    send_webhook_with_image(f"[PAIN TOOL] Bat dau theo doi Roblox. Tan suat: {WEBHOOK_INTERVAL} phut/lan.")

    sleep_seconds = DELAY_MINUTES * 60
    interval_seconds = WEBHOOK_INTERVAL * 60
    elapsed_time = 0

    try:
        while True:
            pid = run_cmd(["pidof", PACKAGE_NAME])
            
            if not pid:
                print("\033[1;31m[-] Roblox bi dong hoac vang. Dang mo lai...\033[0m")
                send_webhook_with_image("[PAIN TOOL] Roblox da bi dong hoac vang game! Dang mo lai:")
                if TARGET_LINK:
                    run_cmd(["am", "start", "-a", "android.intent.action.VIEW", "-d", TARGET_LINK, PACKAGE_NAME])
                else:
                    run_cmd(["am", "start", "-n", f"{PACKAGE_NAME}/.MainActivity"])
                time.sleep(10)
                elapsed_time = 0
            else:
                # Gioi han lay 50 dong logcat cuoi cung de TRANH CRASH MEMORY
                log_output = run_cmd(["logcat", "-d", "-t", "50", "-s", "Unity:V", "AndroidRuntime:E"])
                
                if any(k in log_output.lower() for k in ['disconnect', 'kicked', 'lost connection']):
                    print("\033[1;33m[-] Phat hien mat ket noi. Dang vao lai game...\033[0m")
                    send_webhook_with_image("[PAIN TOOL] Phat hien mat ket noi! Dang Rejoin:")
                    run_cmd(["am", "force-stop", PACKAGE_NAME])
                    time.sleep(2)
                    
                    if TARGET_LINK:
                        run_cmd(["am", "start", "-a", "android.intent.action.VIEW", "-d", TARGET_LINK, PACKAGE_NAME])
                    else:
                        run_cmd(["am", "start", "-n", f"{PACKAGE_NAME}/.MainActivity"])
                    time.sleep(10)
                    elapsed_time = 0
            
            run_cmd(["logcat", "-c"])
            
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
                    toggle_val = input("Chon option [1: Bat / 0: Tat]: ").strip()
                    if toggle_val in ["1", "0"]:
                        AUTO_REJOIN = int(toggle_val)
                        print("\033[1;37m[+] Cap nhat Auto Rejoin thanh cong!\033[0m")
                    time.sleep(1.5)
                elif sub_choice == "2":
                    os.system('clear')
                    input_min = input("Nhap thoi gian cho (phut): ").strip()
                    if input_min.isdigit() and int(input_min) > 0:
                        DELAY_MINUTES = int(input_min)
                        print(f"\033[1;37m[+] Da cap nhat thoi gian cho: {DELAY_MINUTES} phut!\033[0m")
                    time.sleep(1.5)
                elif sub_choice == "3":
                    os.system('clear')
                    input_interval = input("Nhap tan suat Webhook (phut): ").strip()
                    if input_interval.isdigit() and int(input_interval) > 0:
                        WEBHOOK_INTERVAL = int(input_interval)
                        print(f"\033[1;37m[+] Da cap nhat tan suat Webhook: {WEBHOOK_INTERVAL} phut!\033[0m")
                    time.sleep(1.5)
                elif sub_choice == "4":
                    break
        elif choice == "3":
            os.system('clear')
            print("\033[1;35m=== CAI DAT PACKAGE NAME ===\033[0m")
            print(f"Package hien tai: {PACKAGE_NAME}")
            input_pkg = input("Nhap package name mới (de trong de giu nguyen): ").strip()
            if input_pkg:
                PACKAGE_NAME = input_pkg
                print(f"\033[1;37m[+] Da cap nhat Package: {PACKAGE_NAME}\033[0m")
            time.sleep(1.5)
        elif choice == "4":
            os.system('clear')
            print("\033[1;35m=== CAI DAT ID / LINK PRIVATE ===\033[0m")
            input_link = input("Nhap Game ID / Link Server Private: ").strip()
            if input_link.lower() in ["blox", "blox fruit"]:
                TARGET_LINK = "https://www.roblox.com/games/9968396843/Blox-Fruits"
            else:
                TARGET_LINK = input_link
            print("\033[1;37m[+] Da cap nhat Target link!\033[0m")
            time.sleep(1.5)
        elif choice == "5":
            os.system('clear')
            print("\033[1;35m=== CAI DAT WEBHOOK URL ===\033[0m")
            WEBHOOK_URL = input("Nhap Link Discord Webhook: ").strip()
            print("\033[1;37m[+] Da cap nhat Webhook URL!\033[0m")
            time.sleep(1.5)
        elif choice == "6":
            os.system('clear')
            print("\033[1;35m=== DANG NHAP COOKIE ROBLOX ===\033[0m")
            ROBLOX_CREDENTIALS = input("Nhap thong tin cookie: ").strip()
            if ROBLOX_CREDENTIALS:
                run_cmd(["am", "start", "-n", f"{PACKAGE_NAME}/.MainActivity"])
                print("\033[1;37m[+] Da khoi chay Roblox!\033[0m")
            time.sleep(1.5)
        elif choice == "7":
            print("\033[1;31mDa thoat tool. Goodbye!\033[0m")
            sys.exit(0)