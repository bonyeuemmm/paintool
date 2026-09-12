name=paintool.py
import os
import sys
import time
import subprocess
import json
import random
import string
import threading
import sqlite3

API_URL = "https://discord-license-bot-production.up.railway.app/api/verify"
LICENSE_FILE = os.path.join(os.path.expanduser("~"), ".pain_license")

PACKAGE_PREFIX = "com.roblox"
TARGET_LINK = ""
SELECTED_GAME_NAME = "Chưa chọn"
WEBHOOK_URL = ""
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
                    print(f"\033[1;33m[*] Đã qua {DELAY_REJOIN_MINUTES} phút. Đang tiến hành đóng đa nhiệm...\033[0m")
                    
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

def inject_cookie_v2(target_pkg, raw_cookie):
    run_cmd(["su", "-c", "setenforce 0"])
    close_game(target_pkg)
    time.sleep(1)

    cookie_val = raw_cookie.strip()
    if "_|WARNING" in cookie_val:
        idx = cookie_val.find("_|WARNING")
        cookie_val = cookie_val[idx:]
    cookie_val = cookie_val.split()[0].replace('"', '').replace("'", "").strip()

    if not cookie_val.startswith("_|WARNING"):
        print("\033[1;31m[-] Lỗi: Cookie thiếu chuỗi _|WARNING!\033[0m")
        return False

    app_data = f"/data/data/{target_pkg}"
    
    check_exist = run_cmd(["su", "-c", f"test -d {app_data} && echo 1"])
    if check_exist != "1":
        print(f"\033[1;31m[-] Không tìm thấy thư mục dữ liệu của {target_pkg}. Hãy mở game ít nhất 1 lần trước khi tiêm!\033[0m")
        return False

    uid_str = run_cmd(["su", "-c", f"stat -c %u {app_data}"])
    uid = int(uid_str) if uid_str.isdigit() else 10000

    prefs_dir = f"{app_data}/shared_prefs"
    run_cmd(["su", "-c", f"mkdir -p {prefs_dir}"])
    
    xml_content = f'''<?xml version='1.0' encoding='utf-8' standalone='yes' ?>
<map>
    <boolean name="IsLoggedIn" value="true" />
    <string name="ROBLOSECURITY">{cookie_val}</string>
    <string name="GuestData">{cookie_val}</string>
    <string name="AppSessionId">{random.randint(100000000, 999999999)}</string>
    <boolean name="PerformCentralizedLogin" value="false" />
    <string name="RBXSessionInfo">logged_in</string>
</map>'''

    tmp_xml = "/sdcard/pain_prefs.xml"
    try:
        with open(tmp_xml, "w", encoding="utf-8") as f:
            f.write(xml_content)
    except Exception as e:
        print(f"[-] Lỗi ghi file tạm: {e}")
        return False

    xml_targets = [
        f"{prefs_dir}/{target_pkg}_preferences.xml",
        f"{prefs_dir}/com.roblox.robloxmobile.xml",
        f"{prefs_dir}/RBXAuthentication.xml"
    ]

    for xt in xml_targets:
        run_cmd(["su", "-c", f"cp {tmp_xml} {xt}"])

    webview_cookie_path = f"{app_data}/app_webview/Default/Cookies"
    if run_cmd(["su", "-c", f"test -f {webview_cookie_path} && echo 1"]) == "1":
        run_cmd(["su", "-c", f"rm -f {webview_cookie_path}"])

    run_cmd(["su", "-c", f"chown -R {uid}:{uid} {app_data}"])
    run_cmd(["su", "-c", f"chmod -R 777 {app_data}"])
    
    if os.path.exists(tmp_xml):
        os.remove(tmp_xml)
        
    print("\033[1;32m[+] Đã ghi đè Shared Preferences và cấu hình Cookie thành công!\033[0m")
    return True

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
    print("\033[1;35m[6]\033[0m \033[1;37mĐọc Cookie từ File TXT (Tiêm V2 Fix)\033[0m")
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
            print("\033[1;35m=== ĐĂNG NHẬP COOKIE TỪ FILE TXT (FIX V2) ===\033[0m")
            filename_input = input("Nhập tên file (VD: cookie.txt): ").strip()
            
            if not filename_input:
                continue

            possible_paths = [
                f"/sdcard/Download/{filename_input}",
                f"/storage/emulated/0/Download/{filename_input}",
                f"/sdcard/{filename_input}",
                f"/storage/emulated/0/{filename_input}"
            ]
            
            file_path = ""
            for p in possible_paths:
                if os.path.exists(p):
                    file_path = p
                    break

            if not file_path:
                print(f"\033[1;31m[-] Không tìm thấy file '{filename_input}' trong Download!\033[0m")
                time.sleep(2.5)
                continue

            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    raw_cookie = f.read().strip()
                print(f"\033[1;32m[+] Đã đọc file: {file_path}\033[0m")
            except Exception as fe:
                print(f"\033[1;31m[-] Lỗi đọc file: {str(fe)}\033[0m")
                time.sleep(2)
                continue
                
            target_pkg = input("Nhập package name (Để trống dùng mặc định 'com.roblox.client'): ").strip()
            if not target_pkg:
                target_pkg = "com.roblox.client"

            print(f"\033[1;33m[*] Đang tiến hành tiêm Cookie V2 vào {target_pkg}...\033[0m")
            success = inject_cookie_v2(target_pkg, raw_cookie)
            
            if success:
                print(f"\033[1;32m[+] Ép Cookie thành công!\033[0m")
                print(f"\033[1;36m[*] Đang mở Game để đồng bộ tài khoản...\033[0m")
                time.sleep(1.5)
                open_game(target_pkg)
            else:
                print("\033[1;31m[-] Thất bại! File không chứa chuỗi Cookie hợp lệ.\033[0m")
            time.sleep(3)
            
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
                
            print("\033[1;32m[+] Đã lưu script vào tất cả thư mục Autoexec thành công!\033[0m")
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
