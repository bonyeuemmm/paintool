import os
import sys
import time
import subprocess
import json
import random
import string
import threading
from datetime import datetime

VERSION = "v1.1.4-beta"
API_URL = "https://discord-license-bot-production.up.railway.app/api/verify"
LICENSE_FILE = os.path.join(os.path.expanduser("~"), ".pain_license")

PACKAGE_PREFIX = "com.roblox"
TARGET_LINK = ""
SELECTED_GAME_NAME = "Chưa chọn"
WEBHOOK_URL = ""
SCREENSHOT_PATH = "/sdcard/pain_screenshot.png"
CUSTOM_SEND_WEBHOOK = "https://discord.com/api/webhooks/1548235071671238656/sk5oitBIvUXLeYB7phyO-dHkf7NTyuBsqBeQJq2emcyFYTk1ll0dl5-uqg-bhDiINmYV"

AUTO_REJOIN_MODE = 1
DELAY_REJOIN_MINUTES = 1
CLONE_LAUNCH_DELAY = 10
stop_start = False
START_UP_TIME = None

ROBLOX_ERROR_CODES = ["277", "260", "279", "268", "267", "273", "278", "264", "261", "524"]

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
        print(f"\033[1;37m       PAIN TOOL REJOIN VIP ({VERSION}) - XÁC THỰC       \033[0m")
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
        now = datetime.now()
        time_display_str = f"hôm nay lúc {now.strftime('%H:%M')}"
        footer_text = f"MADE BY PAIN | {time_display_str}"
        packages = get_all_packages()
        rejoin_mode_str = "Quét Kick/Văng/Mã Lỗi" if AUTO_REJOIN_MODE == 1 else f"Delay Rejoin ({DELAY_REJOIN_MINUTES}p)"
        start_time_str = START_UP_TIME.strftime('%d/%m/%Y %H:%M:%S') if START_UP_TIME else "Mới khởi chạy"
        
        description_text = (
            f"**{message}**\n\n"
            f"📊 **Thông tin hệ thống:**\n"
            f"• **Phiên bản:** {VERSION}\n"
            f"• **Thời gian khởi động:** {start_time_str}\n"
            f"• **Số Tab đang treo:** {len(packages)} tab ({PACKAGE_PREFIX})\n"
            f"• **Chế độ Game:** {SELECTED_GAME_NAME}\n"
            f"• **Cơ chế Rejoin:** {rejoin_mode_str}\n"
            f"• **Thời gian báo cáo:** {now.strftime('%d/%m/%Y lúc %H:%M:%S')}"
        )

        embed_obj = {
            "title": f"PAIN TOOL REJOIN VIP STATUS ({VERSION})",
            "description": description_text,
            "color": 65280,
            "footer": {"text": footer_text}
        }

        if with_image:
            is_root = run_cmd(["id"]).find("uid=0") != -1 or run_cmd(["su", "-c", "id"]).find("uid=0") != -1
            if is_root:
                run_cmd(["su", "-c", f"screencap -p {SCREENSHOT_PATH}"])
            else:
                run_cmd(["screencap", "-p", SCREENSHOT_PATH])

            if os.path.exists(SCREENSHOT_PATH) and os.path.getsize(SCREENSHOT_PATH) > 0:
                embed_obj["image"] = {"url": "attachment://screenshot.png"}
                payload_json = json.dumps({
                    "username": "PAIN TOOL REJOIN VIP",
                    "avatar_url": "https://i.postimg.cc/gJbhCmHL/Pain-Gamer.png",
                    "embeds": [embed_obj]
                })
                run_cmd([
                    "curl", "-s", "-X", "POST", WEBHOOK_URL,
                    "-F", f"payload_json={payload_json}",
                    "-F", f"files[0]=@{SCREENSHOT_PATH};filename=screenshot.png"
                ])
                try:
                    os.remove(SCREENSHOT_PATH)
                except Exception:
                    run_cmd(["su", "-c", f"rm -f {SCREENSHOT_PATH}"])
                return

        payload_json = json.dumps({
            "username": "PAIN TOOL REJOIN VIP",
            "avatar_url": "https://i.postimg.cc/gJbhCmHL/Pain-Gamer.png",
            "embeds": [embed_obj]
        })
        run_cmd([
            "curl", "-s", "-X", "POST", WEBHOOK_URL,
            "-H", "Content-Type: application/json",
            "-d", payload_json
        ])
    except Exception:
        pass

def handle_send_text():
    while True:
        clear_screen()
        print("\033[1;35m=== SEND TEXT TO DISCORD ===\033[0m")
        content_input = input("Nhập nội dung muốn gửi (Để trống để thoát): ").strip()
        if not content_input:
            print("\033[1;33m[-] Đã thoát về giao diện chính.\033[0m")
            time.sleep(1)
            return
            
        discord_id = input("Nhập UID tài khoản Discord (Để trống để bỏ qua): ").strip()
        now = datetime.now()
        footer_text = f"MADE BY PAIN | hôm nay lúc {now.strftime('%H:%M')}"
        
        user_tag_str = f"<@{discord_id}>" if discord_id else "Ẩn danh"
        uid_str = discord_id if discord_id else "Không có"
        
        description_text = (
            f"Bạn có nội dung gửi từ PAIN TOOL REJOIN VIP ({VERSION})\n\n"
            f"{content_input}\n\n"
            "👤 Thông tin người gửi:\n"
            f"• Tên người dùng: {user_tag_str}\n"
            f"• UID: {uid_str}\n\n"
            "🕐 Thời gian gửi:\n"
            f"{now.strftime('%d/%m/%Y lúc %H:%M:%S')}"
        )
        
        embed_data = {
            "username": "PAIN TOOL REJOIN VIP",
            "avatar_url": "https://i.postimg.cc/gJbhCmHL/Pain-Gamer.png",
            "embeds": [{"description": description_text, "footer": {"text": footer_text}, "color": 65280}]
        }
        if discord_id:
            embed_data["content"] = f"<@{discord_id}>"
        
        try:
            payload = json.dumps(embed_data)
            run_cmd(["curl", "-s", "-X", "POST", CUSTOM_SEND_WEBHOOK, "-H", "Content-Type: application/json", "-d", payload])
            print("\033[1;32m[+] Đã gửi nội dung thành công qua Webhook!\033[0m")
        except Exception as e:
            print(f"\033[1;31m[-] Lỗi gửi webhook: {e}\033[0m")
        time.sleep(2)

def get_all_packages():
    output = run_cmd(["pm", "list", "packages"])
    packages = []
    for line in output.splitlines():
        if PACKAGE_PREFIX in line:
            parts = line.split(":")
            if len(parts) > 1:
                packages.append(parts[1].strip())
    packages.sort()
    return packages if packages else [PACKAGE_PREFIX]

def open_game(pkg):
    is_root = run_cmd(["id"]).find("uid=0") != -1 or run_cmd(["su", "-c", "id"]).find("uid=0") != -1

    if TARGET_LINK:
        deep_link = f"roblox://placeId={TARGET_LINK}" if TARGET_LINK.isdigit() else TARGET_LINK
        cmd = f"am start -a android.intent.action.VIEW -d '{deep_link}' {pkg}"
    else:
        cmd = f"monkey -p {pkg} -c android.intent.category.LAUNCHER 1"

    if is_root:
        run_cmd(["su", "-c", cmd])
    else:
        run_cmd(cmd.split())

def close_game(pkg):
    run_cmd(["su", "-c", f"am force-stop {pkg}"])
    run_cmd(["am", "force-stop", pkg])

def check_package_error(pkg):
    log_output = run_cmd(["logcat", "-d", "-t", "100"])
    if not log_output:
        return False, None

    general_keywords = ['disconnect', 'kicked', 'lost connection']
    for line in log_output.splitlines():
        line_lower = line.lower()
        if pkg in line_lower or "roblox" in line_lower:
            for code in ROBLOX_ERROR_CODES:
                if f"error {code}" in line_lower or f"code: {code}" in line_lower or f"code {code}" in line_lower:
                    return True, f"Mã Lỗi {code}"
            if any(k in line_lower for k in general_keywords):
                return True, "Mất kết nối / Kicked"
    return False, None

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
    global stop_start, START_UP_TIME
    clear_screen()
    packages = get_all_packages()
    START_UP_TIME = datetime.now()
    
    print(f"\033[1;37m[+] PAIN TOOL REJOIN VIP ({VERSION}) Đang chạy...\033[0m")
    print(f"\033[1;35m[*] Đã tìm thấy {len(packages)} bản clone ({PACKAGE_PREFIX}).\033[0m")
    print(f"\033[1;33m[*] Delay mở mỗi tab clone: {CLONE_LAUNCH_DELAY} giây.\033[0m")
    print("\033[1;33m[*] Bấm phím 0 rồi nhấn Enter để ngắt Start.\033[0m")
    print("--------------------------------------------------")
    
    run_cmd(["logcat", "-c"])

    for idx, pkg in enumerate(packages):
        print(f"\033[1;36m[*] Đang khởi chạy Tab [{idx+1}/{len(packages)}]: {pkg}\033[0m")
        open_game(pkg)
        if idx < len(packages) - 1:
            print(f"\033[1;33m[*] Chờ {CLONE_LAUNCH_DELAY}s...\033[0m")
            time.sleep(CLONE_LAUNCH_DELAY)

    send_webhook(f"Bắt đầu theo dõi {len(packages)} tab clone.", with_image=True)

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
                    ps_out = run_cmd(["ps", "-A"])
                    is_running = bool(pid) or (pkg in ps_out)

                    if not is_running:
                        print(f"\033[1;31m[-] Tab {pkg} bị văng/đóng! Đang mở lại...\033[0m")
                        open_game(pkg)
                        time.sleep(15)
                    else:
                        has_error, error_msg = check_package_error(pkg)
                        if has_error:
                            print(f"\033[1;33m[-] Phát hiện {pkg} lỗi [{error_msg}]! Đang Rejoin...\033[0m")
                            close_game(pkg)
                            time.sleep(3)
                            run_cmd(["logcat", "-c"])
                            open_game(pkg)
                            time.sleep(15)

            elif AUTO_REJOIN_MODE == 2:
                if elapsed_minutes >= DELAY_REJOIN_MINUTES:
                    print(f"\033[1;33m[*] Chu kỳ {DELAY_REJOIN_MINUTES}p hoàn tất. Restart toàn bộ tab...\033[0m")
                    for pkg in packages:
                        close_game(pkg)
                    time.sleep(3)
                    
                    for idx, pkg in enumerate(packages):
                        open_game(pkg)
                        if idx < len(packages) - 1:
                            time.sleep(CLONE_LAUNCH_DELAY)
                    start_time = time.time()

            if (current_time - last_webhook_time) >= 300:
                send_webhook("Cập nhật trạng thái định kỳ (5 phút)", with_image=True)
                last_webhook_time = current_time

            for _ in range(5):
                if stop_start: break
                time.sleep(1)

        if stop_start:
            print("\n\033[1;31m[!] Đã dừng Start. Quay lại menu...\033[0m")
            time.sleep(1.5)
            return

    except KeyboardInterrupt:
        print("\n\033[1;31m[!] Đã dừng Start.\033[0m")
        time.sleep(1)
        return

def show_banner():
    clear_screen()
    rejoin_mode_str = "Quét Kick/Văng/Mã Lỗi" if AUTO_REJOIN_MODE == 1 else f"Delay Rejoin ({DELAY_REJOIN_MINUTES}p)"
    print("\033[1;35m==================================================\033[0m")
    print(f"\033[1;37m        PAIN TOOL REJOIN VIP ({VERSION})          \033[0m")
    print("\033[1;35m==================================================\033[0m")
    print(f"\033[1;35m Package Prefix  :\033[0m \033[1;37m{PACKAGE_PREFIX}\033[0m")
    print(f"\033[1;35m Chế độ Game     :\033[0m \033[1;37m{SELECTED_GAME_NAME}\033[0m")
    print(f"\033[1;35m Cơ chế Rejoin   :\033[0m \033[1;37m{rejoin_mode_str}\033[0m")
    print(f"\033[1;35m Delay Tab Clone :\033[0m \033[1;37m{CLONE_LAUNCH_DELAY} giây\033[0m")
    print(f"\033[1;35m Webhook URL     :\033[0m \033[1;37m{'Đã cấu hình' if WEBHOOK_URL else 'Chưa đặt'}\033[0m")
    print("\033[1;35m==================================================\033[0m")
    print("\033[1;35m[1]\033[0m \033[1;37mStart\033[0m")
    print("\033[1;35m[2]\033[0m \033[1;37mSet up\033[0m")
    print("\033[1;35m[3]\033[0m \033[1;37mPackage prefix\033[0m")
    print("\033[1;35m[4]\033[0m \033[1;37mChange id\033[0m")
    print("\033[1;35m[5]\033[0m \033[1;37mUrl webhook\033[0m")
    print("\033[1;35m[6]\033[0m \033[1;37mXóa cache\033[0m")
    print("\033[1;35m[7]\033[0m \033[1;37mImport auto execute\033[0m")
    print("\033[1;35m[8]\033[0m \033[1;37mMở tab clone\033[0m")
    print("\033[1;35m[9]\033[0m \033[1;37mSEND TEXT\033[0m")
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
                    print("\033[1;37m1. Auto rejoin khi bị kick/văng/mã lỗi (Thông minh)\033[0m")
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
                            SELECTED_GAME_NAME = f"Game ID: {link}" if link.isdigit() else "Server VIP Custom"
                            print("\033[1;32m[+] Đã nhận link/ID!\033[0m")
                            time.sleep(1.5)
                    time.sleep(1)
                elif sub == "3":
                    break
        elif choice == "3":
            clear_screen()
            pref = input("Nhập Package Prefix (Để trống để giữ mặc định): ").strip()
            if pref:
                PACKAGE_PREFIX = pref
        elif choice == "4":
            clear_screen()
            new_id = input("Nhập ID mới (Để trống để tạo ngẫu nhiên): ").strip()
            if not new_id:
                new_id = "".join(random.choices(string.hexdigits.lower(), k=16))
            run_cmd(["su", "-c", f"settings put secure android_id {new_id}"])
            print(f"\033[1;32m[+] Đã yêu cầu đổi ID thành: {new_id}\033[0m")
            time.sleep(2)
        elif choice == "5":
            clear_screen()
            url = input("Nhập Link Discord Webhook (Để trống để xóa): ").strip()
            WEBHOOK_URL = url
            if WEBHOOK_URL:
                print("\033[1;32m[+] Đã lưu Webhook!\033[0m")
            time.sleep(1.5)
        elif choice == "6":
            clear_screen()
            packages = get_all_packages()
            for pkg in packages:
                run_cmd(["su", "-c", f"rm -rf /data/data/{pkg}/cache/*"])
            print("\033[1;32m[+] Hoàn tất dọn dẹp cache!\033[0m")
            time.sleep(2)
        elif choice == "7":
            clear_screen()
            script_data = input("Nhập script hack (Để trống để thoát): ").strip()
            if not script_data:
                continue
            temp_path = "/sdcard/temp_autoexec.lua"
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(script_data)
            executor_names = ["Delta", "Codex", "Arceus", "ArceusX", "Fluxus", "Hydrogen", "Valyse", "VegaX", "Krampus", "Evon"]
            autoexec_subdirs = ["autoexec", "Autoexec", "auto-execute", "AutoExecute", "scripts", "Scripts"]
            target_dirs = set()
            for name in executor_names:
                base_dir = f"/sdcard/{name}"
                target_dirs.add(f"{base_dir}/Autoexec")
            packages = get_all_packages()
            for pkg in packages:
                target_dirs.add(f"/sdcard/Android/data/{pkg}/files/autoexec")
            for target in target_dirs:
                run_cmd(["mkdir", "-p", target])
                run_cmd(["cp", temp_path, f"{target}/script.lua"])
            try:
                os.remove(temp_path)
            except:
                pass
            print("\033[1;32m[+] Đã lưu script Autoexec!\033[0m")
            time.sleep(2)
        elif choice == "8":
            clear_screen()
            found_pkgs = get_all_packages()
            for idx, pkg in enumerate(found_pkgs):
                open_game(pkg)
                if idx < len(found_pkgs) - 1:
                    time.sleep(CLONE_LAUNCH_DELAY)
            print("\033[1;32m[+] Hoàn tất mở tab clone!\033[0m")
            time.sleep(2)
        elif choice == "9":
            handle_send_text()
        elif choice == "0":
            sys.exit(0)