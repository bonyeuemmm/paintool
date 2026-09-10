import os
import sys
import time
import subprocess
import json
import random
import string
import threading
import urllib.parse
import urllib.request
import sqlite3

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
stop_start = False

def clear_screen():
    os.system('stty sane 2>/dev/null')
    os.system('clear')

def run_cmd(cmd_list):
    try:
        res = subprocess.run(cmd_list, capture_output=True, text=True, timeout=15, stdin=subprocess.DEVNULL)
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
        clear_screen()
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
            parts = line.split(":")
            if len(parts) > 1:
                packages.append(parts[1].strip())
    return packages if packages else [PACKAGE_PREFIX]

def open_game(pkg):
    if TARGET_LINK:
        if TARGET_LINK.isdigit():
            deep_link = f"roblox://placeId={TARGET_LINK}"
            run_cmd(["su", "-c", f"am start -S -W --activity-clear-task -a android.intent.action.VIEW -d {deep_link} {pkg}"])
            run_cmd(["am", "start", "-S", "-W", "-a", "android.intent.action.VIEW", "-d", deep_link, pkg])
        else:
            run_cmd(["su", "-c", f"am start -S -W --activity-clear-task -a android.intent.action.VIEW -d {TARGET_LINK} {pkg}"])
            run_cmd(["am", "start", "-S", "-W", "-a", "android.intent.action.VIEW", "-d", TARGET_LINK, pkg])
    else:
        run_cmd(["su", "-c", f"monkey -p {pkg} -c android.intent.category.LAUNCHER 1"])
        run_cmd(["monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1"])

def close_game(pkg):
    run_cmd(["su", "-c", f"am force-stop {pkg}"])
    run_cmd(["am", "force-stop", pkg])
    run_cmd(["su", "-c", f"pkill -f {pkg}"])
    run_cmd(["su", "-c", f"killall {pkg}"])

def listen_for_stop():
    global stop_start
    while not stop_start:
        try:
            user_input = sys.stdin.readline().strip()
            if user_input == "0":
                stop_start = True
                break
        except:
            break

def start_tool():
    global stop_start
    clear_screen()
    packages = get_all_packages()
    
    print("\033[1;37m[+] PAIN TOOL REJOIN VIP Đang chạy...\033[0m")
    print(f"\033[1;35m[*] Đã tìm thấy {len(packages)} bản clone ({PACKAGE_PREFIX}).\033[0m")
    print("\033[1;33m[*] Bấm phím 0 rồi nhấn Enter bất cứ lúc nào để ngừng Start.\033[0m")
    print("--------------------------------------------------")
    
    for pkg in packages:
        open_game(pkg)
        time.sleep(2)

    send_webhook(f"[PAIN TOOL] Bắt đầu theo dõi {len(packages)} tab. Auto Rejoin Mode: {AUTO_REJOIN_MODE}")

    start_time = time.time()
    last_webhook_time = time.time()
    
    stop_start = False
    listener = threading.Thread(target=listen_for_stop, daemon=True)
    listener.start()

    try:
        while not stop_start:
            current_time = time.time()
            elapsed_minutes = (current_time - start_time) / 60.0
            
            packages = get_all_packages()

            if AUTO_REJOIN_MODE == 1:
                for pkg in packages:
                    if stop_start: break
                    pid = run_cmd(["pidof", pkg])
                    is_running = False
                    
                    if pid:
                        is_running = True
                    else:
                        ps_out = run_cmd(["ps", "-A"])
                        if pkg in ps_out:
                            is_running = True

                    if not is_running:
                        print(f"\033[1;31m[-] {pkg} bị văng! Đang mở lại...\033[0m")
                        open_game(pkg)
                        time.sleep(3)
                    else:
                        log_output = run_cmd(["logcat", "-d", "-t", "200"])
                        error_keywords = ['disconnect', 'kicked', 'lost connection', 'error 277', 'error 268']
                        kicked = False
                        
                        for line in log_output.splitlines():
                            line_lower = line.lower()
                            if "unity" in line_lower or "roblox" in line_lower or pkg in line_lower:
                                if any(k in line_lower for k in error_keywords):
                                    kicked = True
                                    break
                                    
                        if kicked:
                            print(f"\033[1;33m[-] {pkg} mất kết nối! Đang rejoin...\033[0m")
                            close_game(pkg)
                            time.sleep(2)
                            open_game(pkg)
                            time.sleep(3)
                            run_cmd(["logcat", "-c"])

            elif AUTO_REJOIN_MODE == 2:
                if elapsed_minutes >= DELAY_REJOIN_MINUTES:
                    print(f"\033[1;33m[*] Đã qua {DELAY_REJOIN_MINUTES} phút. Đang tiến hành thoát game và đóng đa nhiệm...\033[0m")
                    
                    run_cmd(["input", "keyevent", "3"])
                    time.sleep(2)
                     
                    for pkg in packages:
                        close_game(pkg)
                    time.sleep(3)
                    
                    print("\033[1;32m[*] Đang mở lại game...\033[0m")
                    for pkg in packages:
                        open_game(pkg)
                        time.sleep(2)
                        
                    start_time = time.time()
                    run_cmd(["logcat", "-c"])

            if (current_time - last_webhook_time) >= 300:
                send_webhook("[PAIN TOOL] Cập nhật trạng thái định kỳ (5 phút):", with_image=True)
                last_webhook_time = current_time

            for _ in range(4):
                if stop_start: break
                time.sleep(0.5)

        if stop_start:
            print("\n\033[1;31m[!] Đã dừng Start theo yêu cầu. Đang quay lại menu...\033[0m")
            time.sleep(1.5)
            return

    except KeyboardInterrupt:
        print("\n\033[1;31m[!] Đã dừng Start.\033[0m")
        time.sleep(1)
        return

def show_banner():
    clear_screen()
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
    print("\033[1;35m[6]\033[0m \033[1;37mXử lý Cookie Roblox (Hỗ trợ đọc File TXT)\033[0m")
    print("\033[1;35m[7]\033[0m \033[1;37mXóa cache\033[0m")
    print("\033[1;35m[8]\033[0m \033[1;37mImport auto execute\033[0m")
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
                clear_screen()
                print("\033[1;35m=== SET UP ===\033[0m")
                print("\033[1;37m1. Set up auto rejoin\033[0m")
                print("\033[1;37m2. Chọn game\033[0m")
                print("\033[1;35m3. Quay lại menu chính\033[0m")
                sub = input("Chọn: ").strip()
                
                if sub == "1":
                    clear_screen()
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
                    clear_screen()
                    print("\033[1;35m=== CHỌN GAME ===\033[0m")
                    print("\033[1;37m1. Blox fruit\033[0m")
                    print("\033[1;37m2. Grow a gaden\033[0m")
                    print("\033[1;37m3. Grow a gaden 2\033[0m")
                    print("\033[1;37m4. ID/link private\033[0m")
                    game_choice = input("Chọn game [1-4]: ").strip()
                    
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
                    time.sleep(1)
                elif sub == "3":
                    break
                    
        elif choice == "3":
            clear_screen()
            print("\033[1;35m=== CÀI ĐẶT PACKAGE PREFIX ===\033[0m")
            pref = input("Nhập Package Prefix (Để trống để giữ mặc định): ").strip()
            if pref:
                PACKAGE_PREFIX = pref
            
        elif choice == "4":
            clear_screen()
            print("\033[1;35m=== ĐỔI ID THIẾT BỊ ===\033[0m")
            print("\033[1;33m(Yêu cầu máy đã Root hoặc cấp quyền ADB)\033[0m")
            new_id = input("Nhập ID mới (Để trống để tạo ngẫu nhiên): ").strip()
            if not new_id:
                new_id = "".join(random.choices(string.hexdigits.lower(), k=16))
            run_cmd(["su", "-c", f"settings put secure android_id {new_id}"])
            print(f"\033[1;32m[+] Đã yêu cầu đổi ID thành: {new_id}\033[0m")
            time.sleep(2)
            
        elif choice == "5":
            clear_screen()
            print("\033[1;35m=== CÀI ĐẶT WEBHOOK URL ===\033[0m")
            url = input("Nhập Link Discord Webhook (Để trống để xóa): ").strip()
            WEBHOOK_URL = url
            if WEBHOOK_URL:
                print("\033[1;32m[+] Đã lưu! Đang gửi tin nhắn test...\033[0m")
                send_webhook("Mới kích hoạt và gửi đến discord.")
            time.sleep(1.5)
            
        elif choice == "6":
            clear_screen()
            print("\033[1;35m=== ĐĂNG NHẬP COOKIE ROBLOX (FILE & DIRECT ENGINE) ===\033[0m")
            print("\033[1;36m1. Nhập trực tiếp chuỗi Cookie/Text\033[0m")
            print("\033[1;36m2. Đọc từ file .txt trên bộ nhớ (Khuyên dùng để tránh lỗi tràn bàn phím)\033[0m")
            input_mode = input("Chọn phương thức nhập [1/2]: ").strip()

            raw_input_data = ""
            if input_mode == "2":
                file_path = input("Nhập đường dẫn file chứa cookie (VD: /sdcard/cookie.txt): ").strip()
                if os.path.exists(file_path):
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            raw_input_data = f.read().strip()
                        print(f"\033[1;32m[+] Đã đọc thành công file: {file_path}\033[0m")
                    except Exception as fe:
                        print(f"\033[1;31m[-] Lỗi đọc file: {str(fe)}\033[0m")
                        time.sleep(2)
                        continue
                else:
                    print(f"\033[1;31m[-] Không tìm thấy file tại đường dẫn: {file_path}\033[0m")
                    time.sleep(2)
                    continue
            else:
                raw_input_data = input("Dán toàn bộ thông tin (user|pass|cookie hoặc cookie): ").strip()

            if not raw_input_data:
                continue
                
            target_pkg = input("Nhập package name để đăng nhập (Ví dụ: com.roblox.client): ").strip()
            if not target_pkg:
                continue

            try:
                cookie_val = ""
                if "_|WARNING" in raw_input_data:
                    start_idx = raw_input_data.find("_|WARNING")
                    # Cắt chuỗi từ _|WARNING đến hết ký tự hợp lệ của cookie (thường dài khoảng 600-700 ký tự)
                    sub_part = raw_input_data[start_idx:]
                    end_idx = len(sub_part)
                    for char_idx, char in enumerate(sub_part):
                        if char in ['\n', '\r', ' ', '"', "'", '|', ';', ',']:
                            end_idx = char_idx
                            break
                    cookie_val = sub_part[:end_idx].strip()
                elif "|" in raw_input_data:
                    parts = raw_input_data.split("|")
                    for p in parts:
                        if "_|WARNING" in p or len(p.strip()) > 100:
                            cookie_val = p.strip()
                            break
                    if not cookie_val and len(parts) > 0:
                        cookie_val = parts[-1].strip()
                else:
                    cookie_val = raw_input_data.replace('"', '').replace("'", "").strip()

                cookie_val = cookie_val.split()[0] if cookie_val else ""
                
                if not cookie_val.startswith("_|WARNING"):
                    print("\033[1;31m[-] Cảnh báo: Không tìm thấy định dạng chuẩn '_|WARNING...' trong chuỗi xử lý!\033[0m")
                    time.sleep(2.5)
                    continue

                print("\033[1;33m[*] Đang xác thực tính hợp lệ của Cookie qua API Roblox...\033[0m")
                try:
                    req_auth = urllib.request.Request(
                        "https://users.roblox.com/v1/users/authenticated",
                        headers={
                            "Cookie": f".ROBLOSECURITY={cookie_val}",
                            "User-Agent": "Roblox/WinInet"
                        }
                    )
                    with urllib.request.urlopen(req_auth, timeout=10) as response:
                        user_data = json.loads(response.read().decode())
                        username_check = user_data.get("name", "Unknown")
                        user_id_check = user_data.get("id", "Unknown")
                        print(f"\033[1;32m[+] Xác thực thành công tài khoản: {username_check} (ID: {user_id_check})\033[0m")
                except Exception as api_err:
                    print(f"\033[1;31m[-] Cookie không hợp lệ hoặc đã hết hạn (Lỗi API: {str(api_err)})\033[0m")
                    proceed_anyway = input("Bạn có muốn tiếp tục ép tiêm cookie này không? (y/n): ").strip().lower()
                    if proceed_anyway != 'y':
                        continue

                print(f"\033[1;33m[*] Đang đóng hoàn toàn {target_pkg}...\033[0m")
                close_game(target_pkg)
                time.sleep(1)

                app_uid = run_cmd(["su", "-c", f"stat -c '%u:%g' /data/data/{target_pkg}"])
                if not app_uid or ":" not in app_uid:
                    app_uid = run_cmd(["su", "-c", f"dumpsys package {target_pkg} | grep userId="])
                    if "=" in app_uid:
                        uid_num = app_uid.split("=")[1].split()[0]
                        app_uid = f"{uid_num}:{uid_num}"
                    else:
                        app_uid = ""

                print("\033[1;33m[*] Đang xóa bộ nhớ đệm ứng dụng cũ...\033[0m")
                run_cmd(["su", "-c", f"rm -rf /data/data/{target_pkg}/app_webview/Default/*"])
                run_cmd(["su", "-c", f"rm -rf /data/data/{target_pkg}/app_webview/Local\\ Storage/*"])
                run_cmd(["su", "-c", f"rm -rf /data/data/{target_pkg}/cache/*"])

                prefs_dir = f"/data/data/{target_pkg}/shared_prefs"
                prefs_path = f"{prefs_dir}/com.roblox.robloxmobile.xml"
                run_cmd(["su", "-c", f"mkdir -p {prefs_dir}"])
                run_cmd(["su", "-c", f"rm -f {prefs_path}"])
                
                xml_content = f'''<?xml version='1.0' encoding='utf-8' standalone='yes' ?>
<map>
    <boolean name="IsLoggedIn" value="true" />
    <string name="ROBLOSECURITY">{cookie_val}</string>
    <string name="GuestData">{cookie_val}</string>
    <string name="RobloxAnalyticsSessionId">{random.randint(100000000, 999999999)}</string>
</map>'''
                
                temp_xml = "/sdcard/temp_roblox_cookie.xml"
                with open(temp_xml, "w", encoding="utf-8") as f:
                    f.write(xml_content)
                
                run_cmd(["su", "-c", f"cp {temp_xml} {prefs_path}"])
                if app_uid:
                    run_cmd(["su", "-c", f"chown -R {app_uid} {prefs_dir}"])
                run_cmd(["su", "-c", f"chmod 777 {prefs_dir}"])
                run_cmd(["su", "-c", f"chmod 666 {prefs_path}"])
                run_cmd(["su", "-c", f"restorecon -R {prefs_dir}"])
                
                cookies_dir = f"/data/data/{target_pkg}/app_webview/Default/Network"
                cookies_db = f"{cookies_dir}/Cookies"
                run_cmd(["su", "-c", f"mkdir -p {cookies_dir}"])
                
                temp_db = "/sdcard/temp_cookies.db"
                if os.path.exists(temp_db):
                    os.remove(temp_db)
                
                conn = sqlite3.connect(temp_db)
                cursor = conn.cursor()
                cursor.execute("PRAGMA user_version = 18;")
                
                cursor.execute("""
                    CREATE TABLE cookies (
                        creation_utc INTEGER NOT NULL,
                        host_key TEXT NOT NULL,
                        top_level_site TEXT NOT NULL,
                        name TEXT NOT NULL,
                        value TEXT NOT NULL,
                        path TEXT NOT NULL,
                        expires_utc INTEGER NOT NULL,
                        is_secure INTEGER NOT NULL,
                        is_httponly INTEGER NOT NULL,
                        last_access_utc INTEGER NOT NULL,
                        has_expires INTEGER NOT NULL,
                        is_persistent INTEGER NOT NULL,
                        priority INTEGER NOT NULL,
                        samesite INTEGER NOT NULL,
                        source_scheme INTEGER NOT NULL,
                        source_port INTEGER NOT NULL,
                        is_same_party INTEGER NOT NULL DEFAULT 0,
                        last_update_utc INTEGER NOT NULL DEFAULT 0
                    )
                """)
                
                import time as t
                epoch_now = int(t.time() * 1000000 + 11644473600000000)
                epoch_expires = int((t.time() + 31536000) * 1000000 + 11644473600000000)
                
                hosts = [".roblox.com", "roblox.com", ".www.roblox.com", "www.roblox.com", "web.roblox.com", ".web.roblox.com"]
                for h in hosts:
                    cursor.execute(
                        "INSERT INTO cookies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (epoch_now, h, "", ".ROBLOSECURITY", cookie_val, "/", epoch_expires, 1, 1, epoch_now, 1, 1, 1, 0, 2, 443, 0, epoch_now)
                    )
                
                conn.commit()
                conn.close()
                
                run_cmd(["su", "-c", f"cp {temp_db} {cookies_db}"])
                if app_uid:
                    run_cmd(["su", "-c", f"chown -R {app_uid} {cookies_dir}"])
                run_cmd(["su", "-c", f"chmod 777 {cookies_dir}"])
                run_cmd(["su", "-c", f"chmod 666 {cookies_db}"])
                run_cmd(["su", "-c", f"restorecon -R {cookies_dir}"])
                
                if os.path.exists(temp_xml):
                    os.remove(temp_xml)
                if os.path.exists(temp_db):
                    os.remove(temp_db)
                
                print(f"\033[1;32m[+] Tiêm Cookie thành công tuyệt đối cho gói: {target_pkg}!\033[0m")
                print(f"\033[1;36m[*] Đang khởi động lại ứng dụng...\033[0m")
                time.sleep(1)
                
                open_game(target_pkg)
                
            except Exception as e:
                print(f"\033[1;31m[-] Lỗi tiêm cookie: {str(e)}\033[0m")
            time.sleep(2.5)
            
        elif choice == "7":
            clear_screen()
            print("\033[1;35m=== XÓA CACHE TẤT CẢ GAME ===\033[0m")
            packages = get_all_packages()
            for pkg in packages:
                print(f"[*] Đang dọn cache cho: {pkg}")
                run_cmd(["su", "-c", f"rm -rf /data/data/{pkg}/cache/*"])
            print("\033[1;32m[+] Hoàn tất dọn dẹp!\033[0m")
            time.sleep(2)
            
        elif choice == "8":
            clear_screen()
            print("\033[1;35m=== IMPORT AUTO EXECUTE ===\033[0m")
            script_data = input("Nhập script hack (Để trống để thoát): ").strip()
            if not script_data:
                continue
                
            temp_path = "/sdcard/temp_autoexec.lua"
            try:
                with open(temp_path, "w", encoding="utf-8") as f:
                    f.write(script_data)
            except Exception:
                run_cmd(["su", "-c", f"echo '{script_data}' > {temp_path}"])

            executor_names = ["Delta", "Codex", "Arceus", "ArceusX", "Fluxus", "Hydrogen", "Valyse", "VegaX", "Krampus", "Evon"]
            autoexec_subdirs = ["autoexec", "Autoexec", "auto-execute", "AutoExecute", "scripts", "Scripts"]
            
            target_dirs = set()

            for name in executor_names:
                base_dir = f"/sdcard/{name}"
                if os.path.exists(base_dir) or run_cmd(["su", "-c", f"test -d {base_dir} && echo 1"]) == "1":
                    found_sub = False
                    for sub in autoexec_subdirs:
                        sub_path = f"{base_dir}/{sub}"
                        if os.path.exists(sub_path) or run_cmd(["su", "-c", f"test -d {sub_path} && echo 1"]) == "1":
                            target_dirs.add(sub_path)
                            found_sub = True
                    if not found_sub:
                        target_dirs.add(f"{base_dir}/Autoexec")

            packages = get_all_packages()
            for pkg in packages:
                target_dirs.add(f"/sdcard/Android/data/{pkg}/files/autoexec")
                target_dirs.add(f"/sdcard/Android/data/{pkg}/files/Autoexec")
                target_dirs.add(f"/data/data/{pkg}/autoexec")
                target_dirs.add(f"/data/data/{pkg}/Autoexec")

            print(f"[*] Đang ghi file script vào {len(target_dirs)} vị trí Autoexec...")
            for target in target_dirs:
                run_cmd(["mkdir", "-p", target])
                run_cmd(["su", "-c", f"mkdir -p {target}"])
                
                run_cmd(["cp", temp_path, f"{target}/script.lua"])
                run_cmd(["su", "-c", f"cp {temp_path} {target}/script.lua"])

            try:
                os.remove(temp_path)
            except:
                run_cmd(["rm", temp_path])
                
            print("\033[1;32m[+] Đã quét và lưu script vào tất cả thư mục Autoexec thành công!\033[0m")
            time.sleep(2.5)
                
        elif choice == "9":
            clear_screen()
            print(f"\033[1;35m=== MỞ HÀNG LOẠT TAB CLONE ===\033[0m")
            print(f"\033[1;33m[*] Đang quét các ứng dụng có chứa '{PACKAGE_PREFIX}'...\033[0m")
            
            output = run_cmd(["pm", "list", "packages"])
            found_pkgs = []
            for line in output.splitlines():
                if PACKAGE_PREFIX in line:
                    parts = line.split(":")
                    if len(parts) > 1:
                        found_pkgs.append(parts[1].strip())
            
            if not found_pkgs:
                print(f"\033[1;31m[-] Không tìm thấy ứng dụng nào chứa prefix: {PACKAGE_PREFIX}\033[0m")
                print(f"\033[1;33m[*] Thử mở gói mặc định: {PACKAGE_PREFIX}\033[0m")
                found_pkgs = [PACKAGE_PREFIX]
            else:
                print(f"\033[1;32m[+] Tìm thấy {len(found_pkgs)} ứng dụng!\033[0m")
                
            for pkg in found_pkgs:
                print(f"[*] Đang mở: {pkg}")
                open_game(pkg)
                time.sleep(1.5)
            print("\033[1;32m[+] Hoàn tất mở tab clone!\033[0m")
            time.sleep(2)
            
        elif choice == "0":
            print("\033[1;31mĐã thoát tool. Goodbye!\033[0m")
            sys.exit(0)