import os
import sys
import time
import subprocess
import json
import random
import string
import threading
from datetime import datetime

VERSION = "v1.2.5"
API_URL = "https://discord-license-bot-production.up.railway.app/api/verify"
LICENSE_FILE = os.path.join(os.path.expanduser("~"), ".pain_license")
CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".pain_config.json")

PACKAGE_PREFIX = "com.roblox"
TARGET_LINK = ""
SELECTED_GAME_NAME = "Chưa chọn"
WEBHOOK_URL = ""
DISCORD_UID = ""
SEND_TEXT_WEBHOOK = "https://discord.com/api/webhooks/1548235071671238656/sk5oitBIvUXLeYB7phyO-dHkf7NTyuBsqBeQJq2emcyFYTk1ll0dl5-uqg-bhDiINmYV"
SCREENSHOT_PATH = "/sdcard/pain_screenshot.png"

DISCORD_LINK = "https://discord.gg/z7RUNArBuJ"

AUTO_REJOIN_MODE = 1
DELAY_REJOIN_MINUTES = 1
CLONE_LAUNCH_DELAY = 10
stop_start = False
START_UP_TIME = None

ROBLOX_ERROR_CODES = ["277", "260", "279", "268", "267", "273", "278", "264", "261", "524"]

def load_saved_config():
    global WEBHOOK_URL, DISCORD_UID
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                WEBHOOK_URL = data.get("webhook_url", "")
                DISCORD_UID = data.get("discord_uid", "")
        except Exception:
            pass

def save_config_file():
    try:
        data = {
            "webhook_url": WEBHOOK_URL,
            "discord_uid": DISCORD_UID
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception:
        pass

def clear_screen():
    os.system('stty sane 2>/dev/null')
    os.system('clear')

def print_ascii_banner():
    PURPLE = "\033[1;35m"
    DEEP_PURPLE = "\033[0;35m"
    WHITE = "\033[1;37m"
    RESET = "\033[0m"

    banner = f"""
{PURPLE}██████╗  █████╗ ██╗███╗   ██╗ {WHITE}██████╗ ███████╗██╗███╗   ██╗
{PURPLE}██╔══██╗██╔══██╗██║████╗  ██║ {WHITE}██╔══██╗██╔════╝██║████╗  ██║
{PURPLE}██████╔╝███████║██║██╔██╗ ██║ {WHITE}██████╔╝█████╗  ██║██╔██╗ ██║
{PURPLE}██╔═══╝ ██╔══██║██║██║╚██╗██║ {WHITE}██╔══██╗██╔══╝  ██║██║╚██╗██║
{PURPLE}██║     ██║  ██║██║██║ ╚████║ {WHITE}██║  ██║███████╗██║██║ ╚████║
{DEEP_PURPLE}╚═╝     ╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝ {DEEP_PURPLE}╚═╝  ╚═╝╚══════╝╚═╝╚═╝  ╚═╝{RESET}"""
    print(banner)

def run_cmd(cmd_list, timeout=15):
    try:
        res = subprocess.run(cmd_list, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        return res.stdout.strip()
    except Exception:
        return ""

def get_system_info():
    model = run_cmd(["getprop", "ro.product.model"]) or "Android Device"
    android_ver = run_cmd(["getprop", "ro.build.version.release"]) or "N/A"
    cpu = run_cmd(["getprop", "ro.board.platform"]) or run_cmd(["getprop", "ro.product.board"]) or "ARM64"
    
    ram_info = "N/A"
    if os.path.exists("/proc/meminfo"):
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if "MemTotal" in line:
                        total_kb = int(line.split()[1])
                        ram_info = f"{round(total_kb / 1024 / 1024, 1)} GB"
                        break
        except Exception:
            pass

    battery_info = "N/A"
    dumpsys_bat = run_cmd(["dumpsys", "battery"])
    if dumpsys_bat:
        for line in dumpsys_bat.splitlines():
            if "level:" in line:
                battery_info = f"{line.split(':')[1].strip()}%"
                break

    return {
        "model": model,
        "android": android_ver,
        "cpu": cpu,
        "ram": ram_info,
        "battery": battery_info
    }

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
        ], timeout=10)
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
                print("\033[1;32m[*] Đang kiểm tra Key đã lưu...\033[0m")
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
        print_ascii_banner()
        print("\033[1;32m==================================================\033[0m")
        print(f"\033[1;37m                 XÁC THỰC BẢN QUYỀN               \033[0m")
        print("\033[1;32m==================================================\033[0m")
        print(f"\033[1;36m HWID hiện tại: {hwid}\033[0m")
        input_key = input("Nhập Key (0 để thoát): ").strip()
        if input_key in ["exit", "0"]:
            sys.exit(0)
        if not input_key:
            continue
        print("\033[1;32m[*] Đang kết nối máy chủ...\033[0m")
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
        footer_text = "MADE BY PAIN"
        packages = get_all_packages()
        rejoin_mode_str = "Auto rejoin vang/kicked" if AUTO_REJOIN_MODE == 1 else f"Delay Rejoin ({DELAY_REJOIN_MINUTES}p)"
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

        payload_dict = {
            "username": "PAIN TOOL REJOIN VIP",
            "avatar_url": "https://i.postimg.cc/gJbhCmHL/Pain-Gamer.png",
            "embeds": [embed_obj]
        }
        if DISCORD_UID:
            payload_dict["content"] = f"<@{DISCORD_UID}>"

        if with_image:
            is_root = run_cmd(["id"]).find("uid=0") != -1 or run_cmd(["su", "-c", "id"]).find("uid=0") != -1
            if is_root:
                run_cmd(["su", "-c", f"screencap -p {SCREENSHOT_PATH}"])
            else:
                run_cmd(["screencap", "-p", SCREENSHOT_PATH])

            if os.path.exists(SCREENSHOT_PATH) and os.path.getsize(SCREENSHOT_PATH) > 0:
                embed_obj["image"] = {"url": "attachment://screenshot.png"}
                payload_json = json.dumps(payload_dict)
                run_cmd([
                    "curl", "-s", "-X", "POST", WEBHOOK_URL,
                    "-F", f"payload_json={payload_json}",
                    "-F", f"files[0]=@{SCREENSHOT_PATH};filename=screenshot.png"
                ], timeout=20)
                try:
                    os.remove(SCREENSHOT_PATH)
                except Exception:
                    run_cmd(["su", "-c", f"rm -f {SCREENSHOT_PATH}"])
                return

        payload_json = json.dumps(payload_dict)
        run_cmd([
            "curl", "-s", "-X", "POST", WEBHOOK_URL,
            "-H", "Content-Type: application/json",
            "-d", payload_json
        ], timeout=15)
    except Exception:
        pass

def send_detailed_alert(message):
    if not WEBHOOK_URL:
        return
    try:
        now = datetime.now()
        ping_str = f"<@{DISCORD_UID}>" if DISCORD_UID else ""
        description_text = (
            f"⚠️ **CẢNH BÁO CHI TIẾT HỆ THỐNG** ⚠️\n\n"
            f"{message}\n\n"
            f"🕐 **Thời gian:** {now.strftime('%d/%m/%Y lúc %H:%M:%S')}"
        )
        embed_obj = {
            "title": f"PAIN TOOL ALERT ({VERSION})",
            "description": description_text,
            "color": 16711680,
            "footer": {"text": "MADE BY PAIN"}
        }
        payload_dict = {
            "username": "PAIN TOOL REJOIN VIP",
            "avatar_url": "https://i.postimg.cc/gJbhCmHL/Pain-Gamer.png",
            "embeds": [embed_obj]
        }
        if ping_str:
            payload_dict["content"] = ping_str

        payload_json = json.dumps(payload_dict)
        run_cmd([
            "curl", "-s", "-X", "POST", WEBHOOK_URL,
            "-H", "Content-Type: application/json",
            "-d", payload_json
        ], timeout=10)
    except Exception:
        pass

def handle_send_text():
    while True:
        clear_screen()
        print("\033[1;32m=== SEND TEXT TO DISCORD ===\033[0m")
        content_input = input("Nhập nội dung muốn gửi (Để trống để thoát): ").strip()
        if not content_input:
            print("\033[1;33m[-] Đã thoát về giao diện chính.\033[0m")
            time.sleep(1)
            return
            
        discord_id = input("Nhập UID tài khoản Discord (Để trống để bỏ qua): ").strip()
        now = datetime.now()
        footer_text = "MADE BY PAIN"
        
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
            run_cmd(["curl", "-s", "-X", "POST", SEND_TEXT_WEBHOOK, "-H", "Content-Type: application/json", "-d", payload])
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

def is_in_target_map(pkg):
    if not TARGET_LINK or not TARGET_LINK.isdigit():
        return True
    
    is_root = run_cmd(["id"]).find("uid=0") != -1 or run_cmd(["su", "-c", "id"]).find("uid=0") != -1
    
    if is_root:
        log_output = run_cmd(["su", "-c", "logcat -d -t 100"], timeout=3)
    else:
        log_output = run_cmd(["logcat", "-d", "-t", "100"], timeout=3)
        
    if not log_output:
        return False
        
    for line in log_output.splitlines():
        line_lower = line.lower()
        if pkg in line_lower or "roblox" in line_lower:
            if f"placeid={TARGET_LINK}" in line_lower or f"placeid:{TARGET_LINK}" in line_lower or f"place {TARGET_LINK}" in line_lower:
                return True
    return False

def open_game_until_success(pkg):
    print(f"\033[1;33m[*] Đang mở game cho {pkg}...\033[0m")
    open_game(pkg)
    
    print(f"\033[1;33m[*] Đang chờ 10 giây để game khởi chạy...\033[0m")
    if wait_with_stop_check(10):
        return

    while not stop_start:
        pid = run_cmd(["pidof", pkg], timeout=3)
        ps_out = run_cmd(["ps", "-A"], timeout=3)
        is_running = bool(pid) or (pkg in ps_out)
        
        if not is_running:
            open_game(pkg)
        
        if is_running and is_in_target_map(pkg):
            print(f"\033[1;32m[+] Vào map thành công cho {pkg}!\033[0m")
            break
            
        print(f"\033[1;36m[*] Đang quét trạng thái map {pkg}... (Thử lại sau 5s)\033[0m")
        if wait_with_stop_check(5):
            break

def close_game(pkg):
    is_root = run_cmd(["id"]).find("uid=0") != -1 or run_cmd(["su", "-c", "id"]).find("uid=0") != -1
    cmd_kill = f"am kill {pkg}"
    cmd_force = f"am force-stop {pkg}"
    
    if is_root:
        run_cmd(["su", "-c", cmd_kill])
        run_cmd(["su", "-c", cmd_force])
    else:
        run_cmd(cmd_kill.split())
        run_cmd(cmd_force.split())

def check_package_error_since(pkg, since_time_str):
    is_root = run_cmd(["id"]).find("uid=0") != -1 or run_cmd(["su", "-c", "id"]).find("uid=0") != -1
    
    cmd = ["logcat", "-d", "-t", since_time_str]
    if is_root:
        log_output = run_cmd(["su", "-c", f"logcat -d -t '{since_time_str}'"], timeout=4)
    else:
        log_output = run_cmd(cmd, timeout=4)

    if not log_output:
        return False, None

    kick_keywords = ['you have been kicked', 'disconnected from game', 'unexpected disconnection', 'same account launched']
    
    for line in log_output.splitlines():
        line_lower = line.lower()
        if pkg in line_lower or "roblox" in line_lower:
            for code in ROBLOX_ERROR_CODES:
                if f"error code: {code}" in line_lower or f"error {code}" in line_lower or f"code: {code}" in line_lower:
                    return True, f"Mã Lỗi {code}"
            if any(k in line_lower for k in kick_keywords):
                return True, "Bị Kick / Mất kết nối"
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

def wait_with_stop_check(seconds, message=""):
    if message:
        print(message)
    for _ in range(seconds):
        if stop_start:
            return True
        time.sleep(1)
    return False

def start_tool():
    global stop_start, START_UP_TIME
    clear_screen()
    print_ascii_banner()
    packages = get_all_packages()
    START_UP_TIME = datetime.now()
    
    last_launch_timestamp = {}
    
    print(f"\033[1;37m[+] PAIN TOOL REJOIN VIP ({VERSION}) Đang chạy...\033[0m")
    print(f"\033[1;32m[*] Đã tìm thấy {len(packages)} bản clone ({PACKAGE_PREFIX}).\033[0m")
    if len(packages) >= 4:
        print(f"\033[1;33m[*] Số lượng tab >= 4, áp dụng mở nhóm 3 tab, cách nhau 15 giây.\033[0m")
    else:
        print(f"\033[1;33m[*] Delay mở mỗi tab clone: {CLONE_LAUNCH_DELAY} giây.\033[0m")
    print("\033[1;33m[*] Bấm phím 0 rồi nhấn Enter để ngắt Start.\033[0m")
    print("--------------------------------------------------")

    if len(packages) >= 4:
        batch_size = 3
        total_clones = len(packages)
        for i in range(0, total_clones, batch_size):
            if stop_start: break
            batch = packages[i:i + batch_size]
            for idx_b, pkg in enumerate(batch):
                if stop_start: break
                global_idx = i + idx_b + 1
                print(f"\033[1;36m[*] Đang khởi chạy Tab [{global_idx}/{total_clones}]: {pkg}\033[0m")
                open_game_until_success(pkg)
                last_launch_timestamp[pkg] = datetime.now().strftime("%m-%d %H:%M:%S.000")
            if i + batch_size < total_clones and not stop_start:
                print(f"\033[1;33m[*] Chờ 15 giây để mở nhóm tiếp theo...\033[0m")
                if wait_with_stop_check(15): break
    else:
        for idx, pkg in enumerate(packages):
            if stop_start: break
            print(f"\033[1;36m[*] Đang khởi chạy Tab [{idx+1}/{len(packages)}]: {pkg}\033[0m")
            open_game_until_success(pkg)
            last_launch_timestamp[pkg] = datetime.now().strftime("%m-%d %H:%M:%S.000")
            if idx < len(packages) - 1:
                print(f"\033[1;33m[*] Chờ {CLONE_LAUNCH_DELAY}s...\033[0m")
                if wait_with_stop_check(CLONE_LAUNCH_DELAY): break

    if not stop_start:
        send_webhook(f"Bắt đầu theo dõi {len(packages)} tab clone.", with_image=True)

    start_time = time.time()
    last_webhook_time = time.time()
    last_cleanup_time = time.time()
    
    stop_start = False
    listener = threading.Thread(target=listen_for_stop, daemon=True)
    listener.start()

    try:
        while not stop_start:
            current_time = time.time()
            elapsed_minutes = (current_time - start_time) / 60.0
            packages = get_all_packages()

            if (current_time - last_cleanup_time) >= 600:
                print("\033[1;32m[*] Tiến hành tự động dọn dẹp RAM và cache định kỳ...\033[0m")
                for pkg in packages:
                    run_cmd(["su", "-c", f"rm -rf /data/data/{pkg}/cache/*"])
                run_cmd(["su", "-c", "sync && echo 3 > /proc/sys/vm/drop_caches"])
                last_cleanup_time = time.time()

            if AUTO_REJOIN_MODE == 1:
                for pkg in packages:
                    if stop_start: break
                    
                    pid = run_cmd(["pidof", pkg], timeout=3)
                    ps_out = run_cmd(["ps", "-A"], timeout=5)
                    is_running = bool(pid) or (pkg in ps_out)

                    if not is_running:
                        print(f"\033[1;31m[-] Tab {pkg} bị văng/đóng! Chờ 5s trước khi Rejoin (Gõ 0 để hủy)...\033[0m")
                        if wait_with_stop_check(5): break
                        
                        send_detailed_alert(f"Tab {pkg} bị văng/đóng hoàn toàn! Tool đang tiến hành tự động mở lại.")
                        close_game(pkg)
                        time.sleep(1)
                        open_game_until_success(pkg)
                        last_launch_timestamp[pkg] = datetime.now().strftime("%m-%d %H:%M:%S.000")
                        print(f"\033[1;32m[+] Đã mở lại {pkg}. Chờ 15s để ổn định...\033[0m")
                        if wait_with_stop_check(15): break
                    else:
                        since_time = last_launch_timestamp.get(pkg, datetime.now().strftime("%m-%d %H:%M:%S.000"))
                        has_error, error_msg = check_package_error_since(pkg, since_time)
                        in_map = is_in_target_map(pkg)
                        
                        if has_error or not in_map:
                            reason_str = error_msg if has_error else "Không ở trong Map Game đã chọn"
                            print(f"\033[1;33m[-] Phát hiện {pkg} [{reason_str}]! Chờ 5s trước khi Rejoin (Gõ 0 để hủy)...\033[0m")
                            if wait_with_stop_check(5): break
                            
                            send_detailed_alert(f"Phát hiện lỗi trên {pkg}: [{reason_str}]. Tool đang thực hiện Rejoin.")
                            close_game(pkg)
                            time.sleep(2)
                            open_game_until_success(pkg)
                            last_launch_timestamp[pkg] = datetime.now().strftime("%m-%d %H:%M:%S.000")
                            print(f"\033[1;32m[+] Đã Rejoin {pkg}. Chờ 15s để ổn định...\033[0m")
                            if wait_with_stop_check(15): break

            elif AUTO_REJOIN_MODE == 2:
                if elapsed_minutes >= DELAY_REJOIN_MINUTES:
                    print(f"\033[1;33m[*] Chu kỳ {DELAY_REJOIN_MINUTES}p hoàn tất. Restart toàn bộ tab...\033[0m")
                    for pkg in packages:
                        close_game(pkg)
                    time.sleep(3)
                    
                    if len(packages) >= 4:
                        batch_size = 3
                        total_clones = len(packages)
                        for i in range(0, total_clones, batch_size):
                            if stop_start: break
                            batch = packages[i:i + batch_size]
                            for idx_b, pkg in enumerate(batch):
                                if stop_start: break
                                open_game_until_success(pkg)
                                last_launch_timestamp[pkg] = datetime.now().strftime("%m-%d %H:%M:%S.000")
                            if i + batch_size < total_clones and not stop_start:
                                if wait_with_stop_check(15): break
                    else:
                        for idx, pkg in enumerate(packages):
                            if stop_start: break
                            open_game_until_success(pkg)
                            last_launch_timestamp[pkg] = datetime.now().strftime("%m-%d %H:%M:%S.000")
                            if idx < len(packages) - 1:
                                if wait_with_stop_check(CLONE_LAUNCH_DELAY): break
                    start_time = time.time()

            if (time.time() - last_webhook_time) >= 300:
                print("\033[1;32m[*] Đã đủ 5 phút, đang gửi báo cáo định kỳ...\033[0m")
                send_webhook("Cập nhật trạng thái định kỳ (5 phút)", with_image=True)
                last_webhook_time = time.time()

            if wait_with_stop_check(3): break

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
    print_ascii_banner()
    
    sys_info = get_system_info()
    rejoin_mode_str = "Auto rejoin vang/kicked" if AUTO_REJOIN_MODE == 1 else f"Delay Rejoin ({DELAY_REJOIN_MINUTES}p)"
    
    print("\033[1;32m--------------------------------------------------\033[0m")
    print("\033[1;37m             PAIN TOOL REJOIN VIP                \033[0m")
    print("\033[1;32m--------------------------------------------------\033[0m")
    print(" \033[1;33mMADE BY       :\033[0m \033[1;37mPAIN GAMER\033[0m")
    print(f" \033[1;33mDISCORD       :\033[0m \033[1;36m{DISCORD_LINK}\033[0m")
    print(f" \033[1;33mVERSION       :\033[0m \033[1;32m{VERSION}\033[0m")
    print("\033[1;32m--------------------------------------------------\033[0m")
    print(" \033[1;32m[ THÔNG TIN THIẾT BỊ ]\033[0m")
    print(f" \033[1;37m• Thiết bị    :\033[0m {sys_info['model']} (Android {sys_info['android']})")
    print(f" \033[1;37m• Chip / CPU  :\033[0m {sys_info['cpu']}")
    print(f" \033[1;37m• Tổng RAM    :\033[0m {sys_info['ram']}")
    print(f" \033[1;37m• Dung lượng  :\033[0m {sys_info['battery']}")
    print("\033[1;32m--------------------------------------------------\033[0m")
    print(f"\033[1;32m Package Prefix  :\033[0m \033[1;37m{PACKAGE_PREFIX}\033[0m")
    print(f"\033[1;32m Chế độ Game     :\033[0m \033[1;37m{SELECTED_GAME_NAME}\033[0m")
    print(f"\033[1;32m Cơ chế Rejoin   :\033[0m \033[1;37m{rejoin_mode_str}\033[0m")
    print(f"\033[1;32m Webhook URL     :\033[0m \033[1;37m{'Đã cài đặt' if WEBHOOK_URL else 'Chưa cài'}\033[0m")
    print("\033[1;32m==================================================\033[0m")
    print("\033[1;32m[1]\033[0m \033[1;37mStart\033[0m")
    print("\033[1;32m[2]\033[0m \033[1;37mSet up\033[0m")
    print("\033[1;32m[3]\033[0m \033[1;37mPackage prefix\033[0m")
    print("\033[1;32m[4]\033[0m \033[1;37mChange id\033[0m")
    print("\033[1;32m[5]\033[0m \033[1;37mSet Webhook URL\033[0m")
    print("\033[1;32m[6]\033[0m \033[1;37mXóa cache\033[0m")
    print("\033[1;32m[7]\033[0m \033[1;37mImport auto execute\033[0m")
    print("\033[1;32m[8]\033[0m \033[1;37mMở tab clone\033[0m")
    print("\033[1;32m[9]\033[0m \033[1;37mSEND TEXT\033[0m")
    print("\033[1;31m[0] Exit\033[0m")
    print("\033[1;32m==================================================\033[0m")

if __name__ == "__main__":
    load_saved_config()
    authenticate()
    while True:
        show_banner()
        choice = input("Chọn chức năng [0-9]: ").strip()
        if choice == "1":
            start_tool()
        elif choice == "2":
            while True:
                clear_screen()
                print("\033[1;32m=== SET UP ===\033[0m")
                print("\033[1;37m1. Set up auto rejoin\033[0m")
                print("\033[1;37m2. Chọn game\033[0m")
                print("\033[1;32m0. Quay lại menu chính\033[0m")
                sub = input("Chọn: ").strip()
                if sub == "1":
                    clear_screen()
                    print("\033[1;32m=== SET UP AUTO REJOIN ===\033[0m")
                    print("\033[1;37m1. Auto rejoin vang/kicked\033[0m")
                    print("\033[1;37m2. Delay rejoin (Đóng & mở lại theo chu kỳ)\033[0m")
                    mode = input("Chọn cơ chế [1/2]: ").strip()
                    if mode == "1":
                        AUTO_REJOIN_MODE = 1
                        print("\033[1;32m[+] Đã chọn Auto rejoin vang/kicked!\033[0m")
                    elif mode == "2":
                        AUTO_REJOIN_MODE = 2
                        mins = input("Nhập thời gian chu kỳ (phút): ").strip()
                        if mins.isdigit() and int(mins) > 0:
                            DELAY_REJOIN_MINUTES = int(mins)
                            print(f"\033[1;32m[+] Đã cài Delay Rejoin {DELAY_REJOIN_MINUTES} phút!\033[0m")
                    time.sleep(1.5)
                elif sub == "2":
                    clear_screen()
                    print("\033[1;32m=== CHỌN GAME ===\033[0m")
                    print("\033[1;37m1. Blox Fruit\033[0m")
                    print("\033[1;37m2. Grow a Garden\033[0m")
                    print("\033[1;37m3. Grow a Garden 2\033[0m")
                    print("\033[1;37m4. Blade Ball\033[0m")
                    print("\033[1;37m5. King Legacy\033[0m")
                    print("\033[1;37m6. Fisch\033[0m")
                    print("\033[1;37m7. Pet Simulator 99\033[0m")
                    print("\033[1;37m8. Anime Vanguards\033[0m")
                    print("\033[1;37m9. 99 Nights in the Forest\033[0m")
                    print("\033[1;37m10. Steal a Brainrot\033[0m")
                    print("\033[1;37m11. Steal An Egg\033[0m")
                    print("\033[1;37m12. Custom ID / Private Link\033[0m")
                    game_choice = input("Chọn game [1-12]: ").strip()
                    if game_choice == "1":
                        TARGET_LINK = "2753915549"
                        SELECTED_GAME_NAME = "Blox Fruit"
                    elif game_choice == "2":
                        TARGET_LINK = "126884695634066"
                        SELECTED_GAME_NAME = "Grow a Garden"
                    elif game_choice == "3":
                        TARGET_LINK = "97598239454123"
                        SELECTED_GAME_NAME = "Grow a Garden 2"
                    elif game_choice == "4":
                        TARGET_LINK = "13772394625"
                        SELECTED_GAME_NAME = "Blade Ball"
                    elif game_choice == "5":
                        TARGET_LINK = "4520749081"
                        SELECTED_GAME_NAME = "King Legacy"
                    elif game_choice == "6":
                        TARGET_LINK = "16732694052"
                        SELECTED_GAME_NAME = "Fisch"
                    elif game_choice == "7":
                        TARGET_LINK = "8737899170"
                        SELECTED_GAME_NAME = "Pet Simulator 99"
                    elif game_choice == "8":
                        TARGET_LINK = "16146832113"
                        SELECTED_GAME_NAME = "Anime Vanguards"
                    elif game_choice == "9":
                        TARGET_LINK = "79546208627805"
                        SELECTED_GAME_NAME = "99 Nights in the Forest"
                    elif game_choice == "10":
                        TARGET_LINK = "109983668079237"
                        SELECTED_GAME_NAME = "Steal a Brainrot"
                    elif game_choice == "11":
                        TARGET_LINK = "107778070777162"
                        SELECTED_GAME_NAME = "Steal An Egg"
                    elif game_choice == "12":
                        link = input("Nhập ID game hoặc Link Server VIP: ").strip()
                        if link:
                            TARGET_LINK = link
                            SELECTED_GAME_NAME = f"Game ID: {link}" if link.isdigit() else "Server VIP Custom"
                            print("\033[1;32m[+] Đã nhận link/ID!\033[0m")
                            time.sleep(1.5)
                    time.sleep(1)
                elif sub == "0":
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
            print("\033[1;32m=== SET WEBHOOK URL ===\033[0m")
            if WEBHOOK_URL:
                print(f"Webhook hiện tại: {WEBHOOK_URL[:35]}...")
            new_webhook = input("Nhập URL Discord Webhook (Để trống để xóa Webhook): ").strip()
            WEBHOOK_URL = new_webhook
            if WEBHOOK_URL:
                while True:
                    uid_input = input("Nhập Discord UID để nhận ping thông báo: ").strip()
                    if uid_input:
                        DISCORD_UID = uid_input
                        break
                    else:
                        print("\033[1;31m[!] Bắt buộc phải nhập Discord UID để tiếp tục!\033[0m")
                save_config_file()
                print("\033[1;32m[+] Đã cập nhật Webhook và Discord UID thành công!\033[0m")
            else:
                DISCORD_UID = ""
                save_config_file()
                print("\033[1;33m[-] Đã xóa Webhook.\033[0m")
            time.sleep(2)
        elif choice == "6":
            clear_screen()
            packages = get_all_packages()
            for pkg in packages:
                run_cmd(["su", "-c", f"rm -rf /data/data/{pkg}/cache/*"])
                run_cmd(["su", "-c", f"pm clear {pkg}"])
            run_cmd(["su", "-c", "sync && echo 3 > /proc/sys/vm/drop_caches"])
            print("\033[1;32m[+] Hoàn tất dọn dẹp cache và RAM định kỳ!\033[0m")
            time.sleep(2)
        elif choice == "7":
            clear_screen()
            script_data = input("Nhập script hack (Để trống để thoát): ").strip()
            if not script_data:
                continue
            temp_path = "/sdcard/temp_autoexec.lua"
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(script_data)
            executor_names = ["Delta", "Codex", "ArceusX", "Fluxus", "Hydrogen", "Valyse", "VegaX", "Krampus", "Evon"]
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
            print(f"\033[1;32m[*] Đang mở hàng loạt tab...\033[0m")
            if len(found_pkgs) >= 4:
                batch_size = 3
                total_clones = len(found_pkgs)
                for i in range(0, total_clones, batch_size):
                    batch = found_pkgs[i:i + batch_size]
                    for idx_b, pkg in enumerate(batch):
                        global_idx = i + idx_b + 1
                        is_root = run_cmd(["id"]).find("uid=0") != -1 or run_cmd(["su", "-c", "id"]).find("uid=0") != -1
                        cmd = f"monkey -p {pkg} -c android.intent.category.LAUNCHER 1"
                        if is_root:
                            run_cmd(["su", "-c", cmd])
                        else:
                            run_cmd(cmd.split())
                        print(f"\033[1;32m[+] Đã mở package [{global_idx}/{total_clones}]: {pkg}\033[0m")
                    if i + batch_size < total_clones:
                        print(f"\033[1;33m[*] Chờ 15 giây để mở nhóm tiếp theo...\033[0m")
                        time.sleep(15)
            else:
                for idx, pkg in enumerate(found_pkgs):
                    is_root = run_cmd(["id"]).find("uid=0") != -1 or run_cmd(["su", "-c", "id"]).find("uid=0") != -1
                    cmd = f"monkey -p {pkg} -c android.intent.category.LAUNCHER 1"
                    if is_root:
                        run_cmd(["su", "-c", cmd])
                    else:
                        run_cmd(cmd.split())
                    print(f"\033[1;32m[+] Đã mở package: {pkg}\033[0m")
                    if idx < len(found_pkgs) - 1:
                        time.sleep(CLONE_LAUNCH_DELAY)
            print("\033[1;32m[+] Hoàn tất mở các tab clone!\033[0m")
            time.sleep(2)
        elif choice == "9":
            handle_send_text()
        elif choice == "0":
            sys.exit(0)