import os
import sys
import time
import subprocess
import json
import threading
import re
import shlex
from datetime import datetime
from dotenv import load_dotenv

# Nạp cấu hình từ file .env riêng biệt
load_dotenv()

VERSION = "v1.3.3"

CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".pain_config.json")

# Lấy webhook từ file .env, nếu không có file .env sẽ để rỗng
SEND_TEXT_WEBHOOK = os.getenv("SEND_TEXT_WEBHOOK", "")

MAX_PACKAGES = 5             # tối đa số package name được thêm
PACKAGE_NAMES = []           # danh sách package name (tab clone) tool sẽ chạy
PKG_NAME_RX = re.compile(r"[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+")
TARGET_LINK = ""
SELECTED_GAME_NAME = "Chưa chọn"

DISCORD_LINK = "https://discord.gg/z7RUNArBuJ"

DELAY_REJOIN_MINUTES = 1     # chu kỳ delay rejoin (phút): hết chu kỳ tự tắt Đa nhiệm rồi vào lại Map
CLONE_LAUNCH_DELAY = 10
stop_start = False

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
RETRY_COUNTDOWN_SECONDS = 5  # tab không vào lại được game: đếm ngược bấy nhiêu giây rồi tắt Đa nhiệm và vào lại
LOGCAT_BASELINE = {}         # pkg -> mốc thời gian (epoch) logcat đã đọc tới, chỉ lấy dòng mới hơn mốc này

# ==================== TIỆN ÍCH GIAO DIỆN / PHẢN HỒI ====================
GREEN = "\033[1;32m"
RED = "\033[1;31m"
YELLOW = "\033[1;33m"
CYAN = "\033[1;36m"
WHITE = "\033[1;37m"
RESET = "\033[0m"

def msg_ok(text):
    print(f"{GREEN}[✓] {text}{RESET}")

def msg_err(text):
    print(f"{RED}[✗] {text}{RESET}")

def msg_warn(text):
    print(f"{YELLOW}[!] {text}{RESET}")

def msg_info(text):
    print(f"{CYAN}[*] {text}{RESET}")

def ack_choice(label, delay=0.7):
    """Xác nhận ngay mục người dùng vừa chọn trước khi thực hiện."""
    print(f"{CYAN}[»] Bạn đã chọn: {WHITE}{label}{RESET}")
    time.sleep(delay)

def pause(text="Ấn Enter để tiếp tục..."):
    """Dừng lại cho người dùng đọc thông báo trước khi màn hình bị xóa."""
    try:
        input(f"\n{CYAN}{text}{RESET}")
    except (EOFError, KeyboardInterrupt):
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

def load_saved_config():
    """Nạp danh sách package name đã lưu (lọc lại cho hợp lệ, tối đa MAX_PACKAGES)."""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return
    names = data.get("packages", []) if isinstance(data, dict) else []
    PACKAGE_NAMES.clear()
    for n in names if isinstance(names, list) else []:
        if isinstance(n, str) and PKG_NAME_RX.fullmatch(n) and n not in PACKAGE_NAMES and len(PACKAGE_NAMES) < MAX_PACKAGES:
            PACKAGE_NAMES.append(n)

def save_config_file():
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"packages": PACKAGE_NAMES}, f, ensure_ascii=False, indent=4)
    except Exception:
        pass

def get_all_packages():
    return list(PACKAGE_NAMES)

def is_package_installed(pkg):
    """True/False = máy có / chưa cài package. None = không truy vấn được `pm` (khi đó cho thêm nhưng có cảnh báo)."""
    if not run_cmd(["pm", "list", "packages", "android"]):
        return None
    return f"package:{pkg}" in run_cmd(["pm", "list", "packages", pkg]).split()

def print_package_list():
    print(f"\033[1;37mPackage name đang dùng ({len(PACKAGE_NAMES)}/{MAX_PACKAGES}):\033[0m")
    if not PACKAGE_NAMES:
        print("  (chưa có package nào)")
    for i, p in enumerate(PACKAGE_NAMES, 1):
        print(f"  \033[1;36m{i}.\033[0m {p}")

def package_name_menu():
    while True:
        clear_screen()
        print(f"{GREEN}=== PACKAGE NAME ==={RESET}")
        print_package_list()
        print()
        print(f"{WHITE}1. Add package name{RESET}")
        print(f"{WHITE}2. Remove package name{RESET}")
        print(f"{GREEN}0. Quay lại menu chính{RESET}")
        sub = input("Chọn: ").strip()
        if sub == "0":
            msg_info("Đang quay lại menu chính...")
            time.sleep(0.8)
            return
        if sub == "1":
            ack_choice("1. Add package name")
            if len(PACKAGE_NAMES) >= MAX_PACKAGES:
                msg_err(f"Đã đủ {MAX_PACKAGES} package, hãy Remove bớt trước khi thêm.")
                pause()
                continue
            name = input("Nhập package name cần thêm (Enter để hủy): ").strip()
            if not name:
                msg_warn("Đã hủy thao tác thêm package name.")
                time.sleep(1.2)
                continue
            if not PKG_NAME_RX.fullmatch(name):
                msg_err("Package name không hợp lệ (ví dụ: com.roblox.client).")
            elif name in PACKAGE_NAMES:
                msg_warn("Package này đã có trong danh sách, không cần thêm lại.")
            else:
                installed = is_package_installed(name)
                if installed is False:
                    msg_err(f"Máy chưa cài package '{name}'.")
                else:
                    PACKAGE_NAMES.append(name)
                    save_config_file()
                    msg_ok(f"Đã thêm package {name} thành công ({len(PACKAGE_NAMES)}/{MAX_PACKAGES}) và lưu cấu hình!")
                    if installed is None:
                        msg_warn("Không kiểm tra được package đã cài hay chưa (không đọc được `pm`), hãy tự kiểm tra tên.")
            pause()
        elif sub == "2":
            ack_choice("2. Remove package name")
            if not PACKAGE_NAMES:
                msg_warn("Chưa có package nào để xóa.")
                pause()
                continue
            name = input("Nhập package name cần xóa (hoặc số thứ tự, Enter để hủy): ").strip()
            if not name:
                msg_warn("Đã hủy thao tác xóa package name.")
                time.sleep(1.2)
                continue
            if name.isdigit() and 1 <= int(name) <= len(PACKAGE_NAMES):
                name = PACKAGE_NAMES[int(name) - 1]
            if name in PACKAGE_NAMES:
                PACKAGE_NAMES.remove(name)
                save_config_file()
                msg_ok(f"Đã xóa package {name} thành công ({len(PACKAGE_NAMES)}/{MAX_PACKAGES}) và lưu cấu hình!")
            else:
                msg_err(f"'{name}' không có trong danh sách.")
            pause()
        else:
            msg_err("Lựa chọn không hợp lệ, vui lòng chọn 0, 1 hoặc 2.")
            time.sleep(1.2)

def handle_send_text():
    while True:
        clear_screen()
        print(f"{GREEN}=== SEND TEXT TO DISCORD ==={RESET}")

        if not SEND_TEXT_WEBHOOK:
            msg_err("Không tìm thấy link Webhook! Vui lòng kiểm tra lại ")
            pause()
            return

        content_input = input("Nhập nội dung muốn gửi (Để trống để thoát): ").strip()
        if not content_input:
            msg_info("Đã thoát về giao diện chính.")
            time.sleep(1)
            return

        discord_id = input("Nhập UID tài khoản Discord (Để trống để bỏ qua): ").strip()
        now = datetime.now()
        footer_text = "MADE BY PAIN"

        user_tag_str = f"<@{discord_id}>" if discord_id else "Ẩn danh"
        uid_str = discord_id if discord_id else "Không có"

        description_text = (
            f"Bạn có nội dung gửi từ PAIN TOOL REJOIN ({VERSION})\n\n"
            f"{content_input}\n\n"
            "👤 Thông tin người gửi:\n"
            f"• Tên người dùng: {user_tag_str}\n"
            f"• UID: {uid_str}\n\n"
            "🕐 Thời gian gửi:\n"
            f"{now.strftime('%d/%m/%Y lúc %H:%M:%S')}"
        )

        embed_data = {
            "username": "PAIN TOOL REJOIN",
            "avatar_url": "https://i.postimg.cc/gJbhCmHL/Pain-Gamer.png",
            "embeds": [{"description": description_text, "footer": {"text": footer_text}, "color": 65280}]
        }
        if discord_id:
            embed_data["content"] = f"<@{discord_id}>"

        msg_info("Đang gửi nội dung tới Discord, vui lòng chờ...")
        code = run_cmd(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-X", "POST", SEND_TEXT_WEBHOOK,
                        "-H", "Content-Type: application/json", "-d", json.dumps(embed_data)], timeout=20)
        if code.startswith("2"):
            msg_ok("Đã gửi nội dung thành công qua Webhook!")
        else:
            msg_err(f"Gửi thất bại ({'mã ' + code if code else 'không kết nối được mạng'}).")
        pause()

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
    for line in sh("ps -A", timeout=3).splitlines():
        parts = line.split()
        if parts and parts[-1] == pkg:
            return True
    return False

def is_app_in_foreground(pkg):
    """True = tab còn cửa sổ đang mở, False = tab đã mất cửa sổ / thoát ra màn hình chính.
    Không đọc được dumpsys (vd máy không root) thì coi như ổn, tránh rejoin nhầm liên tục."""
    markers = ("mCurrentFocus", "mFocusedApp", "mResumedActivity", "topResumedActivity")
    dump = sh("dumpsys window displays", timeout=5)
    if not any(m in dump for m in markers):
        dump = sh("dumpsys activity activities", timeout=5)
    if not any(m in dump for m in markers):
        return True
    return pkg in dump

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

def launch_commands(pkg, enter_map=True, soft=False):
    """Các cách mở game, ưu tiên cách đầu; lỗi thì dùng cách dự phòng.
    enter_map=False: chỉ mở app, không vào map.
    soft=True: tab đang chạy -> giữ nguyên task (không tắt Đa nhiệm), chỉ đưa lên và gửi lệnh vào map.
    soft=False: --activity-clear-task để tab mới thay thế hẳn tab cũ trong Đa nhiệm."""
    clear = [] if soft else ["--activity-clear-task"]
    deep_link = build_deep_link() if enter_map else None
    if deep_link:
        base = ["am", "start", "-a", "android.intent.action.VIEW", "-d", deep_link]
    else:
        base = ["am", "start", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER"]
    cmds = [base + clear + [pkg]]
    if clear:
        cmds.append(base + [pkg])
    if not deep_link:
        cmds.append(["monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1"])
    return cmds

def mark_launched(pkg):
    """Mốc mới cho tab: log/logcat cũ trước thời điểm này sẽ bị bỏ qua, không bị bắt lại lỗi cũ."""
    path = get_latest_log_file(pkg)
    LOG_STATE[pkg] = (path, get_file_size(path) if path else 0)
    LOGCAT_BASELINE[pkg] = time.time()

def open_game(pkg, hard=False, enter_map=True):
    """hard=True : tắt hẳn tab (tắt Đa nhiệm) rồi mở mới.
    hard=False: tab đã mở sẵn thì GIỮ NGUYÊN (không tắt Đa nhiệm), chỉ đưa lên và vào map; tab chưa mở thì mở mới.
    enter_map=False: chỉ mở app, không vào map."""
    running = is_app_running(pkg)
    if hard and running:
        close_game(pkg)
        time.sleep(1)
        running = is_app_running(pkg)
        if running:
            print(f"\033[1;31m[!] Không tắt được {pkg} (máy không root nên không force-stop được?). Vẫn thử mở lại...\033[0m")
    mark_launched(pkg)
    soft = running and not hard
    for cmd in launch_commands(pkg, enter_map=enter_map, soft=soft):
        out = sh_args(cmd, merge_stderr=True).lower()
        if not any(w in out for w in ("error", "exception", "unable to resolve", "unknown option")):
            return True
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

def read_new_log_text(pkg):
    """Phần log file MỚI của tab (cần root)."""
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

_EPOCH_RX = re.compile(r"^\s*(\d{9,11}\.\d+)")

def read_new_logcat_text(pkg):
    """Logcat MỚI của đúng tab này (theo PID, không lẫn các clone khác).
    Lọc theo mốc thời gian nên tab vào lại mà không tắt (cùng PID) cũng không bị bắt lại lỗi cũ."""
    pids = sh(f"pidof {pkg}", timeout=3).split()
    if not pids:
        return ""
    out = sh(f"logcat -d -v epoch --pid={pids[0]} -t 500", timeout=6)
    base = LOGCAT_BASELINE.get(pkg, time.time())
    newest = base
    fresh = []
    for line in out.splitlines():
        m = _EPOCH_RX.match(line)
        if not m:
            continue
        ts = float(m.group(1))
        if ts > base:
            fresh.append(line)
            newest = max(newest, ts)
    LOGCAT_BASELINE[pkg] = newest
    return "\n".join(fresh)

def check_package_error(pkg):
    found, reason = scan_text_for_problem(read_new_log_text(pkg))
    if found:
        return True, f"{reason} (Log File)"
    found, reason = scan_text_for_problem(read_new_logcat_text(pkg), check_crash=True)
    if found:
        return True, f"{reason} (Logcat)"
    return False, None

def quick_problem(pkg):
    """Kiểm tra nhanh sau khi vào map. Trả về lý do nếu chưa ổn, None nếu ổn."""
    if not is_app_running(pkg):
        return "Game bị tắt / crash (không còn tiến trình)"
    if not is_app_in_foreground(pkg):
        return "Không thấy cửa sổ game"
    has_error, reason = check_package_error(pkg)
    return reason if has_error else None

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

def retry_countdown(pkg, why):
    """Tab không vào lại được game: đếm ngược RETRY_COUNTDOWN_SECONDS giây. Hết giờ thì caller tắt Đa nhiệm (force-stop) và vào lại.
    Trả về True nếu bị ngắt giữa chừng (bấm dừng Start)."""
    print(f"\033[1;33m[-] {pkg}: {why}. Sau {RETRY_COUNTDOWN_SECONDS}s sẽ tắt Đa nhiệm và vào lại...\033[0m")
    print("\033[1;33m    Đếm ngược: ", end="", flush=True)
    for sec in range(RETRY_COUNTDOWN_SECONDS, 0, -1):
        print(f"{sec}..", end=" ", flush=True)
        if wait_with_stop_check(1):
            print("\033[0m")
            return True
    print("\033[0m")
    return False

def join_map(pkg, hard=False):
    """Vào Map tối đa LAUNCH_MAX_RETRY lần.
    Mỗi lần: mở / gửi lệnh vào map -> chờ app lên -> chờ map load -> kiểm tra lại.
    Tab không vào được game: đếm ngược 5s -> tắt hẳn tab (tắt Đa nhiệm) -> mở lại vào map.
    Lần 1: tab đã mở sẵn thì chỉ vào map, không tắt Đa nhiệm (trừ khi hard=True). Từ lần 2 trở đi luôn tắt hẳn rồi mở lại."""
    for attempt in range(1, LAUNCH_MAX_RETRY + 1):
        if stop_start:
            return False
        print(f"\033[1;33m[*] Vào Map {pkg} (lần {attempt}/{LAUNCH_MAX_RETRY})...\033[0m")
        open_game(pkg, hard=(hard or attempt > 1))

        started = False
        for _ in range(max(1, LAUNCH_VERIFY_SECONDS // 2)):
            if wait_with_stop_check(2):
                return False
            if is_app_running(pkg):
                started = True
                break
        if not started:
            print(f"\033[1;31m[!] {pkg} chưa lên sau {LAUNCH_VERIFY_SECONDS}s.\033[0m")
            if attempt < LAUNCH_MAX_RETRY and retry_countdown(pkg, "Tab không lên được game"):
                return False
            continue

        print(f"\033[1;33m[*] {pkg} đã bật. Chờ {MAP_LOAD_WAIT}s để Map ổn định...\033[0m")
        if wait_with_stop_check(MAP_LOAD_WAIT):
            return False
        problem = quick_problem(pkg)
        if not problem:
            print(f"\033[1;32m[+] {pkg} đã vào Map.\033[0m")
            return True
        print(f"\033[1;31m[!] {pkg} chưa vào được Map [{problem}].\033[0m")
        if attempt < LAUNCH_MAX_RETRY and retry_countdown(pkg, "Tab không vào lại được game"):
            return False

    print(f"\033[1;31m[!] Không vào được Map {pkg} sau {LAUNCH_MAX_RETRY} lần.\033[0m")
    return False

def launch_all(packages, hard=False):
    """Vào Map lần lượt các tab (>=4 tab: nhóm 3 tab, cách nhau 15s).
    hard=False: tab đã mở sẵn thì chỉ vào Map, không tắt Đa nhiệm (lúc bấm Start).
    hard=True : tắt hẳn từng tab (tắt Đa nhiệm) rồi mở lại vào Map (hết chu kỳ delay rejoin)."""
    total = len(packages)
    if total >= 4:
        batch_size = 3
        for i in range(0, total, batch_size):
            if stop_start: break
            for idx_b, pkg in enumerate(packages[i:i + batch_size]):
                if stop_start: break
                print(f"\033[1;36m[*] Đang khởi chạy Tab [{i + idx_b + 1}/{total}]: {pkg}\033[0m")
                join_map(pkg, hard=hard)
            if i + batch_size < total and not stop_start:
                print(f"\033[1;33m[*] Chờ 15 giây để mở nhóm tiếp theo...\033[0m")
                if wait_with_stop_check(15): break
    else:
        for idx, pkg in enumerate(packages):
            if stop_start: break
            print(f"\033[1;36m[*] Đang khởi chạy Tab [{idx + 1}/{total}]: {pkg}\033[0m")
            join_map(pkg, hard=hard)
            if idx < total - 1:
                print(f"\033[1;33m[*] Chờ {CLONE_LAUNCH_DELAY}s...\033[0m")
                if wait_with_stop_check(CLONE_LAUNCH_DELAY): break

def start_tool():
    global stop_start
    stop_start = False
    clear_screen()
    print_ascii_banner()
    packages = get_all_packages()
    LOG_STATE.clear()
    LOGCAT_BASELINE.clear()

    if not packages:
        msg_err("Chưa có package nào. Vào mục [4] Package name > Add package name để thêm (tối đa 5).")
        pause()
        return

    print(f"\033[1;37m[+] PAIN TOOL REJOIN FREE ({VERSION}) Đang chạy...\033[0m")
    msg_ok(f"Đã khởi động Start với {len(packages)}/{MAX_PACKAGES} package: {', '.join(packages)}")
    print(f"\033[1;32m[*] Delay Rejoin: mỗi {DELAY_REJOIN_MINUTES} phút tự thoát game, tắt Đa nhiệm rồi vào lại Map.\033[0m")
    if not TARGET_LINK:
        print("\033[1;31m[!] Chưa chọn game (mục [3] Chọn game): tool chỉ mở app, không vào Map.\033[0m")
    if len(packages) >= 4:
        print(f"\033[1;33m[*] Số lượng tab >= 4, áp dụng mở nhóm 3 tab, cách nhau 15 giây.\033[0m")
    else:
        print(f"\033[1;33m[*] Delay mở mỗi tab clone: {CLONE_LAUNCH_DELAY} giây.\033[0m")
    print("\033[1;33m[*] Bấm phím 0 rồi nhấn Enter để ngắt Start.\033[0m")
    print("--------------------------------------------------")

    listener = threading.Thread(target=listen_for_stop, daemon=True)
    listener.start()

    launch_all(packages)
    start_time = time.time()

    try:
        while not stop_start:
            elapsed_minutes = (time.time() - start_time) / 60.0
            if elapsed_minutes >= DELAY_REJOIN_MINUTES:
                packages = get_all_packages()
                print(f"\033[1;33m[*] Chu kỳ {DELAY_REJOIN_MINUTES}p hoàn tất. Tắt Đa nhiệm và vào lại Map toàn bộ tab...\033[0m")
                launch_all(packages, hard=True)
                start_time = time.time()   # tính chu kỳ mới từ lúc vào lại xong

            if wait_with_stop_check(2): break

        if stop_start:
            print()
            msg_ok("Đã dừng Start thành công. Đang quay lại menu chính...")
            time.sleep(1.5)
            return

    except KeyboardInterrupt:
        print()
        msg_ok("Đã dừng Start thành công (Ctrl+C). Đang quay lại menu chính...")
        time.sleep(1.5)
        return


def show_banner():
    clear_screen()
    print_ascii_banner()
    
    sys_info = get_system_info()
    rejoin_mode_str = f"Delay Rejoin ({DELAY_REJOIN_MINUTES}p)"
    
    print("\033[1;32m--------------------------------------------------\033[0m")
    print("\033[1;37m             PAIN TOOL REJOIN FREE               \033[0m")
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
    pkg_txt = ", ".join(PACKAGE_NAMES) or "Chưa thêm"
    if len(pkg_txt) > 26:
        pkg_txt = pkg_txt[:25] + "…"
    print(f"\033[1;32m Package Name    :\033[0m \033[1;37m{len(PACKAGE_NAMES)}/{MAX_PACKAGES} · {pkg_txt}\033[0m")
    print(f"\033[1;32m Chế độ Game     :\033[0m \033[1;37m{SELECTED_GAME_NAME}\033[0m")
    print(f"\033[1;32m Cơ chế Rejoin   :\033[0m \033[1;37m{rejoin_mode_str}\033[0m")
    print("\033[1;32m==================================================\033[0m")
    print("\033[1;32m[1]\033[0m \033[1;37mStart\033[0m")
    print("\033[1;32m[2]\033[0m \033[1;37mSet up delay rejoin\033[0m")
    print("\033[1;32m[3]\033[0m \033[1;37mChọn game\033[0m")
    print("\033[1;32m[4]\033[0m \033[1;37mPackage name\033[0m")
    print("\033[1;32m[5]\033[0m \033[1;37mXóa cache\033[0m")
    print("\033[1;32m[6]\033[0m \033[1;37mImport auto execute\033[0m")
    print("\033[1;32m[7]\033[0m \033[1;37mMở tab clone\033[0m")
    print("\033[1;32m[8]\033[0m \033[1;37mSEND TEXT\033[0m")
    print("\033[1;31m[0] Exit\033[0m")
    print("\033[1;32m==================================================\033[0m")

GAMES = {
    "1": ("Blox Fruit", "2753915549"),
    "2": ("Grow a Garden", "126884695634066"),
    "3": ("Grow a Garden 2", "97598239454123"),
    "4": ("Blade Ball", "13772394625"),
    "5": ("King Legacy", "4520749081"),
    "6": ("Fisch", "16732694052"),
    "7": ("Pet Simulator 99", "8737899170"),
    "8": ("Anime Vanguards", "16146832113"),
    "9": ("99 Nights in the Forest", "79546208627805"),
    "10": ("Steal a Brainrot", "109983668079237"),
    "11": ("Steal An Egg", "107778070777162"),
}

def setup_delay_rejoin():
    global DELAY_REJOIN_MINUTES
    clear_screen()
    print(f"{GREEN}=== SET UP DELAY REJOIN ==={RESET}")
    print(f"{WHITE}Chu kỳ hiện tại: {DELAY_REJOIN_MINUTES} phút{RESET}")
    print("Hết mỗi chu kỳ tool tự thoát app game, tắt Đa nhiệm rồi vào lại Map.")
    print("Tab nào không vào lại được game sẽ đếm ngược 5 giây, tắt Đa nhiệm và vào lại.")
    mins = input("Nhập thời gian chu kỳ (phút, Enter để giữ nguyên): ").strip()
    if not mins:
        msg_info(f"Giữ nguyên chu kỳ hiện tại: {DELAY_REJOIN_MINUTES} phút.")
        time.sleep(1.5)
    elif mins.isdigit() and int(mins) > 0:
        DELAY_REJOIN_MINUTES = int(mins)
        msg_ok(f"Đã cập nhật Delay Rejoin thành công: {DELAY_REJOIN_MINUTES} phút!")
        pause()
    else:
        msg_err("Chu kỳ phải là số nguyên lớn hơn 0. Chưa có thay đổi nào được áp dụng.")
        pause()

def choose_game():
    global TARGET_LINK, SELECTED_GAME_NAME
    clear_screen()
    print(f"{GREEN}=== CHỌN GAME ==={RESET}")
    for key, (name, _pid) in GAMES.items():
        print(f"{WHITE}{key}. {name}{RESET}")
    print(f"{WHITE}12. Custom ID / Private Link{RESET}")
    game_choice = input("Chọn game [1-12]: ").strip()
    if game_choice in GAMES:
        SELECTED_GAME_NAME, TARGET_LINK = GAMES[game_choice]
        msg_ok(f"Đã chọn game thành công: {SELECTED_GAME_NAME} (ID: {TARGET_LINK})")
        pause()
    elif game_choice == "12":
        link = input("Nhập ID game hoặc Link Server VIP: ").strip()
        if link:
            TARGET_LINK = link
            SELECTED_GAME_NAME = f"Game ID: {link}" if link.isdigit() else "Server VIP Custom"
            msg_ok(f"Đã nhận link/ID thành công! Chế độ hiện tại: {SELECTED_GAME_NAME}")
            pause()
        else:
            msg_warn("Chưa nhập link/ID nên không có thay đổi nào được áp dụng.")
            time.sleep(1.5)
    else:
        msg_err("Lựa chọn không hợp lệ, vui lòng chọn từ 1 đến 12.")
        time.sleep(1.5)

def clear_cache_action():
    clear_screen()
    packages = get_all_packages()
    if not packages:
        msg_err("Chưa có package nào. Vào mục [4] Package name để thêm.")
        pause()
        return
    if not root_mode():
        msg_err("Máy không có root nên không xóa được cache của app.")
        pause()
        return
    msg_info(f"Đang xóa cache của {len(packages)} package, vui lòng chờ...")
    # Chỉ xóa cache (KHÔNG pm clear) nên không mất đăng nhập
    for pkg in packages:
        sh(f"rm -rf /data/data/{pkg}/cache/* /data/data/{pkg}/code_cache/*")
        msg_ok(f"Đã xóa cache: {pkg}")
    sh("sync && echo 3 > /proc/sys/vm/drop_caches")
    msg_ok("Đã xóa cache và dọn RAM thành công (không xóa dữ liệu đăng nhập)!")
    pause()

def import_autoexec():
    clear_screen()
    script_data = input("Nhập script hack (Để trống để thoát): ").strip()
    if not script_data:
        msg_warn("Đã hủy import auto execute (chưa nhập script).")
        time.sleep(1.2)
        return
    msg_info("Đang lưu script vào các thư mục Autoexec...")
    temp_path = "/sdcard/temp_autoexec.lua"
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(script_data)
    except Exception as e:
        msg_err(f"Không ghi được file tạm {temp_path}: {e}")
        pause()
        return
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
    msg_ok(f"Đã lưu script Autoexec thành công vào {len(target_dirs)} thư mục!")
    pause()

def open_clone_tabs():
    clear_screen()
    found_pkgs = get_all_packages()
    if not found_pkgs:
        msg_err("Chưa có package nào. Vào mục [4] Package name để thêm.")
        pause()
        return
    msg_info("Đang mở hàng loạt tab (chỉ mở app, không vào Map)... (Ấn Ctrl+C để dừng)")
    opened = 0
    total_clones = len(found_pkgs)

    def _open_one(pkg, label):
        nonlocal opened
        msg_info(f"Đang mở tab {label}: {pkg}")
        # enter_map=False: chỉ mở app, không gửi lệnh vào Map
        if open_game(pkg, hard=True, enter_map=False):
            opened += 1
            msg_ok(f"Đã mở tab {label}: {pkg}")
        else:
            msg_err(f"Không mở được tab {label}: {pkg}")

    try:
        if total_clones >= 4:
            batch_size = 3
            for i in range(0, total_clones, batch_size):
                batch = found_pkgs[i:i + batch_size]
                for idx_b, pkg in enumerate(batch):
                    _open_one(pkg, f"[{i + idx_b + 1}/{total_clones}]")
                if i + batch_size < total_clones:
                    msg_warn("Chờ 15 giây để mở nhóm tiếp theo...")
                    time.sleep(15)
        else:
            for idx, pkg in enumerate(found_pkgs):
                _open_one(pkg, f"[{idx + 1}/{total_clones}]")
                if idx < total_clones - 1:
                    msg_warn(f"Chờ {CLONE_LAUNCH_DELAY}s trước khi mở tab tiếp theo...")
                    time.sleep(CLONE_LAUNCH_DELAY)
    except KeyboardInterrupt:
        print()
        msg_warn(f"Đã dừng giữa chừng bằng Ctrl+C ({opened}/{total_clones} tab đã mở).")
        pause()
        return

    if opened == total_clones:
        msg_ok(f"Hoàn tất mở tất cả tab clone thành công ({opened}/{total_clones})!")
    elif opened > 0:
        msg_warn(f"Chỉ mở được {opened}/{total_clones} tab, các tab còn lại thất bại.")
    else:
        msg_err(f"Không mở được tab clone nào (0/{total_clones}).")
    pause()

def exit_tool():
    print(f"\n{GREEN}[✓] Đã thoát tool thành công. Tạm biệt!{RESET}")
    time.sleep(1)
    sys.exit(0)

if __name__ == "__main__":
    load_saved_config()
    try:
        while True:
            show_banner()
            choice = input("Chọn chức năng [0-8]: ").strip()
            if choice == "1":
                ack_choice("[1] Start")
                start_tool()
            elif choice == "2":
                ack_choice("[2] Set up delay rejoin")
                setup_delay_rejoin()
            elif choice == "3":
                ack_choice("[3] Chọn game")
                choose_game()
            elif choice == "4":
                ack_choice("[4] Package name")
                package_name_menu()
            elif choice == "5":
                ack_choice("[5] Xóa cache")
                clear_cache_action()
            elif choice == "6":
                ack_choice("[6] Import auto execute")
                import_autoexec()
            elif choice == "7":
                ack_choice("[7] Mở tab clone")
                open_clone_tabs()
            elif choice == "8":
                ack_choice("[8] SEND TEXT")
                handle_send_text()
            elif choice == "0":
                exit_tool()
            else:
                msg_err(f"Lựa chọn '{choice}' không hợp lệ. Vui lòng nhập số từ 0 đến 8.")
                time.sleep(1.5)
    except KeyboardInterrupt:
        exit_tool()
