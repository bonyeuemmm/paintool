import os
import sys
import time
import subprocess
import json
import random
import string
import threading
import hmac
import hashlib
import re
import shlex
from datetime import datetime

VERSION = "v1.3.1 Beta"
API_URL = "https://paintool-bot.onrender.com/api/verify"
SECRET_KEY = "PainGamerSecretKey2026#VipTool"
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

# Mã lỗi Roblox khiến tab bị văng/kick/không vào được game -> tự tắt tab và vào lại.
# 258-290: nhóm mã mất kết nối/kick (277, 279, 264, 268, 273, 278...), thêm 5xx/6xx/7xx là lỗi join/teleport.
ROBLOX_ERROR_CODES = [str(c) for c in range(258, 291)] + ["517", "522", "523", "524", "529", "610", "769", "770", "771", "772", "773"]

# Cụm từ (viết thường) báo bị kick / mất kết nối / crash trong log
KICK_PHRASES = [
    "you have been kicked", "you were kicked", "kicked from the game", "kicked from this experience",
    "disconnected from game", "unexpected disconnection", "same account launched",
    "lost connection to the game server", "connection attempt failed", "failed to connect to the game",
    "you have been disconnected",
]
CRASH_PHRASES = ["fatal exception", "fatal signal"]

LAUNCH_VERIFY_SECONDS = 30   # chờ tối đa bao lâu để app lên tiến trình sau khi gửi lệnh mở
LAUNCH_MAX_RETRY = 3         # số lần thử mở lại nếu app không lên
MAP_LOAD_WAIT = 15           # chờ map load xong (giây) sau khi app đã bật
LOG_STATE = {}               # pkg -> (file log, số byte đã đọc), chỉ đọc phần log mới

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
{DEEP_PURPLE}╚═╝     ╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝ {DEEP_PURPLE}╚═╝  ╚═╝╚══════╝╚═╝╚═╝  ╚═══╝{RESET}"""
    print(banner)

def run_cmd(cmd_list, timeout=15, merge_stderr=False):
    try:
        res = subprocess.run(cmd_list, capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=timeout, stdin=subprocess.DEVNULL)
        out = res.stdout + ("\n" + res.stderr if merge_stderr else "")
        return out.strip()
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
    try:
        board = run_cmd(["getprop", "ro.product.board"]) or "unknown_board"
        brand = run_cmd(["getprop", "ro.product.brand"]) or "unknown_brand"
        model = run_cmd(["getprop", "ro.product.model"]) or "unknown_model"
        arch = run_cmd(["getprop", "ro.product.cpu.abi"]) or "unknown_arch"
        serial = run_cmd(["getprop", "ro.serialno"]) or "unknown_serial"

        raw_data = f"{board}|{brand}|{model}|{arch}|{serial}"
        return hashlib.sha256(raw_data.encode()).hexdigest()
    except Exception:
        return hashlib.sha256("default_fallback_hwid".encode()).hexdigest()

def check_license_curl(key, hwid):
    try:
        timestamp = int(time.time())
        raw_data = f"{key}:{hwid}:{timestamp}"
        signature = hmac.new(
            SECRET_KEY.encode('utf-8'),
            raw_data.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        payload = json.dumps({
            "key": key,
            "hwid": hwid,
            "timestamp": timestamp,
            "signature": signature
        })

        res_text = run_cmd([
            "curl", "-s", "-X", "POST", API_URL,
            "-H", "Content-Type: application/json",
            "-d", payload,
            "--connect-timeout", "60"
        ], timeout=60)

        if not res_text:
            return False, "Không kết nối được server"

        try:
            data = json.loads(res_text)
            if isinstance(data, dict):
                return data.get("valid") is True or data.get("status") == "success", data.get("reason", res_text)
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

# ==================== ROOT / SHELL ====================
_ROOT_MODE = "unknown"

def root_mode():
    """'direct' = đang chạy sẵn uid=0, 'su' = gọi được su, None = không root (kết quả được nhớ lại)."""
    global _ROOT_MODE
    if _ROOT_MODE == "unknown":
        if "uid=0" in run_cmd(["id"]):
            _ROOT_MODE = "direct"
        elif "uid=0" in run_cmd(["su", "-c", "id"]):
            _ROOT_MODE = "su"
        else:
            _ROOT_MODE = None
    return _ROOT_MODE

def sh(cmd, timeout=15):
    """Chạy 1 lệnh shell dạng chuỗi (có pipe được). Có root thì chạy qua su."""
    if root_mode() == "su":
        return run_cmd(["su", "-c", cmd], timeout=timeout)
    return run_cmd(["sh", "-c", cmd], timeout=timeout)

def sh_args(args, timeout=15, merge_stderr=False):
    """Chạy 1 lệnh dạng list (tự quote đúng khi qua su, không bị lỗi dấu nháy/ký tự & trong link)."""
    if root_mode() == "su":
        quoted = " ".join(shlex.quote(a) for a in args)
        return run_cmd(["su", "-c", quoted], timeout=timeout, merge_stderr=merge_stderr)
    return run_cmd(args, timeout=timeout, merge_stderr=merge_stderr)

# ==================== MỞ / ĐÓNG GAME ====================
def is_app_running(pkg):
    if sh(f"pidof {pkg}", timeout=3):
        return True
    return pkg in sh("ps -A", timeout=3)

def is_app_in_foreground(pkg):
    dumpsys = sh("dumpsys window displays", timeout=3)
    if not dumpsys:
        dumpsys = sh("dumpsys activity activities", timeout=3)
    return pkg in dumpsys and "mCurrentFocus" in dumpsys

def close_game(pkg):
    """Tắt hẳn tab: force-stop + kill, nếu tiến trình còn sống thì kill -9."""
    sh(f"am force-stop {pkg}")
    sh(f"am kill {pkg}")
    time.sleep(0.5)
    for _ in range(3):
        if not is_app_running(pkg):
            break
        sh(f"kill -9 $(pidof {pkg})", timeout=5)
        time.sleep(0.5)

def build_deep_link():
    if not TARGET_LINK:
        return None
    if TARGET_LINK.startswith("roblox://") or TARGET_LINK.startswith("http"):
        return TARGET_LINK
    return f"roblox://placeId={TARGET_LINK}"

def launch_commands(pkg):
    """Các cách mở game, ưu tiên cách đầu; lỗi thì dùng cách dự phòng.
    --activity-clear-task: xóa task cũ của app, tab mới thay thế hẳn tab cũ trong Đa nhiệm."""
    deep_link = build_deep_link()
    if deep_link:
        base = ["am", "start", "-a", "android.intent.action.VIEW", "-d", deep_link]
        return [base + ["--activity-clear-task", pkg], base + [pkg]]
    main = ["am", "start", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER"]
    return [main + ["--activity-clear-task", pkg],
            ["monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1"]]

def open_game(pkg, close_first=True):
    if close_first:
        close_game(pkg)
        time.sleep(1)
    snapshot_log_baseline(pkg)  # log cũ trước thời điểm này sẽ bị bỏ qua
    for cmd in launch_commands(pkg):
        out = sh_args(cmd, merge_stderr=True).lower()
        if not any(w in out for w in ("error", "exception", "unable to resolve", "unknown option")):
            return True
    return False

def open_game_until_success(pkg, close_first=True):
    """Mở game + vào map. Không thấy app lên tiến trình thì thử lại tối đa LAUNCH_MAX_RETRY lần."""
    for attempt in range(1, LAUNCH_MAX_RETRY + 1):
        if stop_start:
            return False
        print(f"\033[1;33m[*] Mở {pkg} và tải Map (lần {attempt}/{LAUNCH_MAX_RETRY})...\033[0m")
        open_game(pkg, close_first=(close_first or attempt > 1))

        started = False
        for _ in range(max(1, LAUNCH_VERIFY_SECONDS // 2)):
            if wait_with_stop_check(2):
                return False
            if is_app_running(pkg):
                started = True
                break

        if started:
            print(f"\033[1;33m[*] {pkg} đã bật. Chờ {MAP_LOAD_WAIT}s để Map ổn định...\033[0m")
            wait_with_stop_check(MAP_LOAD_WAIT)
            return True
        print(f"\033[1;31m[!] {pkg} chưa lên sau {LAUNCH_VERIFY_SECONDS}s, thử mở lại...\033[0m")

    print(f"\033[1;31m[!] Không mở được {pkg} sau {LAUNCH_MAX_RETRY} lần.\033[0m")
    return False

# ==================== PHÁT HIỆN KICK / VĂNG / CRASH ====================
_CODE_REGEXES = [
    re.compile(r"error\s*code[:\s=]*\(?(\d{3})\b"),
    re.compile(r"disconnection\s*notification[^0-9\n]{0,40}(\d{3})\b"),
    re.compile(r"sending\s*disconnect\s*with\s*reason[:\s]*(\d{3})\b"),
    re.compile(r"\bcode[:\s=]+(\d{3})\b"),
]

def scan_text_for_problem(text, check_crash=False):
    """Trả về (True, lý do) nếu text có mã lỗi / cụm từ kick, mất kết nối (và crash nếu check_crash)."""
    if not text:
        return False, None
    low = text.lower()
    for rx in _CODE_REGEXES:
        for m in rx.finditer(low):
            if m.group(1) in ROBLOX_ERROR_CODES:
                return True, f"Mã Lỗi {m.group(1)}"
    for phrase in KICK_PHRASES:
        if phrase in low:
            return True, "Bị Kick / Mất kết nối"
    if check_crash:
        for phrase in CRASH_PHRASES:
            if phrase in low:
                return True, "Game bị Crash"
    return False, None

def log_dirs(pkg):
    return [
        f"/data/data/{pkg}/files/logs",
        f"/data/data/{pkg}/files/appData/logs",
        f"/sdcard/Android/data/{pkg}/files/logs",
    ]

def get_latest_log_file(pkg):
    if not root_mode():
        return None
    globs = " ".join(f"{d}/*.log {d}/*.txt" for d in log_dirs(pkg))
    out = sh(f"ls -t {globs} 2>/dev/null | head -n 1", timeout=5)
    first = out.splitlines()[0].strip() if out else ""
    return first if first.startswith("/") else None

def get_file_size(path):
    out = sh(f"stat -c %s '{path}' 2>/dev/null || wc -c < '{path}'", timeout=5)
    try:
        return int(out.split()[0])
    except Exception:
        return 0

def snapshot_log_baseline(pkg):
    """Ghi nhớ vị trí cuối log hiện tại: từ giờ chỉ đọc phần log MỚI, log cũ không bị bắt lại."""
    path = get_latest_log_file(pkg)
    LOG_STATE[pkg] = (path, get_file_size(path) if path else 0)

def read_new_log_text(pkg):
    path = get_latest_log_file(pkg)
    if not path:
        return ""
    if pkg not in LOG_STATE:
        LOG_STATE[pkg] = (path, get_file_size(path))
        return ""
    old_path, offset = LOG_STATE[pkg]
    size = get_file_size(path)
    if path != old_path or size < offset:
        offset = 0  # game mở lại → file log mới
    LOG_STATE[pkg] = (path, size)
    if size <= offset:
        return ""
    return sh(f"tail -c +{offset + 1} '{path}'", timeout=8)

def check_logcat_problem(pkg):
    """Đọc logcat theo PID của đúng tab này (không lẫn lỗi của các clone khác)."""
    pids = sh(f"pidof {pkg}", timeout=3).split()
    if not pids:
        return False, None
    out = sh(f"logcat -d --pid={pids[0]} -t 500", timeout=6)
    return scan_text_for_problem(out, check_crash=True)

def check_package_error(pkg):
    found, reason = scan_text_for_problem(read_new_log_text(pkg))
    if found:
        return True, f"{reason} (Log File)"
    found, reason = check_logcat_problem(pkg)
    if found:
        return True, f"{reason} (Logcat)"
    return False, None

def detect_problem(pkg):
    """Kiểm tra 1 tab. Trả về lý do nếu cần rejoin, không có vấn đề thì trả về None."""
    if not is_app_running(pkg):
        return "Tab bị tắt Đa nhiệm / Game crash (không còn tiến trình)"

    if not is_app_in_foreground(pkg):
        print(f"\033[1;33m[-] {pkg} bị thoát ra Màn hình chính/Lobby. Đang đếm ngược 5s...\033[0m")
        if wait_with_stop_check(5):
            return None
        if not is_app_running(pkg):
            return "Tab bị tắt Đa nhiệm / Game crash (không còn tiến trình)"
        if not is_app_in_foreground(pkg):
            return "Bị thoát ra Màn hình chính / Lobby"
        return None

    has_error, reason = check_package_error(pkg)
    return reason if has_error else None

def notify_async(message):
    """Gửi cảnh báo Discord ở luồng riêng để không làm chậm việc rejoin."""
    if WEBHOOK_URL:
        threading.Thread(target=send_detailed_alert, args=(message,), daemon=True).start()

def recover_tab(pkg, reason):
    """Bị kick/văng/crash: tắt tab (force-stop, xóa task Đa nhiệm) → mở lại game → vào Map."""
    print(f"\033[1;31m[-] Phát hiện {pkg} lỗi [{reason}]! Tắt tab Đa nhiệm rồi vào lại Map...\033[0m")
    notify_async(f"Phát hiện lỗi trên {pkg}: [{reason}]. Đã tắt tab Đa nhiệm, đang vào lại game/Map.")
    close_game(pkg)
    if wait_with_stop_check(2):
        return
    open_game_until_success(pkg, close_first=False)

# ==================== VÒNG LẶP CHÍNH ====================
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

def launch_all(packages):
    """Mở lần lượt các tab (>=4 tab: nhóm 3 tab, cách nhau 15s)."""
    total = len(packages)
    if total >= 4:
        batch_size = 3
        for i in range(0, total, batch_size):
            if stop_start: break
            for idx_b, pkg in enumerate(packages[i:i + batch_size]):
                if stop_start: break
                print(f"\033[1;36m[*] Đang khởi chạy Tab [{i + idx_b + 1}/{total}]: {pkg}\033[0m")
                open_game_until_success(pkg)
            if i + batch_size < total and not stop_start:
                print(f"\033[1;33m[*] Chờ 15 giây để mở nhóm tiếp theo...\033[0m")
                if wait_with_stop_check(15): break
    else:
        for idx, pkg in enumerate(packages):
            if stop_start: break
            print(f"\033[1;36m[*] Đang khởi chạy Tab [{idx + 1}/{total}]: {pkg}\033[0m")
            open_game_until_success(pkg)
            if idx < total - 1:
                print(f"\033[1;33m[*] Chờ {CLONE_LAUNCH_DELAY}s...\033[0m")
                if wait_with_stop_check(CLONE_LAUNCH_DELAY): break

def start_tool():
    global stop_start, START_UP_TIME
    stop_start = False
    clear_screen()
    print_ascii_banner()
    packages = get_all_packages()
    START_UP_TIME = datetime.now()
    LOG_STATE.clear()

    print(f"\033[1;37m[+] PAIN TOOL REJOIN VIP ({VERSION}) Đang chạy...\033[0m")
    print(f"\033[1;32m[*] Đã tìm thấy {len(packages)} bản clone ({PACKAGE_PREFIX}).\033[0m")
    if len(packages) >= 4:
        print(f"\033[1;33m[*] Số lượng tab >= 4, áp dụng mở nhóm 3 tab, cách nhau 15 giây.\033[0m")
    else:
        print(f"\033[1;33m[*] Delay mở mỗi tab clone: {CLONE_LAUNCH_DELAY} giây.\033[0m")
    print("\033[1;33m[*] Bấm phím 0 rồi nhấn Enter để ngắt Start.\033[0m")
    print("--------------------------------------------------")

    listener = threading.Thread(target=listen_for_stop, daemon=True)
    listener.start()

    launch_all(packages)

    if not stop_start:
        send_webhook(f"Bắt đầu theo dõi {len(packages)} tab clone.", with_image=True)

    start_time = time.time()
    last_webhook_time = time.time()
    last_cleanup_time = time.time()

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
                    reason = detect_problem(pkg)
                    if reason:
                        recover_tab(pkg, reason)

            elif AUTO_REJOIN_MODE == 2:
                if elapsed_minutes >= DELAY_REJOIN_MINUTES:
                    print(f"\033[1;33m[*] Chu kỳ {DELAY_REJOIN_MINUTES}p hoàn tất. Restart toàn bộ tab...\033[0m")
                    for pkg in packages:
                        close_game(pkg)
                    time.sleep(3)
                    launch_all(packages)
                    start_time = time.time()

            if (time.time() - last_webhook_time) >= 300:
                print("\033[1;32m[*] Đã đủ 5 phút, đang gửi báo cáo ảnh chụp màn hình định kỳ (Im lặng, không ping)...\033[0m")
                send_webhook("Cập nhật trạng thái định kỳ (5 phút)", with_image=True)
                last_webhook_time = time.time()

            if wait_with_stop_check(2): break

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
                        open_game(pkg)
                        print(f"\033[1;32m[+] Đã mở package [{global_idx}/{total_clones}]: {pkg}\033[0m")
                    if i + batch_size < total_clones:
                        print(f"\033[1;33m[*] Chờ 15 giây để mở nhóm tiếp theo...\033[0m")
                        time.sleep(15)
            else:
                for idx, pkg in enumerate(found_pkgs):
                    open_game(pkg)
                    print(f"\033[1;32m[+] Đã mở package: {pkg}\033[0m")
                    if idx < len(found_pkgs) - 1:
                        time.sleep(CLONE_LAUNCH_DELAY)
            print("\033[1;32m[+] Hoàn tất mở các tab clone!\033[0m")
            time.sleep(2)
        elif choice == "9":
            handle_send_text()
        elif choice == "0":
            sys.exit(0)
