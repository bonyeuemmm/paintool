import os
import sys
import time
import subprocess
import json
import random
import string
import select
import urllib.parse

API_URL = "https://discord-license-bot-production.up.railway.app/api/verify"
LICENSE_FILE = os.path.join(os.path.expanduser("~"), ".pain_license")

PACKAGE_PREFIX = "com.roblox"
TARGET_LINK = ""
SELECTED_GAME_NAME = "Chưa chọn"
WEBHOOK_URL = ""
ROBLOX_CREDENTIALS = ""
SCREENSHOT_PATH = "/sdcard/pain_screenshot.png"

AUTO_REJOIN_MODE = 1
DELAY_REJOIN_MINUTES = 1

def run_cmd(cmd_list):
    try:
        res = subprocess.run(cmd_list, capture_output=True, text=True, timeout=15)
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
            return False, "Không kết nối được server"

        try:
            data = json.loads(res_text)
            if isinstance(data, dict):
                return data.get("valid") is True or data.get("status") == "success", res_text
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
                print("\033[1;35m[*] Đang kiểm tra Key đã lưu...\033[0m")
                is_valid, _ = check_license_curl(input_key, hwid)
                if is_valid:
                    print("\033[1;32m[+] Tự động xác thực bản quyền thành công!\033[0m")
                    time.sleep(1)
                    return
                else:
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
        input_key = input("Nhập Key (0 để thoát): ").strip()
        
        if input_key in ["exit", "0"]:
            sys.exit(0)
        if not input_key:
            continue

        print("\033[1;35m[*] Đang kết nối máy chủ...\033[0m")
        is_valid, response_text = check_license_curl(input_key, hwid)

        if is_valid:
            try:
                with open(LICENSE_FILE, "w") as f:
                    f.write(input_key)
            except:
                pass
            print("\033[1;32m[+] Xác thực Key thành công!\033[0m")
            time.sleep(1)
            break
        else:
            print("\033[1;31m[!] Thất bại: Key không hợp lệ hoặc sai HWID.\033[0m")
            time.sleep(2)

def send_webhook(message, with_image=False):
    if not WEBHOOK_URL:
        return
    try:
        payload_json = json.dumps({"content": message})
        if with_image:
            run_cmd(["screencap", "-p", SCREENSHOT_PATH])
            if os.path.exists(SCREENSHOT_PATH):
                run_cmd([
                    "curl", "-s", "-X", "POST", WEBHOOK_URL,
                    "-F", f"payload_json={payload_json}",
                    "-F", f"file=@{SCREENSHOT_PATH}"
                ])
                return
        run_cmd([
            "curl", "-s", "-X", "POST", WEBHOOK_URL,
            "-H", "Content-Type: application/json",
            "-d", payload_json
        ])
    except Exception:
        pass

def get_all_packages():
    output = run_cmd(["pm", "list", "packages"])
    packages = []
    for line in output.splitlines():
        if PACKAGE_PREFIX in line:
            packages.append(line.split(":")[1].strip())
    return packages if packages else [PACKAGE_PREFIX]

def open_game(pkg):
    if TARGET_LINK:
        if TARGET_LINK.isdigit():
            deep_link = f"roblox://placeId={TARGET_LINK}"
            run_cmd(["am", "start", "-W", "-a", "android.intent.action.VIEW", "-d", deep_link, pkg])
        else:
            run_cmd(["am", "start", "-W", "-a", "android.intent.action.VIEW", "-d", TARGET_LINK, pkg])
    else:
        run_cmd(["am", "start", "-W", "-n", f"{pkg}/.MainActivity"])

def close_game(pkg):
    run_cmd(["am", "force-stop", pkg])

def start_tool():
    os.system('clear')
    packages = get_all_packages()
    
    print("\033[1;37m[+] PAIN TOOL REJOIN VIP Đang chạy...\033[0m")
    print(f"\033[1;35m[*] Đã tìm thấy {len(packages)} bản clone ({PACKAGE_PREFIX}).\033[0m")
    print("\033[1;33m[*] Bấm phím 0 rồi nhấn Enter bất cứ lúc nào để ngừng Start.\033[0m")
    print("--------------------------------------------------")
    
    for pkg in packages:
        open_game(pkg)
        time.sleep(2)

    send_webhook(f"[PAIN TOOL] Bắt đầu theo dõi {len(packages)} tab. Auto Rejoin Mode: {AUTO_REJOIN_MODE}")

    minutes_passed = 0
    try:
        while True:
            
            for _ in range(60):
                if select.select([sys.stdin], [], [], 1)[0]:
                    cmd_input = sys.stdin.readline().strip()
                    if cmd_input == "0":
                        print("\n\033[1;31m[!] Đã dừng Start theo yêu cầu. Đang quay lại menu...\033[0m")
                        time.sleep(1.5)
                        return
            
            minutes_passed += 1
            packages = get_all_packages()

            if AUTO_REJOIN_MODE == 1:
                for pkg in packages:
                    pid = run_cmd(["pidof", pkg])
                    if not pid:
                        print(f"\033[1;31m[-] {pkg} bị văng! Đang mở lại...\033[0m")
                        open_game(pkg)
                        time.sleep(3)
                    else:
                        log_output = run_cmd(["logcat", "-d", "-t", "100", "-s", "Unity:V", "AndroidRuntime:E"])
                        if any(k in log_output.lower() for k in ['disconnect', 'kicked', 'lost connection']):
                            print(f"\033[1;33m[-] {pkg} mất kết nối! Đang rejoin...\033[0m")
                            close_game(pkg)
                            time.sleep(2)
                            open_game(pkg)
                            time.sleep(3)
                run_cmd(["logcat", "-c"]) 

            elif AUTO_REJOIN_MODE == 2:
                if minutes_passed % DELAY_REJOIN_MINUTES == 0:
                    print("\033[1;33m[*] Tới chu kỳ Delay Rejoin. Đang khởi động lại toàn bộ tab...\033[0m")
                    for pkg in packages:
                        close_game(pkg)
                    time.sleep(3)
                    for pkg in packages:
                        open_game(pkg)
                        time.sleep(2)

            if minutes_passed % 5 == 0:
                send_webhook("[PAIN TOOL] Cập nhật trạng thái định kỳ (5 phút):", with_image=True)

    except KeyboardInterrupt:
        print("\n\033[1;31m[!] Đã dừng Start.\033[0m")
        time.sleep(1)
        return

def show_banner():
    os.system('clear')
    rejoin_mode_str = "Quét Kick/Văng" if AUTO_REJOIN_MODE == 1 else f"Delay Rejoin ({DELAY_REJOIN_MINUTES}p)"
    
    print("\033[1;35m==================================================\033[0m")
    print("\033[1;37m             PAIN TOOL REJOIN VIP                 \033[0m")
    print("\033[1;35m==================================================\033[0m")
    print(f"\033[1;35m Package Prefix  :\033[0m \033[1;37m{PACKAGE_PREFIX}\033[0m")
    print(f"\033[1;35m Chế độ Game     :\033[0m \033[1;37m{SELECTED_GAME_NAME}\033[0m")
    print(f"\033[1;35m Cơ chế Rejoin   :\033[0m \033[1;37m{rejoin_mode_str}\033[0m")
    print(f"\033[1;35m Webhook URL     :\033[0m \033[1;37m{'Đã cấu hình' if WEBHOOK_URL else 'Chưa đặt'}\033[0m")
    print("\033[1;35m==================================================\033[0m")
    print("\033[1;35m[1]\033[0m \033[1;37mStart\033[0m")
    print("\033[1;35m[2]\033[0m \033[1;37mSet up\033[0m")
    print("\033[1;35m[3]\033[0m \033[1;37mPackage prefix\033[0m")
    print("\033[1;35m[4]\033[0m \033[1;37mChange id\033[0m")
    print("\033[1;35m[5]\033[0m \033[1;37mUrl webhook\033[0m")
    print("\033[1;35m[6]\033[0m \033[1;37mLogin cookie roblox\033[0m")
    print("\033[1;35m[7]\033[0m \033[1;37mXóa cache\033[0m")
    print("\033[1;35m[8]\033[0m \033[1;37mBypass key delta x\033[0m")
    print("\033[1;35m[9]\033[0m \033[1;37mMở tab clone\033[0m")
    print("\033[1;31m[0] Exit\033[0m")
    print("\033[1;35m==================================================\033[0m")

if __name__ == "__main__":
    authenticate()

    while True:
        show_banner()
        choice = input("Chọn chức năng [0-9]: ").strip()
        
        if choice == "1":
            start_tool()
            
        elif choice == "2":
            while True:
                os.system('clear')
                print("\033[1;35m=== SET UP ===\033[0m")
                print("\033[1;37m1. Set up auto rejoin\033[0m")
                print("\033[1;37m2. Chọn game\033[0m")
                print("\033[1;35m3. Quay lại menu chính\033[0m")
                sub = input("Chọn: ").strip()
                
                if sub == "1":
                    os.system('clear')
                    print("\033[1;35m=== SET UP AUTO REJOIN ===\033[0m")
                    print("\033[1;37m1. Auto rejoin khi bị kick/văng (Thông minh)\033[0m")
                    print("\033[1;37m2. Delay rejoin (Đóng & mở lại theo chu kỳ)\033[0m")
                    mode = input("Chọn cơ chế [1/2]: ").strip()
                    if mode == "1":
                        AUTO_REJOIN_MODE = 1
                        print("\033[1;32m[+] Đã chọn Auto Rejoin thông minh!\033[0m")
                    elif mode == "2":
                        AUTO_REJOIN_MODE = 2
                        mins = input("Nhập thời gian chu kỳ (phút): ").strip()
                        if mins.isdigit() and int(mins) > 0:
                            DELAY_REJOIN_MINUTES = int(mins)
                            print(f"\033[1;32m[+] Đã cài Delay Rejoin {DELAY_REJOIN_MINUTES} phút!\033[0m")
                    time.sleep(1.5)
                    
                elif sub == "2":
                    os.system('clear')
                    print("\033[1;35m=== CHỌN GAME ===\033[0m")
                    print("\033[1;37m1. Blox fruit\033[0m")
                    print("\033[1;37m2. Grow a gaden\033[0m")
                    print("\033[1;37m3. Grow a gaden 2\033[0m")
                    print("\033[1;37m4. ID/link private\033[0m")
                    game_choice = input("Chọn game [1-4] hoặc dán luôn ID: ").strip()
                    
                    if game_choice == "1":
                        TARGET_LINK = "9968396843"
                        SELECTED_GAME_NAME = "Blox fruit"
                    elif game_choice == "2":
                        TARGET_LINK = "11790933930"
                        SELECTED_GAME_NAME = "Grow a gaden"
                    elif game_choice == "3":
                        TARGET_LINK = "11790933930"
                        SELECTED_GAME_NAME = "Grow a gaden 2"
                    elif game_choice == "4":
                        link = input("Nhập ID game hoặc Link Server VIP: ").strip()
                        if link:
                            TARGET_LINK = link
                            if link.isdigit():
                                SELECTED_GAME_NAME = f"Game ID: {link}"
                                print(f"\033[1;32m[+] Đã nhận Game ID: {link}\033[0m")
                            else:
                                SELECTED_GAME_NAME = "Server VIP Custom"
                                print(f"\033[1;32m[+] Đã nhận Link Server VIP!\033[0m")
                            time.sleep(1.5)
                    elif len(game_choice) > 4: 
                        TARGET_LINK = game_choice
                        if game_choice.isdigit():
                            SELECTED_GAME_NAME = f"Game ID: {game_choice}"
                            print(f"\033[1;32m[+] Tự động nhận Game ID: {game_choice}\033[0m")
                        else:
                            SELECTED_GAME_NAME = "Server VIP Custom"
                            print(f"\033[1;32m[+] Tự động nhận Link Server VIP!\033[0m")
                        time.sleep(1.5)
                    time.sleep(1)
                elif sub == "3":
                    break
                    
        elif choice == "3":
            os.system('clear')
            print("\033[1;35m=== CÀI ĐẶT PACKAGE PREFIX ===\033[0m")
            pref = input("Nhập Package Prefix (Để trống để giữ mặc định): ").strip()
            if pref:
                PACKAGE_PREFIX = pref
            
        elif choice == "4":
            os.system('clear')
            print("\033[1;35m=== ĐỔI ID THIẾT BỊ ===\033[0m")
            print("\033[1;33m(Yêu cầu máy đã Root hoặc cấp quyền ADB)\033[0m")
            new_id = input("Nhập ID mới (Để trống để tạo ngẫu nhiên): ").strip()
            if not new_id:
                new_id = "".join(random.choices(string.hexdigits.lower(), k=16))
            run_cmd(["su", "-c", f"settings put secure android_id {new_id}"])
            print(f"\033[1;32m[+] Đã yêu cầu đổi ID thành: {new_id}\033[0m")
            time.sleep(2)
            
        elif choice == "5":
            os.system('clear')
            print("\033[1;35m=== CÀI ĐẶT WEBHOOK URL ===\033[0m")
            url = input("Nhập Link Discord Webhook (Để trống để xóa): ").strip()
            WEBHOOK_URL = url
            if WEBHOOK_URL:
                print("\033[1;32m[+] Đã lưu! Đang gửi tin nhắn test...\033[0m")
                send_webhook("Mới kích hoạt và gửi đến discord.")
            time.sleep(1.5)
            
        elif choice == "6":
            os.system('clear')
            print("\033[1;35m=== ĐĂNG NHẬP COOKIE ROBLOX ===\033[0m")
            ROBLOX_CREDENTIALS = input("Nhập thông tin cookie: ").strip()
            if ROBLOX_CREDENTIALS:
                print("\033[1;32m[+] Đã ghi nhận Cookie!\033[0m")
            time.sleep(1.5)
            
        elif choice == "7":
            os.system('clear')
            print("\033[1;35m=== XÓA CACHE TẤT CẢ GAME ===\033[0m")
            packages = get_all_packages()
            for pkg in packages:
                print(f"[*] Đang dọn cache cho: {pkg}")
                run_cmd(["su", "-c", f"rm -rf /data/data/{pkg}/cache/*"])
            print("\033[1;32m[+] Hoàn tất dọn dẹp!\033[0m")
            time.sleep(2)
            
        elif choice == "8":
            os.system('clear')
            print("\033[1;35m=== BYPASS KEY DELTA X ===\033[0m")
            link = input("Dán link Delta X để bypass (Để trống để thoát): ").strip()
            if link:
                print("\033[1;33m[*] Đang tiến hành xử lý bypass qua API gốc Delta...\033[0m")
                
                parsed_url = urllib.parse.urlparse(link)
                query_params = urllib.parse.parse_qs(parsed_url.query)
                hwid_val = query_params.get("hwid", [""])[0] or query_params.get("token", [""])[0] or query_params.get("id", [""])[0]
                
                if not hwid_val:
                    path_parts = [p for p in parsed_url.path.strip("/").split("/") if p]
                    if path_parts:
                        hwid_val = path_parts[-1]
                
                if not hwid_val:
                    hwid_val = link.strip()

                encoded_hwid = urllib.parse.quote(hwid_val, safe='')
                encoded_link = urllib.parse.quote(link, safe='')
                
                api_endpoints = [
                    f"https://api.platoboost.com/public/v1/bypass?url={encoded_link}",
                    f"https://api.delta-enexploit.net/public/bypass?hwid={encoded_hwid}",
                    f"https://bypass.donat-api.workers.dev/delta?link={encoded_link}",
                    f"https://api.keyrblx.com/public/delta?link={encoded_link}",
                    f"https://api.bypass.vip/public/delta?link={encoded_link}"
                ]
                
                key_result = ""
                res_text = ""
                
                for api in api_endpoints:
                    res_text = run_cmd([
                        "curl", "-s", "-L", "-X", "GET", api,
                        "-H", "User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
                        "-H", "Accept: application/json, text/plain, */*",
                        "-H", "Origin: https://gateway.platoboost.com",
                        "-H", "Referer: https://gateway.platoboost.com/",
                        "--connect-timeout", "15"
                    ])
                    
                    if not res_text or "<html>" in res_text.lower():
                        continue
                        
                    try:
                        data = json.loads(res_text)
                        if isinstance(data, dict):
                            key_result = (
                                data.get("key") or 
                                data.get("result") or 
                                data.get("bypassed") or 
                                data.get("data") or 
                                data.get("keyz") or
                                data.get("message")
                            )
                            if key_result and "http" not in str(key_result) and len(str(key_result)) < 120:
                                break
                            else:
                                key_result = ""
                    except:
                        if res_text and len(res_text) < 150 and "error" not in res_text.lower():
                            key_result = res_text
                            break

                print("\033[1;32m[+] Bypass hoàn tất!\033[0m")
                if key_result:
                    print(f"\033[1;37m[KEY CỦA BẠN]: \033[1;32m{key_result}\033[0m\n")
                else:
                    print(f"\033[1;31m[!] Các API công cộng hiện tại đã bị Cloudflare chặn hoặc thay đổi cấu trúc.\033[0m")
                    print(f"\033[1;31m[-] Phản hồi gần nhất: {res_text[:150]}\033[0m\n")
                
                while True:
                    back = input("\033[1;33mBấm phím 0 để quay lại giao diện chính: \033[0m").strip()
                    if back == "0":
                        break
                
        elif choice == "9":
            os.system('clear')
            packages = get_all_packages()
            print(f"\033[1;35m=== MỞ HÀNG LOẠT TAB CLONE ({len(packages)} ỨNG DỤNG) ===\033[0m")
            for pkg in packages:
                print(f"[*] Đang mở: {pkg}")
                open_game(pkg)
                time.sleep(1.5)
            print("\033[1;32m[+] Hoàn tất!\033[0m")
            time.sleep(2)
            
        elif choice == "0":
            print("\033[1;31mĐã thoát tool. Goodbye!\033[0m")
            sys.exit(0)