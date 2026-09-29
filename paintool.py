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
import shutil
import getpass
import unicodedata
from datetime import datetime, timezone

VERSION = "v1.5.5 Beta"
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

AUTO_REJOIN_MODE = 1          # 1 = Auto rejoin vang/crash, 2 = Delay rejoin (vào lại map theo chu kỳ)
DELAY_REJOIN_MINUTES = 1
CLONE_LAUNCH_DELAY = 10
stop_start = False
START_UP_TIME = None

# ---- Auto Clear Data / Khôi phục tab kẹt ----
AUTO_CLEAR_DATA = True        # tab treo (không có log mới) quá FREEZE_TIMEOUT_MIN phút -> pm clear -> khôi phục backup -> mở lại
FREEZE_TIMEOUT_MIN = 4        # ngưỡng coi là treo cứng: 3-5 phút
CLEAR_COOLDOWN_SEC = 600      # 1 tab vừa bị xóa data thì 10 phút sau mới được xóa lại (tránh lặp vô hạn)

# ---- Sao lưu & khôi phục dữ liệu tab ----
AUTO_BACKUP = True            # tự backup định kỳ các tab đang chạy ổn định
BACKUP_INTERVAL_MIN = 30
BACKUP_STABLE_SECONDS = 120   # tab phải vào map ổn định ít nhất bấy nhiêu giây mới được auto backup
BACKUP_DIR = "/sdcard/PainBackup"
BACKUP_EXCLUDE = ("cache", "code_cache")   # bỏ qua cache cho nhẹ, chỉ giữ dữ liệu đăng nhập/cài đặt

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
LOGCAT_BASELINE = {}         # pkg -> mốc thời gian (epoch) logcat đã đọc tới, chỉ lấy dòng mới hơn mốc này
LAST_ACTIVITY = {}           # pkg -> lần cuối thấy log mới (dùng để phát hiện tab treo)
LAST_CLEAR = {}              # pkg -> lần cuối bị tự động xóa data
LAST_SOFT_JOIN = {}          # pkg -> lần cuối vào lại map mà không tắt tab
JOINED_AT = {}               # pkg -> lúc vào map thành công
LAST_BACKUP = {}             # pkg -> lần cuối auto backup (trong phiên chạy này)
NEEDS_LOGIN = set()          # tab vừa bị xóa data mà mất backup -> tạm không auto backup (tránh ghi đè bản tốt bằng bản chưa đăng nhập)
LOG_SOURCE_WORKS = False     # đã đọc được log của ít nhất 1 tab -> mới dám kết luận "treo"

# ---- Cảnh báo Discord thông minh (phân loại theo màu) ----
ALERT_STYLES = {
    "critical": {"color": 0xED4245, "icon": "🔴", "label": "LỖI NẶNG"},        # đỏ: Kick / Crash / treo / rejoin thất bại
    "lobby":    {"color": 0xFEE75C, "icon": "🟡", "label": "VĂNG LOBBY"},      # vàng: văng ra Lobby / màn hình chính
    "success":  {"color": 0x57F287, "icon": "🟢", "label": "REJOIN THÀNH CÔNG"},  # xanh: vào lại Map thành công
}
PING_LEVELS = ("critical",)   # mức nào thì ping Discord UID (thêm "lobby" / "success" nếu muốn ping cả hai)
ALERT_COOLDOWN_SEC = 20       # cùng 1 cảnh báo của cùng 1 tab trong khoảng này chỉ gửi 1 lần (chống spam)
_ALERT_LAST = {}
REJOIN_COUNT = {}             # pkg -> số lần đã phải rejoin trong phiên chạy này
ACCOUNTS = {}                 # pkg -> tên tài khoản Roblox đã login bằng mục Login Cookie (chỉ lưu tên, KHÔNG lưu cookie)

def get_rejoin_mode_str():
    if AUTO_REJOIN_MODE == 1:
        return "Auto rejoin vang/crash"
    return f"Delay Rejoin ({DELAY_REJOIN_MINUTES}p)"

def load_saved_config():
    global WEBHOOK_URL, DISCORD_UID, AUTO_CLEAR_DATA, FREEZE_TIMEOUT_MIN, AUTO_BACKUP
    if not os.path.exists(CONFIG_FILE):
        return
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return
    if not isinstance(data, dict):
        return
    WEBHOOK_URL = data.get("webhook_url", "")
    DISCORD_UID = data.get("discord_uid", "")
    AUTO_CLEAR_DATA = bool(data.get("auto_clear_data", AUTO_CLEAR_DATA))
    AUTO_BACKUP = bool(data.get("auto_backup", AUTO_BACKUP))
    mins = data.get("freeze_timeout_min", FREEZE_TIMEOUT_MIN)
    if isinstance(mins, int) and 3 <= mins <= 5:
        FREEZE_TIMEOUT_MIN = mins
    acc = data.get("accounts", {})
    if isinstance(acc, dict):
        ACCOUNTS.clear()
        ACCOUNTS.update({str(k): str(v) for k, v in acc.items() if isinstance(v, str)})

def save_config_file():
    try:
        data = {
            "webhook_url": WEBHOOK_URL,
            "discord_uid": DISCORD_UID,
            "auto_clear_data": AUTO_CLEAR_DATA,
            "freeze_timeout_min": FREEZE_TIMEOUT_MIN,
            "auto_backup": AUTO_BACKUP,
            "accounts": ACCOUNTS
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

# ==================== UI HELPERS ====================
class C:
    R = "\033[0m"
    PUR = "\033[1;35m"       # tím đậm (cùng tông với banner)
    LPUR = "\033[38;5;141m"  # tím nhạt (khung, phím menu)
    GRN = "\033[1;32m"
    RED = "\033[1;31m"
    YEL = "\033[1;33m"
    CYN = "\033[1;36m"
    WHT = "\033[1;37m"
    GRY = "\033[38;5;245m"

_ANSI_RX = re.compile(r"\033\[[0-9;]*m")

def _cw(ch):
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1

def vlen(s):
    """Độ rộng hiển thị thật của chuỗi (bỏ mã màu ANSI, tính đúng chữ có dấu)."""
    return sum(_cw(ch) for ch in _ANSI_RX.sub("", str(s)))

def clip(s, n):
    s = str(s)
    if vlen(s) <= n:
        return s
    out, w = "", 0
    for ch in s:
        if w + _cw(ch) > n - 1:
            break
        out += ch
        w += _cw(ch)
    return out + "…"

def ui_width():
    try:
        cols = shutil.get_terminal_size((58, 24)).columns
    except Exception:
        cols = 58
    return max(44, min(cols, 58))

def pad(text, width, align="left"):
    gap = max(0, width - vlen(text))
    if align == "center":
        left = gap // 2
        return " " * left + text + " " * (gap - left)
    return text + " " * gap

def box_top(w):
    return f"{C.LPUR}╭{'─' * (w - 2)}╮{C.R}"

def box_sep(w):
    return f"{C.LPUR}├{'─' * (w - 2)}┤{C.R}"

def box_bot(w):
    return f"{C.LPUR}╰{'─' * (w - 2)}╯{C.R}"

def box_row(text, w, align="left"):
    return f"{C.LPUR}│{C.R} {pad(text, w - 4, align)} {C.LPUR}│{C.R}"

def box_kv(label, value, w, lw=12):
    return box_row(f"{C.GRY}{pad(label, lw)}{C.R} {value}", w)

def dot(state):
    """True = xanh, False = đỏ, None = vàng."""
    color = C.GRN if state else (C.RED if state is False else C.YEL)
    return f"{color}●{C.R}"

def section_title(title):
    w = ui_width()
    print()
    print(f" {C.PUR}▌{C.R}{C.WHT} {title}{C.R}")
    print(f" {C.GRY}{'─' * (w - 2)}{C.R}")

def msg_ok(text):
    print(f"{C.GRN}[+] {text}{C.R}")

def msg_err(text):
    print(f"{C.RED}[!] {text}{C.R}")

def msg_info(text):
    print(f"{C.YEL}[*] {text}{C.R}")

def ask(label):
    print(f" {C.PUR}›{C.R} {C.WHT}{label}{C.R} ", end="", flush=True)
    return input()

def with_spinner(label, func, *args, **kwargs):
    """Chạy func ở luồng riêng, hiện spinner + số giây chờ (server Render có thể 'ngủ' vài chục giây)."""
    box = {}

    def worker():
        try:
            box["v"] = func(*args, **kwargs)
        except Exception as e:
            box["e"] = e

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    t0 = time.time()
    i = 0
    try:
        while t.is_alive():
            sys.stdout.write(f"\r {C.LPUR}{frames[i % len(frames)]}{C.R} {C.WHT}{label}{C.R} {C.GRY}({int(time.time() - t0)}s){C.R}   ")
            sys.stdout.flush()
            i += 1
            time.sleep(0.1)
    finally:
        sys.stdout.write("\r" + " " * (vlen(label) + 16) + "\r")
        sys.stdout.flush()
    if "e" in box:
        raise box["e"]
    return box.get("v")

def run_cmd(cmd_list, timeout=15, merge_stderr=False):
    try:
        res = subprocess.run(cmd_list, capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=timeout, stdin=subprocess.DEVNULL)
        out = res.stdout + ("\n" + res.stderr if merge_stderr else "")
        return out.strip()
    except Exception:
        return ""

_SYS_STATIC = {}

def get_system_info():
    if not _SYS_STATIC:
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
        _SYS_STATIC.update({"model": model, "android": android_ver, "cpu": cpu, "ram": ram_info})

    battery_info = "N/A"
    dumpsys_bat = run_cmd(["dumpsys", "battery"])
    if dumpsys_bat:
        for line in dumpsys_bat.splitlines():
            if "level:" in line:
                battery_info = f"{line.split(':')[1].strip()}%"
                break

    return dict(_SYS_STATIC, battery=battery_info)

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

def license_screen(hwid, note=None):
    clear_screen()
    print_ascii_banner()
    w = ui_width()
    lw = 12
    vw = w - 4 - lw - 1
    info = get_system_info()
    print(box_top(w))
    print(box_row(f"{C.WHT}XÁC THỰC BẢN QUYỀN{C.R}", w, "center"))
    print(box_row(f"{C.GRY}Nhập key để kích hoạt tool{C.R}", w, "center"))
    print(box_sep(w))
    print(box_kv("Trạng thái", f"{dot(False)} {C.RED}Chưa kích hoạt{C.R}", w, lw))
    print(box_kv("Thiết bị", clip(f"{info['model']} · Android {info['android']}", vw), w, lw))
    print(box_kv("Phiên bản", f"{C.LPUR}{VERSION}{C.R}", w, lw))
    print(box_kv("Lấy key", f"{C.CYN}{clip(DISCORD_LINK, vw)}{C.R}", w, lw))
    print(box_bot(w))
    print()
    print(f" {C.GRY}HWID của bạn (chạm giữ để sao chép, gửi admin để gắn key):{C.R}")
    print(f" {C.CYN}{hwid}{C.R}")
    print(f" {C.GRY}Nhập 0 hoặc exit để thoát.{C.R}")
    if note:
        print(f"\n {note}")
    print()

def authenticate():
    hwid = get_hwid()
    note = None
    if os.path.exists(LICENSE_FILE):
        saved = ""
        try:
            with open(LICENSE_FILE, "r") as f:
                saved = f.read().strip()
        except Exception:
            pass
        if saved:
            clear_screen()
            print_ascii_banner()
            print()
            is_valid, resp = with_spinner("Đang kiểm tra key đã lưu", check_license_curl, saved, hwid)
            if is_valid:
                msg_ok("Tự động xác thực bản quyền thành công!")
                time.sleep(1)
                return
            if resp == "Không kết nối được server":
                # lỗi mạng / server đang ngủ: giữ nguyên key đã lưu, không xóa
                note = f"{C.YEL}[!] Không kết nối được máy chủ. Kiểm tra mạng rồi nhập lại key.{C.R}"
            else:
                try:
                    os.remove(LICENSE_FILE)
                except Exception:
                    pass
                note = f"{C.RED}[!] Key đã lưu không còn hợp lệ, vui lòng nhập key mới.{C.R}"

    while True:
        license_screen(hwid, note)
        note = None
        input_key = ask("Nhập Key:").strip()
        if input_key.lower() in ("exit", "0"):
            sys.exit(0)
        if not input_key:
            continue
        is_valid, response_text = with_spinner("Đang kết nối máy chủ", check_license_curl, input_key, hwid)
        if is_valid:
            try:
                with open(LICENSE_FILE, "w") as f:
                    f.write(input_key)
            except Exception:
                pass
            msg_ok("Xác thực Key thành công!")
            time.sleep(1)
            break
        if response_text == "Không kết nối được server":
            note = f"{C.YEL}[!] Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại.{C.R}"
        else:
            note = f"{C.RED}[!] Thất bại: Key không hợp lệ hoặc sai HWID.{C.R}"

def send_webhook(message, with_image=False):
    if not WEBHOOK_URL:
        return
    try:
        now = datetime.now()
        footer_text = "MADE BY PAIN"
        packages = get_all_packages()
        rejoin_mode_str = get_rejoin_mode_str()
        start_time_str = START_UP_TIME.strftime('%d/%m/%Y %H:%M:%S') if START_UP_TIME else "Mới khởi chạy"
        
        description_text = (
            f"**{message}**\n\n"
            f"📊 **Thông tin hệ thống:**\n"
            f"• **Phiên bản:** {VERSION}\n"
            f"• **Thời gian khởi động:** {start_time_str}\n"
            f"• **Số Tab đang treo:** {len(packages)} tab ({PACKAGE_PREFIX})\n"
            f"• **Chế độ Game:** {SELECTED_GAME_NAME}\n"
            f"• **Cơ chế Rejoin:** {rejoin_mode_str}\n"
            f"• **Auto Clear Data:** {'Bật (' + str(FREEZE_TIMEOUT_MIN) + 'p)' if AUTO_CLEAR_DATA else 'Tắt'}\n"
            f"• **Auto Backup:** {'Bật' if AUTO_BACKUP else 'Tắt'}\n"
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

# ==================== CẢNH BÁO DISCORD THÔNG MINH ====================
def classify_reason(reason):
    """'critical' (đỏ) = Kick / Crash / mất kết nối / treo, 'lobby' (vàng) = văng ra Lobby / màn hình chính."""
    low = (reason or "").lower()
    if any(k in low for k in ("kick", "mã lỗi", "crash", "mất kết nối", "không còn tiến trình", "treo")):
        return "critical"
    if any(k in low for k in ("lobby", "màn hình chính", "không thấy cửa sổ")):
        return "lobby"
    return "critical"

def alert_title_for(reason, level):
    low = (reason or "").lower()
    if level == "lobby":
        return "Văng ra Lobby"
    if "crash" in low or "không còn tiến trình" in low:
        return "Game Crash / Bị tắt"
    if "treo" in low:
        return "Tab treo cứng"
    return "Bị Kick / Mất kết nối"

def send_detailed_alert(level, title, description, pkg=None, reason=None, action=None, took=None):
    if not WEBHOOK_URL:
        return
    try:
        style = ALERT_STYLES.get(level, ALERT_STYLES["critical"])
        fields = []

        def add(name, value, inline=True):
            if value not in (None, ""):
                fields.append({"name": name, "value": str(value)[:1000], "inline": inline})

        add("📦 Package", f"`{pkg}`" if pkg else None)
        add("👤 Tài khoản", ACCOUNTS.get(pkg) if pkg else None)
        add("🎮 Game", SELECTED_GAME_NAME)
        add("🔁 Lần rejoin", REJOIN_COUNT.get(pkg) if pkg else None)
        add("⏱️ Xử lý trong", f"{took}s" if took is not None else None)
        add("⚠️ Nguyên nhân", reason, inline=False)
        add("🛠️ Hành động", action, inline=False)

        embed_obj = {
            "title": f"{style['icon']} {style['label']} · {title}",
            "description": description,
            "color": style["color"],
            "fields": fields,
            "footer": {"text": f"MADE BY PAIN • {VERSION}"},
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        }
        payload_dict = {
            "username": "PAIN TOOL REJOIN VIP",
            "avatar_url": "https://i.postimg.cc/gJbhCmHL/Pain-Gamer.png",
            "embeds": [embed_obj]
        }
        if DISCORD_UID and level in PING_LEVELS:
            payload_dict["content"] = f"<@{DISCORD_UID}>"

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
        section_title("SEND TEXT TO DISCORD")
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

def list_installed_packages():
    """Danh sách package khớp PACKAGE_PREFIX (không có phần 'giả' như get_all_packages khi máy chưa cài)."""
    out = run_cmd(["pm", "list", "packages"])
    pkgs = []
    for line in out.splitlines():
        if PACKAGE_PREFIX in line and ":" in line:
            pkgs.append(line.split(":", 1)[1].strip())
    return sorted(set(pkgs))

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
    """True = tab còn cửa sổ đang mở (chạy nền cùng các clone khác vẫn tính là ổn).
    False = tab đã mất cửa sổ / thoát ra màn hình chính.
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
    """Mốc mới cho tab: log/logcat cũ trước thời điểm này bị bỏ qua, và thời gian 'treo' được tính lại từ đầu."""
    path = get_latest_log_file(pkg)
    LOG_STATE[pkg] = (path, get_file_size(path) if path else 0)
    LOGCAT_BASELINE[pkg] = time.time()
    LAST_ACTIVITY[pkg] = time.time()
    JOINED_AT.pop(pkg, None)

def open_game(pkg, hard=False, enter_map=True):
    """hard=True : tắt hẳn tab rồi mở mới (dùng khi tab lỗi/crash/treo).
    hard=False: tab đã mở sẵn thì GIỮ NGUYÊN (không tắt Đa nhiệm), chỉ đưa lên và vào map; tab chưa mở thì mở mới.
    enter_map=False: chỉ mở app, không vào map."""
    running = is_app_running(pkg)
    if hard and running:
        close_game(pkg)
        time.sleep(1)
        running = False
    mark_launched(pkg)
    if running:
        LAST_SOFT_JOIN[pkg] = time.time()
    for cmd in launch_commands(pkg, enter_map=enter_map, soft=running):
        out = sh_args(cmd, merge_stderr=True).lower()
        if not any(w in out for w in ("error", "exception", "unable to resolve", "unknown option")):
            return True
    return False

def quick_problem(pkg):
    """Kiểm tra nhanh (không đếm ngược) sau khi vào map. Trả về lý do nếu chưa ổn, None nếu ổn."""
    if not is_app_running(pkg):
        return "Game bị tắt / crash (không còn tiến trình)"
    if not is_app_in_foreground(pkg):
        return "Không thấy cửa sổ game"
    has_error, reason = check_package_error(pkg)
    return reason if has_error else None

def join_map(pkg, hard=False):
    """Vào Map tối đa LAUNCH_MAX_RETRY lần (dùng chung cho chế độ 1 và 2).
    Mỗi lần: mở / gửi lệnh vào map -> chờ app lên -> chờ map load -> kiểm tra lại. Chưa ổn thì thử lần kế.
    Lần 1: tab đã mở sẵn thì chỉ vào map, không tắt Đa nhiệm. Từ lần 2 trở đi: tắt hẳn tab rồi mở lại."""
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
            print(f"\033[1;31m[!] {pkg} chưa lên sau {LAUNCH_VERIFY_SECONDS}s, thử lại...\033[0m")
            continue

        print(f"\033[1;33m[*] {pkg} đã bật. Chờ {MAP_LOAD_WAIT}s để Map ổn định...\033[0m")
        if wait_with_stop_check(MAP_LOAD_WAIT):
            return False
        problem = quick_problem(pkg)
        if not problem:
            JOINED_AT[pkg] = time.time()
            print(f"\033[1;32m[+] {pkg} đã vào Map.\033[0m")
            return True
        print(f"\033[1;31m[!] {pkg} chưa vào được Map [{problem}], thử lại...\033[0m")

    print(f"\033[1;31m[!] Không vào được Map {pkg} sau {LAUNCH_MAX_RETRY} lần.\033[0m")
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

def note_activity(pkg):
    """Tab vừa có log mới = còn phản hồi (dùng cho cơ chế phát hiện treo)."""
    global LOG_SOURCE_WORKS
    LAST_ACTIVITY[pkg] = time.time()
    LOG_SOURCE_WORKS = True

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
    text = sh(f"tail -c +{offset + 1} '{path}'", timeout=8)
    if text:
        note_activity(pkg)
    return text

_EPOCH_RX = re.compile(r"^\s*(\d{9,11}\.\d+)")

def read_new_logcat_text(pkg):
    """Logcat MỚI của đúng tab này (theo PID, không lẫn các clone khác).
    Lọc theo mốc thời gian nên tab được vào lại mà không tắt (cùng PID) cũng không bị bắt lại lỗi cũ."""
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
    text = "\n".join(fresh)
    if text:
        note_activity(pkg)
    return text

def collect_new_logs(pkg):
    """Chỉ đọc log để cập nhật mốc hoạt động (dùng khi không chạy dò lỗi, vd chế độ 2)."""
    read_new_log_text(pkg)
    read_new_logcat_text(pkg)

def check_package_error(pkg):
    found, reason = scan_text_for_problem(read_new_log_text(pkg))
    if found:
        return True, f"{reason} (Log File)"
    found, reason = scan_text_for_problem(read_new_logcat_text(pkg), check_crash=True)
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

def notify_async(level, title, description, pkg=None, reason=None, action=None, took=None):
    """Gửi cảnh báo Discord ở luồng riêng để không làm chậm việc rejoin. level: critical (đỏ) / lobby (vàng) / success (xanh)."""
    if not WEBHOOK_URL:
        return
    key = (level, pkg, title)
    now = time.time()
    if now - _ALERT_LAST.get(key, 0) < ALERT_COOLDOWN_SEC:
        return
    _ALERT_LAST[key] = now
    threading.Thread(target=send_detailed_alert, args=(level, title, description, pkg, reason, action, took), daemon=True).start()

def report_rejoin_result(pkg, ok, started, action):
    """Báo kết quả sau khi vào lại Map: xanh = thành công, đỏ = thất bại."""
    if stop_start:
        return
    took = int(time.time() - started)
    if ok:
        notify_async("success", "Rejoin thành công", f"`{pkg}` đã vào lại Map.", pkg=pkg, action=action, took=took)
    else:
        notify_async("critical", "Rejoin thất bại", f"`{pkg}` không vào lại được Map sau {LAUNCH_MAX_RETRY} lần thử.",
                     pkg=pkg, reason=f"Không vào được Map sau {LAUNCH_MAX_RETRY} lần thử",
                     action="Tool tiếp tục theo dõi và sẽ thử lại", took=took)

def recover_tab(pkg, reason):
    """Chế độ 1: bị kick/văng/crash -> vào lại Map.
    - Tab đã tắt (crash / mất tiến trình): mở lại.
    - Tab còn mở (kick, thoát ra lobby): chỉ vào lại Map, KHÔNG tắt Đa nhiệm.
    - Game crash thật (fatal), hoặc vừa vào lại mà vẫn lỗi: tắt hẳn tab rồi mở lại."""
    running = is_app_running(pkg)
    recently_soft = (time.time() - LAST_SOFT_JOIN.get(pkg, 0)) < 90
    hard = running and ("Crash" in reason or recently_soft)
    if not running:
        action = "Tab đã tắt, mở lại và vào Map"
    elif hard:
        action = "Tắt hẳn tab rồi vào lại Map"
    else:
        action = "Tab còn mở, chỉ vào lại Map (không tắt Đa nhiệm)"

    level = classify_reason(reason)
    REJOIN_COUNT[pkg] = REJOIN_COUNT.get(pkg, 0) + 1
    color = "\033[1;33m" if level == "lobby" else "\033[1;31m"
    print(f"{color}[-] Phát hiện {pkg} lỗi [{reason}]! {action}...\033[0m")
    notify_async(level, alert_title_for(reason, level), f"`{pkg}` gặp sự cố, tool đang xử lý.",
                 pkg=pkg, reason=reason, action=action)
    started = time.time()
    ok = join_map(pkg, hard=hard)
    report_rejoin_result(pkg, ok, started, action)

# ==================== BACKUP / RESTORE DATA TAB ====================
def backup_path(pkg, prev=False):
    return f"{BACKUP_DIR}/{pkg}{'.prev' if prev else ''}.tar"

def backup_size(pkg, prev=False):
    return get_file_size(backup_path(pkg, prev))

def backup_info(pkg):
    """(kích thước byte, thời gian backup) hoặc None nếu tab chưa có backup."""
    size = backup_size(pkg)
    if size <= 0:
        return None
    when = sh(f"stat -c %y '{backup_path(pkg)}'", timeout=5).split(".")[0]
    return size, when

def _tar_rc(out):
    m = re.search(r"__RC__(\d+)", out or "")
    return int(m.group(1)) if m else -1

def backup_tab(pkg, stop_first=False):
    """Backup dữ liệu app (trừ cache) của 1 tab -> BACKUP_DIR/<pkg>.tar, giữ thêm 1 bản cũ (.prev.tar).
    stop_first=True: tắt tab trước để dữ liệu nhất quán. Trả về (ok, thông báo)."""
    if not root_mode():
        return False, "cần quyền root"
    data_dir = f"/data/data/{pkg}"
    if "1" not in sh(f"[ -d {data_dir} ] && echo 1", timeout=5):
        return False, "không thấy thư mục dữ liệu của tab"
    if stop_first:
        close_game(pkg)
    entries = [e.strip() for e in sh(f"ls -A {data_dir}", timeout=8).splitlines()]
    entries = [e for e in entries if e and e not in BACKUP_EXCLUDE]
    if not entries:
        return False, "dữ liệu tab đang trống"
    names = " ".join(shlex.quote(e) for e in entries)
    tmp, cur, prev = f"{BACKUP_DIR}/{pkg}.tmp", backup_path(pkg), backup_path(pkg, prev=True)
    sh(f"mkdir -p {BACKUP_DIR} && rm -f {shlex.quote(tmp)}", timeout=8)
    out = sh(f"sync; cd {data_dir} && tar -cf {shlex.quote(tmp)} {names} 2>&1; echo __RC__$?", timeout=300)
    # rc 1 = có file đổi trong lúc đọc (tab đang chạy) -> vẫn chấp nhận
    if _tar_rc(out) not in (0, 1) or get_file_size(tmp) <= 0:
        sh(f"rm -f {shlex.quote(tmp)}", timeout=8)
        return False, "tar lỗi (thiếu dung lượng hoặc không ghi được vào /sdcard)"
    sh(f"[ -f {shlex.quote(cur)} ] && mv -f {shlex.quote(cur)} {shlex.quote(prev)}; mv -f {shlex.quote(tmp)} {shlex.quote(cur)}", timeout=15)
    size = backup_size(pkg)
    if size <= 0:
        return False, "không lưu được file backup"
    return True, f"{round(size / 1024 / 1024, 1)} MB"

def restore_tab(pkg, prev=False, clear_first=True):
    """Khôi phục dữ liệu tab từ backup (tab sẽ bị tắt). clear_first=True: pm clear trước cho sạch file cũ rồi mới giải nén.
    Trả về (ok, thông báo)."""
    if not root_mode():
        return False, "cần quyền root"
    src = backup_path(pkg, prev)
    if get_file_size(src) <= 0:
        return False, "chưa có bản backup"
    data_dir = f"/data/data/{pkg}"
    close_game(pkg)
    owner = sh(f"stat -c %u:%g {data_dir}", timeout=5).strip()
    if clear_first:
        sh(f"pm clear {pkg}", timeout=30)
        owner = sh(f"stat -c %u:%g {data_dir}", timeout=5).strip() or owner
    if not re.fullmatch(r"\d+:\d+", owner):
        return False, "không đọc được uid của app"
    out = sh(f"tar -xf {shlex.quote(src)} -C {data_dir} 2>&1; echo __RC__$?", timeout=300)
    if _tar_rc(out) not in (0, 1):
        return False, "giải nén backup lỗi"
    sh(f"chown -R {owner} {data_dir}", timeout=60)          # đúng chủ sở hữu trước
    sh(f"restorecon -R {data_dir} 2>/dev/null", timeout=60)  # rồi mới gán lại nhãn SELinux
    return True, "đã khôi phục dữ liệu"

def should_auto_backup(pkg):
    """Chỉ backup tab đã vào map ổn định, đang có log mới (không backup trạng thái treo/lỗi)."""
    if not (AUTO_BACKUP and root_mode()) or pkg in NEEDS_LOGIN:
        return False
    now = time.time()
    joined = JOINED_AT.get(pkg)
    if not joined or now - joined < BACKUP_STABLE_SECONDS:
        return False
    if LOG_SOURCE_WORKS and now - LAST_ACTIVITY.get(pkg, 0) > 120:
        return False
    return now - LAST_BACKUP.get(pkg, 0) >= BACKUP_INTERVAL_MIN * 60

# ==================== AUTO CLEAR DATA / KHÔI PHỤC TAB KẸT ====================
def is_tab_frozen(pkg):
    """Tab còn tiến trình nhưng không có log mới quá FREEZE_TIMEOUT_MIN phút = treo cứng.
    Chỉ kết luận khi đã đọc được log của ít nhất 1 tab (tránh xóa nhầm khi máy không đọc được log)."""
    if not (AUTO_CLEAR_DATA and LOG_SOURCE_WORKS):
        return False
    if not is_app_running(pkg):
        return False   # tab đã chết thì cơ chế rejoin lo
    last = LAST_ACTIVITY.get(pkg)
    if last is None:
        LAST_ACTIVITY[pkg] = time.time()
        return False
    return (time.time() - last) >= FREEZE_TIMEOUT_MIN * 60

def recover_frozen_tab(pkg):
    """Tab treo cứng: pm clear -> khôi phục backup (giữ login) -> mở lại vào Map.
    Chỉ xóa data khi tab ĐÃ CÓ backup; chưa có backup / vừa xóa gần đây thì chỉ tắt hẳn rồi mở lại (không mất login)."""
    now = time.time()
    in_cooldown = (now - LAST_CLEAR.get(pkg, 0)) < CLEAR_COOLDOWN_SEC
    has_backup = bool(root_mode()) and (backup_size(pkg) > 0 or backup_size(pkg, prev=True) > 0)
    reason = f"Tab treo hơn {FREEZE_TIMEOUT_MIN} phút không có log"
    REJOIN_COUNT[pkg] = REJOIN_COUNT.get(pkg, 0) + 1
    started = time.time()

    if has_backup and not in_cooldown:
        action = "Xóa data (pm clear) → khôi phục backup → mở lại vào Map"
        print(f"\033[1;31m[!] {pkg} treo > {FREEZE_TIMEOUT_MIN} phút không có log! Xóa data (pm clear) → khôi phục backup → mở lại...\033[0m")
        notify_async("critical", "Tab treo cứng", f"`{pkg}` treo, tool đang khôi phục.", pkg=pkg, reason=reason, action=action)
        LAST_CLEAR[pkg] = now
        ok, msg = restore_tab(pkg, prev=False)
        if not ok and backup_size(pkg, prev=True) > 0:
            ok, msg = restore_tab(pkg, prev=True)
        if ok:
            print(f"\033[1;32m[+] {pkg}: {msg}.\033[0m")
        else:
            NEEDS_LOGIN.add(pkg)
            print(f"\033[1;31m[!] {pkg}: khôi phục lỗi ({msg}). Tab có thể mất login, cần đăng nhập lại.\033[0m")
            notify_async("critical", "Khôi phục backup lỗi", f"`{pkg}` khôi phục backup lỗi, tab có thể đã mất login.",
                         pkg=pkg, reason=msg, action="Cần đăng nhập lại (dùng mục Login Cookie Roblox)")
        joined = join_map(pkg, hard=True)
        report_rejoin_result(pkg, joined, started, action)
        return

    if not root_mode():
        why = "máy không có root"
    elif in_cooldown:
        why = "vừa xóa data gần đây"
    else:
        why = "chưa có backup, tránh mất login"
    action = "Tắt hẳn tab rồi mở lại, không xóa data"
    print(f"\033[1;31m[!] {pkg} treo > {FREEZE_TIMEOUT_MIN} phút không có log ({why}) → chỉ tắt hẳn tab rồi mở lại.\033[0m")
    notify_async("critical", "Tab treo cứng", f"`{pkg}` treo, tool tắt tab và mở lại (không xóa data).",
                 pkg=pkg, reason=f"{reason} ({why})", action=action)
    close_game(pkg)
    joined = join_map(pkg, hard=True)
    report_rejoin_result(pkg, joined, started, action)

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
    """Vào Map lần lượt các tab (>=4 tab: nhóm 3 tab, cách nhau 15s). Tab đã mở sẵn thì chỉ vào Map, không tắt Đa nhiệm.
    Dùng chung cho chế độ 1 và 2 (mỗi tab thử vào Map tối đa LAUNCH_MAX_RETRY lần)."""
    total = len(packages)
    if total >= 4:
        batch_size = 3
        for i in range(0, total, batch_size):
            if stop_start: break
            for idx_b, pkg in enumerate(packages[i:i + batch_size]):
                if stop_start: break
                print(f"\033[1;36m[*] Đang khởi chạy Tab [{i + idx_b + 1}/{total}]: {pkg}\033[0m")
                join_map(pkg)
            if i + batch_size < total and not stop_start:
                print(f"\033[1;33m[*] Chờ 15 giây để mở nhóm tiếp theo...\033[0m")
                if wait_with_stop_check(15): break
    else:
        for idx, pkg in enumerate(packages):
            if stop_start: break
            print(f"\033[1;36m[*] Đang khởi chạy Tab [{idx + 1}/{total}]: {pkg}\033[0m")
            join_map(pkg)
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
    for state in (LOG_STATE, LOGCAT_BASELINE, LAST_ACTIVITY, LAST_CLEAR, LAST_SOFT_JOIN, JOINED_AT, LAST_BACKUP, REJOIN_COUNT):
        state.clear()

    print(f"\033[1;37m[+] PAIN TOOL REJOIN VIP ({VERSION}) Đang chạy...\033[0m")
    print(f"\033[1;32m[*] Đã tìm thấy {len(packages)} bản clone ({PACKAGE_PREFIX}).\033[0m")
    print(f"\033[1;32m[*] Cơ chế Rejoin: {get_rejoin_mode_str()}\033[0m")
    if not TARGET_LINK:
        print("\033[1;31m[!] Chưa chọn game (Set up > Chọn game): tool chỉ mở app, không vào Map.\033[0m")
    if (AUTO_CLEAR_DATA or AUTO_BACKUP) and not root_mode():
        print("\033[1;31m[!] Máy không có root: Auto Clear Data / Auto Backup không hoạt động.\033[0m")
    else:
        if AUTO_CLEAR_DATA:
            print(f"\033[1;32m[*] Auto Clear Data: BẬT (treo > {FREEZE_TIMEOUT_MIN} phút không có log).\033[0m")
        if AUTO_BACKUP:
            print(f"\033[1;32m[*] Auto Backup: BẬT (mỗi {BACKUP_INTERVAL_MIN} phút, lưu ở {BACKUP_DIR}).\033[0m")
    if WEBHOOK_URL:
        print("\033[1;32m[*] Cảnh báo Discord: BẬT  \033[1;31m● Đỏ\033[0m Kick/Crash  \033[1;33m● Vàng\033[0m Lobby  \033[1;32m● Xanh\033[0m Rejoin thành công")
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
    last_packages_time = time.time()
    last_freeze_check = 0
    last_backup_check = time.time()

    try:
        while not stop_start:
            current_time = time.time()
            elapsed_minutes = (current_time - start_time) / 60.0
            if current_time - last_packages_time >= 30:
                packages = get_all_packages()
                last_packages_time = current_time

            if (current_time - last_cleanup_time) >= 600:
                print("\033[1;32m[*] Tiến hành tự động dọn dẹp RAM và cache định kỳ...\033[0m")
                for pkg in packages:
                    sh(f"rm -rf /data/data/{pkg}/cache/*")
                sh("sync && echo 3 > /proc/sys/vm/drop_caches")
                last_cleanup_time = time.time()

            if AUTO_REJOIN_MODE == 1:
                # Chế độ 1: dò lỗi (mã lỗi / kick / crash / mất tiến trình) rồi vào lại Map
                for pkg in packages:
                    if stop_start: break
                    reason = detect_problem(pkg)
                    if reason:
                        recover_tab(pkg, reason)

            elif AUTO_REJOIN_MODE == 2:
                # Chế độ 2: hết chu kỳ thì vào lại Map (mỗi tab thử tối đa 3 lần), tab đang mở thì không tắt Đa nhiệm.
                # Không có tự động rejoin khi crash ở chế độ này.
                if elapsed_minutes >= DELAY_REJOIN_MINUTES:
                    print(f"\033[1;33m[*] Chu kỳ {DELAY_REJOIN_MINUTES}p hoàn tất. Vào lại Map toàn bộ tab...\033[0m")
                    launch_all(packages)
                    start_time = time.time()

            # Auto Clear Data / khôi phục tab kẹt (chạy ở cả 2 chế độ), kiểm tra mỗi 10 giây
            if AUTO_CLEAR_DATA and not stop_start and (time.time() - last_freeze_check) >= 10:
                last_freeze_check = time.time()
                for pkg in packages:
                    if stop_start: break
                    if AUTO_REJOIN_MODE == 2:
                        collect_new_logs(pkg)   # chế độ 1 đã đọc log trong detect_problem
                    if is_tab_frozen(pkg):
                        recover_frozen_tab(pkg)

            # Auto Backup định kỳ: mỗi lượt chỉ backup 1 tab để không chặn vòng lặp lâu
            if AUTO_BACKUP and not stop_start and (time.time() - last_backup_check) >= 60:
                last_backup_check = time.time()
                for pkg in packages:
                    if stop_start: break
                    if is_app_running(pkg) and should_auto_backup(pkg):
                        ok, msg = backup_tab(pkg)
                        LAST_BACKUP[pkg] = time.time()   # lỗi thì 30 phút sau mới thử lại, không spam
                        color = "\033[1;32m[+]" if ok else "\033[1;31m[!]"
                        print(f"{color} Auto Backup {pkg}: {msg}\033[0m")
                        break

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

    w = ui_width()
    inner = w - 4
    lw = 12
    vw = inner - lw - 1
    info = get_system_info()
    n_tabs = len(list_installed_packages())
    rooted = bool(root_mode())

    try:
        bat = int(str(info["battery"]).strip("%"))
        bat_col = C.GRN if bat >= 50 else (C.YEL if bat >= 20 else C.RED)
    except Exception:
        bat_col = C.WHT

    def on_off(flag, text_on):
        return f"{dot(True)} {C.WHT}{text_on}{C.R}" if flag else f"{dot(False)} {C.GRY}Tắt{C.R}"

    root_txt = f"{dot(True)} {C.WHT}Root{C.R}" if rooted else f"{dot(False)} {C.RED}Không root{C.R}"
    if WEBHOOK_URL:
        webhook_txt = f"{dot(True)} {C.WHT}Đã cài{C.R}  {C.RED}●{C.YEL}●{C.GRN}●{C.R}"
    else:
        webhook_txt = f"{dot(None)} {C.GRY}Chưa cài{C.R}"

    print(box_top(w))
    print(box_row(f"{C.WHT}PAIN TOOL REJOIN VIP{C.R}", w, "center"))
    print(box_row(f"{C.GRY}by{C.R} {C.YEL}PAIN GAMER{C.R} {C.GRY}·{C.R} {C.LPUR}{VERSION}{C.R}", w, "center"))
    print(box_row(f"{C.CYN}{clip(DISCORD_LINK, inner)}{C.R}", w, "center"))
    print(box_sep(w))
    print(box_row(f"{C.PUR}▸ THIẾT BỊ{C.R}", w))
    print(box_kv("Máy", clip(f"{info['model']} · Android {info['android']}", vw), w, lw))
    print(box_kv("Chip / RAM", clip(f"{info['cpu']} · {info['ram']}", vw), w, lw))
    print(box_kv("Pin / Root", f"{bat_col}{info['battery']}{C.R} {C.GRY}·{C.R} {root_txt}", w, lw))
    print(box_sep(w))
    print(box_row(f"{C.PUR}▸ TRẠNG THÁI{C.R}", w))
    print(box_kv("Game", f"{dot(bool(TARGET_LINK) or None)} {C.WHT}{clip(SELECTED_GAME_NAME, vw - 2)}{C.R}", w, lw))
    print(box_kv("Package", f"{dot(n_tabs > 0)} {C.WHT}{clip(PACKAGE_PREFIX, vw - 12)}{C.R} {C.GRY}({n_tabs} tab){C.R}", w, lw))
    print(box_kv("Rejoin", f"{dot(True)} {C.WHT}{clip(get_rejoin_mode_str(), vw - 2)}{C.R}", w, lw))
    print(box_kv("Clear Data", on_off(AUTO_CLEAR_DATA, f"Bật (treo > {FREEZE_TIMEOUT_MIN}p)"), w, lw))
    print(box_kv("Auto Backup", on_off(AUTO_BACKUP, f"Bật (mỗi {BACKUP_INTERVAL_MIN}p)"), w, lw))
    print(box_kv("Webhook", webhook_txt, w, lw))
    print(box_sep(w))
    print(box_row(f"{C.PUR}▸ MENU{C.R}", w))

    entries = [
        ("1", "Start", "Start"),
        ("2", "Set up", "Set up"),
        ("3", "Package prefix", "Package prefix"),
        ("4", "Change ID", "Change id"),
        ("5", "Set Webhook URL", "Set Webhook URL"),
        ("6", "Xóa cache", "Xóa cache"),
        ("7", "Import auto execute", "Import auto execute"),
        ("8", "Mở tab, không vào map", "Mở tab clone (không vào map)"),
        ("9", "Send Text", "SEND TEXT"),
        ("10", "Backup / Restore", "Backup / Restore data tab"),
        ("11", "Login Cookie Roblox", "Login Cookie Roblox"),
        ("0", "Exit", "Exit"),
    ]

    def cell(entry, width, short):
        k, s, l = entry
        label = s if short else l
        kc = C.RED if k == "0" else (C.GRN if k == "1" else C.LPUR)
        lc = C.RED if k == "0" else C.WHT
        return f"{kc}{pad('[' + k + ']', 4)}{C.R} {lc}{clip(label, width - 5)}{C.R}"

    if w >= 56:
        colw = inner // 2
        for i in range(6):
            print(box_row(pad(cell(entries[i], colw, True), colw) + cell(entries[i + 6], inner - colw, True), w))
    else:
        for e in entries:
            print(box_row(cell(e, inner, False), w))
    print(box_bot(w))

# ==================== MENU SET UP / BACKUP ====================
def setup_auto_rejoin():
    global AUTO_REJOIN_MODE, DELAY_REJOIN_MINUTES
    clear_screen()
    section_title("SET UP AUTO REJOIN")
    print("\033[1;37m1. Auto rejoin vang/crash\033[0m")
    print("\033[1;37m2. Delay rejoin (Vào lại Map theo chu kỳ)\033[0m")
    mode = input("Chọn cơ chế [1/2]: ").strip()
    if mode == "1":
        AUTO_REJOIN_MODE = 1
        print("\033[1;32m[+] Đã chọn Auto rejoin vang/crash!\033[0m")
    elif mode == "2":
        AUTO_REJOIN_MODE = 2
        mins = input("Nhập thời gian chu kỳ (phút): ").strip()
        if mins.isdigit() and int(mins) > 0:
            DELAY_REJOIN_MINUTES = int(mins)
            print(f"\033[1;32m[+] Đã cài Delay Rejoin {DELAY_REJOIN_MINUTES} phút!\033[0m")
    time.sleep(1.5)

def setup_auto_clear():
    global AUTO_CLEAR_DATA, FREEZE_TIMEOUT_MIN
    clear_screen()
    section_title("AUTO CLEAR DATA / KHÔI PHỤC TAB KẸT")
    print(f"Trạng thái: {'BẬT' if AUTO_CLEAR_DATA else 'TẮT'} | Ngưỡng treo: {FREEZE_TIMEOUT_MIN} phút")
    print("Tab không có log mới quá ngưỡng -> xóa data (pm clear) -> khôi phục backup (giữ login) -> mở lại vào Map.")
    print("Chỉ xóa data khi tab đã có backup; chưa có backup thì chỉ tắt hẳn tab rồi mở lại.")
    print("\033[1;37m1. Bật\033[0m")
    print("\033[1;37m2. Tắt\033[0m")
    print("\033[1;37m3. Đổi ngưỡng treo (3-5 phút)\033[0m")
    print("\033[1;32m0. Quay lại\033[0m")
    sub = input("Chọn: ").strip()
    if sub == "1":
        AUTO_CLEAR_DATA = True
    elif sub == "2":
        AUTO_CLEAR_DATA = False
    elif sub == "3":
        mins = input("Nhập số phút (3-5): ").strip()
        if mins.isdigit() and 3 <= int(mins) <= 5:
            FREEZE_TIMEOUT_MIN = int(mins)
        else:
            print("\033[1;31m[!] Chỉ nhận 3, 4 hoặc 5 phút.\033[0m")
    else:
        return
    save_config_file()
    print(f"\033[1;32m[+] Auto Clear Data: {'BẬT' if AUTO_CLEAR_DATA else 'TẮT'} (ngưỡng {FREEZE_TIMEOUT_MIN} phút)\033[0m")
    time.sleep(1.5)

def setup_auto_backup():
    global AUTO_BACKUP
    clear_screen()
    section_title("AUTO BACKUP DATA TAB")
    print(f"Trạng thái: {'BẬT' if AUTO_BACKUP else 'TẮT'} | Chu kỳ: {BACKUP_INTERVAL_MIN} phút | Thư mục: {BACKUP_DIR}")
    print("Tự backup dữ liệu (đăng nhập, cài đặt) của các tab đang chạy ổn định. Cần root.")
    print("\033[1;37m1. Bật\033[0m")
    print("\033[1;37m2. Tắt\033[0m")
    print("\033[1;32m0. Quay lại\033[0m")
    sub = input("Chọn: ").strip()
    if sub == "1":
        AUTO_BACKUP = True
    elif sub == "2":
        AUTO_BACKUP = False
    else:
        return
    save_config_file()
    print(f"\033[1;32m[+] Auto Backup: {'BẬT' if AUTO_BACKUP else 'TẮT'}\033[0m")
    time.sleep(1.5)

def pick_package(packages):
    for i, p in enumerate(packages, 1):
        info = backup_info(p)
        status = f"đã backup lúc {info[1]}" if info else "chưa có backup"
        print(f"\033[1;37m{i}. {p}\033[0m ({status})")
    c = input("Chọn tab (số, 0 để hủy): ").strip()
    if c.isdigit() and 1 <= int(c) <= len(packages):
        return packages[int(c) - 1]
    return None

def backup_menu():
    while True:
        clear_screen()
        section_title("BACKUP / RESTORE DATA TAB")
        print("\033[1;37m1. Backup tất cả tab\033[0m")
        print("\033[1;37m2. Restore tất cả tab\033[0m")
        print("\033[1;37m3. Backup 1 tab\033[0m")
        print("\033[1;37m4. Restore 1 tab\033[0m")
        print("\033[1;37m5. Xem danh sách backup\033[0m")
        print("\033[1;32m0. Quay lại menu chính\033[0m")
        sub = input("Chọn: ").strip()
        if sub == "0":
            return
        if sub not in ("1", "2", "3", "4", "5"):
            continue
        if not root_mode():
            print("\033[1;31m[!] Backup / Restore cần quyền root.\033[0m")
            time.sleep(2)
            continue
        packages = get_all_packages()

        if sub == "5":
            for p in packages:
                info = backup_info(p)
                if info:
                    prev = " + bản cũ" if backup_size(p, prev=True) > 0 else ""
                    print(f"\033[1;32m[+] {p}: {round(info[0] / 1024 / 1024, 1)} MB, {info[1]}{prev}\033[0m")
                else:
                    print(f"\033[1;33m[-] {p}: chưa có backup\033[0m")
            print(f"Thư mục: {BACKUP_DIR}")
            input("Enter để quay lại...")

        elif sub in ("1", "3"):
            targets = packages
            if sub == "3":
                pkg = pick_package(packages)
                if not pkg:
                    continue
                targets = [pkg]
            if input("Sẽ tắt tab để backup dữ liệu nhất quán. Tiếp tục? (y/n): ").strip().lower() != "y":
                continue
            for p in targets:
                print(f"\033[1;33m[*] Đang backup {p}...\033[0m")
                ok, msg = backup_tab(p, stop_first=True)
                if ok:
                    NEEDS_LOGIN.discard(p)
                print(f"\033[1;32m[+] {p}: {msg}\033[0m" if ok else f"\033[1;31m[!] {p}: {msg}\033[0m")
            input("Xong. Enter để quay lại...")

        elif sub in ("2", "4"):
            targets = packages
            if sub == "4":
                pkg = pick_package(packages)
                if not pkg:
                    continue
                targets = [pkg]
            if input("Sẽ xóa data hiện tại của tab và thay bằng bản backup. Tiếp tục? (y/n): ").strip().lower() != "y":
                continue
            for p in targets:
                use_prev = False
                if sub == "4" and backup_size(p, prev=True) > 0:
                    use_prev = input("Dùng bản backup cũ hơn? (y = bản cũ, Enter = bản mới nhất): ").strip().lower() == "y"
                print(f"\033[1;33m[*] Đang restore {p}...\033[0m")
                ok, msg = restore_tab(p, prev=use_prev)
                if ok:
                    NEEDS_LOGIN.discard(p)
                print(f"\033[1;32m[+] {p}: {msg}\033[0m" if ok else f"\033[1;31m[!] {p}: {msg}\033[0m")
            print("Mở lại tab bằng Start hoặc mục [8].")
            input("Xong. Enter để quay lại...")

# ==================== LOGIN COOKIE ROBLOX ====================
# Cách hoạt động (cần root): ghi cookie .ROBLOSECURITY thẳng vào kho cookie WebView của tab
# (/data/data/<package>/app_webview/Default/Cookies) khi tab đang tắt. Mở tab lên là đã đăng nhập.
# Cookie KHÔNG được lưu ra file, KHÔNG gửi lên server/webhook nào của tool; chỉ gửi tới chính Roblox để kiểm tra còn sống.
COOKIE_NAME = ".ROBLOSECURITY"
COOKIE_HOST = ".roblox.com"
COOKIE_DB_PATHS = ("app_webview/Default/Cookies", "app_webview/Cookies")
COOKIE_FILE_DEFAULT = "/sdcard/cookie.txt"
PKG_NAME_RX = re.compile(r"[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+")

def normalize_cookie(raw):
    """Nhận nhiều kiểu dán: cookie trần, '.ROBLOSECURITY=...', 'user:pass:cookie', có nháy, dính khoảng trắng... -> giá trị cookie sạch."""
    s = (raw or "").strip().strip("\"'").strip()
    i = s.find("_|WARNING")
    if i != -1:
        s = s[i:]
    else:
        m = re.search(r"\.ROBLOSECURITY[\s=]+([^;\s]+)", s, re.I)
        if m:
            s = m.group(1)
    s = s.split(";")[0]
    return "".join(s.split()).strip("\"'")

def looks_like_cookie(c):
    return len(c) >= 100 and c.isascii()

def cookie_preview(c):
    tok = c.split("|_", 1)[-1]
    return f"_|WARNING…|_{tok[:6]}…{tok[-4:]}"

def read_text_any(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        pass
    if root_mode():
        return sh(f"cat {shlex.quote(path)}", timeout=10)
    return ""

def roblox_check_cookie(cookie):
    """Gọi API Roblox (chỉ đọc) xem cookie còn sống không.
    Trả về (True, {id,name,displayName}) / (False, lý do) nếu cookie chết / (None, lý do) nếu chưa xác minh được (mạng, rate limit)."""
    out = run_cmd([
        "curl", "-s", "-m", "15", "-w", "\n%{http_code}",
        "-H", f"Cookie: {COOKIE_NAME}={cookie}",
        "-H", "User-Agent: Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36",
        "https://users.roblox.com/v1/users/authenticated",
    ], timeout=25)
    if not out:
        return None, "không kết nối được Roblox"
    body, _, code = out.rpartition("\n")
    code = code.strip()
    if code == "200":
        try:
            data = json.loads(body)
            if isinstance(data, dict) and data.get("id"):
                return True, data
        except Exception:
            pass
        return None, "Roblox trả về dữ liệu lạ"
    if code == "401":
        return False, "cookie đã hết hạn hoặc bị đăng xuất (401)"
    return None, f"Roblox trả về mã {code or '?'}"

def find_cookie_db(pkg):
    for rel in COOKIE_DB_PATHS:
        p = f"/data/data/{pkg}/{rel}"
        if "1" in sh(f"[ -f {shlex.quote(p)} ] && echo 1", timeout=5):
            return p
    return None

def ensure_cookie_db(pkg):
    """App chưa từng mở thì chưa có file cookie -> mở app 1 lần cho nó tự tạo rồi tắt."""
    db = find_cookie_db(pkg)
    if db:
        return db
    msg_info(f"{pkg} chưa có dữ liệu WebView, mở app 1 lần để khởi tạo...")
    open_game(pkg, hard=True, enter_map=False)
    for _ in range(15):
        time.sleep(2)
        db = find_cookie_db(pkg)
        if db:
            time.sleep(3)   # cho Chromium ghi xong
            break
    close_game(pkg)
    return db or find_cookie_db(pkg)

def inject_cookie(pkg, cookie):
    """Ghi cookie vào kho cookie WebView của tab (tab sẽ bị tắt). Trả về (ok, thông báo)."""
    if not root_mode():
        return False, "cần quyền root (cookie nằm trong dữ liệu riêng của app)"
    try:
        import sqlite3
    except Exception:
        return False, "Python thiếu module sqlite3"
    q = shlex.quote
    data_dir = f"/data/data/{pkg}"
    if "1" not in sh(f"[ -d {data_dir} ] && echo 1", timeout=5):
        return False, "không thấy thư mục dữ liệu của tab (sai package?)"
    close_game(pkg)
    db = ensure_cookie_db(pkg)
    if not db:
        return False, "app chưa tạo file cookie, hãy mở tab bằng tay 1 lần rồi thử lại"

    work = os.path.join(os.path.expanduser("~"), ".pain_cookie_tmp")
    local = os.path.join(work, "Cookies")
    try:
        shutil.rmtree(work, ignore_errors=True)
        os.makedirs(work, exist_ok=True)
        os.chmod(work, 0o700)
        # Tạo file rỗng bằng quyền của Python, root chỉ ghi nội dung vào (không đổi chủ sở hữu / nhãn SELinux)
        open(local, "wb").close()
        sh(f"cat {q(db)} > {q(local)}", timeout=15)
        if os.path.getsize(local) <= 0:
            return False, "không đọc được file cookie của app"
        if "1" in sh(f"[ -f {q(db + '-journal')} ] && echo 1", timeout=5):
            open(local + "-journal", "wb").close()
            sh(f"cat {q(db + '-journal')} > {q(local + '-journal')}", timeout=15)

        con = sqlite3.connect(local, timeout=10)
        try:
            cur = con.cursor()
            cols = cur.execute("PRAGMA table_info(cookies)").fetchall()
            if not cols:
                return False, "file cookie không đúng định dạng (không có bảng cookies)"
            now_c = int((time.time() + 11644473600) * 1000000)   # giờ Chromium: micro giây từ 1601
            exp_c = now_c + 300 * 86400 * 1000000
            known = {
                "creation_utc": now_c, "host_key": COOKIE_HOST, "top_frame_site_key": "", "name": COOKIE_NAME,
                "value": cookie, "encrypted_value": b"", "path": "/", "expires_utc": exp_c,
                "is_secure": 1, "is_httponly": 1, "last_access_utc": now_c, "has_expires": 1, "is_persistent": 1,
                "priority": 1, "samesite": -1, "source_scheme": 2, "source_port": 443, "is_same_party": 0,
                "last_update_utc": now_c, "source_type": 0, "has_cross_site_ancestor": 0,
            }
            row = {}
            for _cid, name, ctype, notnull, dflt, _pk in cols:
                if name in known:
                    row[name] = known[name]
                elif notnull and dflt is None:      # cột lạ của bản Chromium khác: điền giá trị rỗng cho khỏi lỗi NOT NULL
                    t = (ctype or "").upper()
                    row[name] = b"" if "BLOB" in t else ("" if ("CHAR" in t or "TEXT" in t) else 0)
            cur.execute("DELETE FROM cookies WHERE host_key LIKE '%roblox.com' AND name IN (?, 'GuestData')", (COOKIE_NAME,))
            keys = list(row)
            cur.execute(
                f"INSERT INTO cookies ({','.join(chr(34) + k + chr(34) for k in keys)}) VALUES ({','.join('?' * len(keys))})",
                [row[k] for k in keys])
            con.commit()
            n = cur.execute("SELECT COUNT(*) FROM cookies WHERE name=? AND value=?", (COOKIE_NAME, cookie)).fetchone()[0]
            if n != 1:
                return False, "ghi cookie vào database không thành công"
            if cur.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                return False, "database cookie bị lỗi sau khi ghi, đã hủy (dữ liệu app giữ nguyên)"
        finally:
            con.close()

        # Ghi đè tại chỗ: giữ nguyên chủ sở hữu, quyền và nhãn SELinux của file gốc
        sh(f"cat {q(local)} > {q(db)}", timeout=15)
        sh(f"rm -f {q(db + '-journal')} {q(db + '-wal')} {q(db + '-shm')}", timeout=8)
        if get_file_size(db) != os.path.getsize(local):
            return False, "ghi lại file cookie chưa trọn vẹn, hãy thử lại"
        return True, "đã ghi cookie vào tab"
    except Exception as e:
        return False, f"lỗi ghi cookie: {e}"
    finally:
        shutil.rmtree(work, ignore_errors=True)

def pick_login_package():
    """Hỏi package name cần đăng nhập (gõ tên đầy đủ hoặc gõ số trong danh sách). Enter trống = bỏ qua."""
    pkgs = list_installed_packages()
    print()
    if pkgs:
        print(f" {C.GRY}Package tìm thấy ({PACKAGE_PREFIX}):{C.R}")
        for i, p in enumerate(pkgs, 1):
            acc = ACCOUNTS.get(p)
            tag = f" {C.GRY}← {acc}{C.R}" if acc else ""
            print(f"  {C.LPUR}{i:>2}.{C.R} {C.WHT}{p}{C.R}{tag}")
    else:
        msg_err(f"Không thấy package nào khớp '{PACKAGE_PREFIX}' (đổi ở mục [3] nếu clone đặt tên khác).")
    while True:
        raw = ask("Nhập package name cần đăng nhập (Enter để bỏ qua):").strip()
        if not raw:
            return None
        if raw.isdigit():
            n = int(raw)
            if 1 <= n <= len(pkgs):
                return pkgs[n - 1]
            msg_err("Số không hợp lệ.")
            continue
        if not PKG_NAME_RX.fullmatch(raw):
            msg_err("Package name không hợp lệ (ví dụ: com.roblox.client).")
            continue
        if raw in pkgs or "package:" in sh(f"pm path {raw}", timeout=8):
            return raw
        msg_err(f"Máy chưa cài package '{raw}'.")

def login_one_cookie(cookie, idx, total):
    print()
    head = f"Cookie {idx}/{total}" if total > 1 else "Cookie"
    print(f" {C.PUR}▸ {head}{C.R}  {C.GRY}{cookie_preview(cookie)}{C.R}")
    if not looks_like_cookie(cookie):
        msg_err("Cookie không đúng định dạng (quá ngắn hoặc có ký tự lạ). Hãy copy lại cả chuỗi bắt đầu bằng _|WARNING:")
        return False

    state, res = with_spinner("Đang kiểm tra cookie với Roblox", roblox_check_cookie, cookie)
    name = None
    if state is True:
        name = res.get("name") or None
        msg_ok(f"Cookie hợp lệ → {res.get('displayName') or name} (@{name}, ID {res.get('id')})")
    elif state is False:
        msg_err(f"Cookie không dùng được: {res}")
        return False
    else:
        msg_info(f"Chưa xác minh được cookie ({res}).")
        if ask("Vẫn ghi cookie vào tab? (y/n):").strip().lower() != "y":
            return False

    pkg = pick_login_package()
    if not pkg:
        msg_info("Đã bỏ qua cookie này.")
        return False

    msg_info(f"Đang ghi cookie vào {pkg} (tab sẽ được tắt nếu đang chạy)...")
    ok, msg = inject_cookie(pkg, cookie)
    if not ok:
        msg_err(f"{pkg}: {msg}")
        return False
    NEEDS_LOGIN.discard(pkg)
    if name:
        ACCOUNTS[pkg] = name
        save_config_file()
    msg_ok(f"{pkg}: đăng nhập cookie thành công" + (f" ({name})" if name else "") + ".")

    if ask("Mở tab vào game ngay? (y/n):").strip().lower() == "y":
        if open_game(pkg, hard=True, enter_map=bool(TARGET_LINK)):
            msg_ok("Đã gửi lệnh mở tab.")
            if not TARGET_LINK:
                msg_info("Chưa chọn game nên chỉ mở app (Set up > Chọn game để tự vào Map).")
        else:
            msg_err("Không mở được tab, thử mở bằng tay hoặc mục [8].")
    return True

def cookie_login_menu():
    while True:
        clear_screen()
        section_title("LOGIN COOKIE ROBLOX")
        print(f" {C.GRY}Đăng nhập tài khoản Roblox vào tab clone bằng cookie {COOKIE_NAME}.{C.R}")
        print(f" {C.GRY}Cần root. Cookie chỉ ghi vào máy, không lưu và không gửi đi đâu.{C.R}")
        print()
        print(f" {C.LPUR}[1]{C.R} {C.WHT}Dán cookie trực tiếp{C.R}")
        print(f" {C.LPUR}[2]{C.R} {C.WHT}Đọc từ file{C.R} {C.GRY}(mỗi dòng 1 cookie){C.R}")
        print(f" {C.LPUR}[3]{C.R} {C.WHT}Lấy từ clipboard{C.R} {C.GRY}(cần Termux:API){C.R}")
        print(f" {C.RED}[0] Quay lại{C.R}")
        print()
        sub = ask("Chọn:").strip()
        if sub == "0":
            return
        if sub not in ("1", "2", "3"):
            continue
        if not root_mode():
            msg_err("Máy không có root nên không ghi được cookie vào app.")
            time.sleep(2)
            continue

        if sub == "1":
            print(f" {C.GRY}Dán cookie rồi Enter (nội dung được ẩn khi dán, Enter trống để hủy).{C.R}")
            try:
                raw = getpass.getpass(" › Cookie: ")
            except Exception:
                raw = ask("Cookie:")
            if not raw.strip():
                continue
            raw_list = [raw]
        elif sub == "2":
            path = ask(f"Đường dẫn file (Enter = {COOKIE_FILE_DEFAULT}):").strip() or COOKIE_FILE_DEFAULT
            text = read_text_any(path)
            if not text.strip():
                msg_err(f"Không đọc được file hoặc file trống: {path}")
                time.sleep(2)
                continue
            raw_list = text.splitlines()
        else:
            text = run_cmd(["termux-clipboard-get"], timeout=8)
            if not text.strip():
                msg_err("Không đọc được clipboard. Cần: pkg install termux-api + cài app Termux:API, hoặc dùng cách [1].")
                time.sleep(2.5)
                continue
            raw_list = text.splitlines()

        cookies = []
        for r in raw_list:
            c = normalize_cookie(r)
            if c and c not in cookies:
                cookies.append(c)
        if not cookies:
            msg_err("Không tìm thấy cookie nào để xử lý.")
            time.sleep(2)
            continue

        done = 0
        for i, c in enumerate(cookies, 1):
            if login_one_cookie(c, i, len(cookies)):
                done += 1
        print()
        msg_info(f"Hoàn tất: {done}/{len(cookies)} cookie đã đăng nhập.")
        ask("Enter để quay lại...")

if __name__ == "__main__":
    load_saved_config()
    authenticate()
    while True:
        show_banner()
        choice = ask("Chọn chức năng [0-11]:").strip()
        if choice == "1":
            start_tool()
        elif choice == "2":
            while True:
                clear_screen()
                section_title("SET UP")
                print("\033[1;37m1. Set up auto rejoin\033[0m")
                print("\033[1;37m2. Chọn game\033[0m")
                print(f"\033[1;37m3. Auto Clear Data / Khôi phục tab kẹt [{'Bật' if AUTO_CLEAR_DATA else 'Tắt'}]\033[0m")
                print(f"\033[1;37m4. Auto Backup data tab [{'Bật' if AUTO_BACKUP else 'Tắt'}]\033[0m")
                print("\033[1;32m0. Quay lại menu chính\033[0m")
                sub = input("Chọn: ").strip()
                if sub == "1":
                    setup_auto_rejoin()
                elif sub == "2":
                    clear_screen()
                    section_title("CHỌN GAME")
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
                elif sub == "3":
                    setup_auto_clear()
                elif sub == "4":
                    setup_auto_backup()
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
            sh(f"settings put secure android_id {new_id}")
            print(f"\033[1;32m[+] Đã yêu cầu đổi ID thành: {new_id}\033[0m")
            time.sleep(2)
        elif choice == "5":
            clear_screen()
            section_title("SET WEBHOOK URL")
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
            # Chỉ xóa cache (không pm clear) nên không mất đăng nhập. Xóa hẳn data: dùng Backup/Restore hoặc Auto Clear Data.
            for pkg in packages:
                sh(f"rm -rf /data/data/{pkg}/cache/* /data/data/{pkg}/code_cache/*")
            sh("sync && echo 3 > /proc/sys/vm/drop_caches")
            print("\033[1;32m[+] Đã xóa cache và dọn RAM (không xóa dữ liệu đăng nhập)!\033[0m")
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
            print(f"\033[1;32m[*] Đang mở hàng loạt tab (chỉ mở tab, KHÔNG vào Map)...\033[0m")

            def open_tab_only(pkg, label):
                if open_game(pkg, enter_map=False):
                    print(f"\033[1;32m[+] Đã mở package {label}: {pkg}\033[0m")
                else:
                    print(f"\033[1;31m[!] Không mở được package {label}: {pkg}\033[0m")

            if len(found_pkgs) >= 4:
                batch_size = 3
                total_clones = len(found_pkgs)
                for i in range(0, total_clones, batch_size):
                    batch = found_pkgs[i:i + batch_size]
                    for idx_b, pkg in enumerate(batch):
                        open_tab_only(pkg, f"[{i + idx_b + 1}/{total_clones}]")
                    if i + batch_size < total_clones:
                        print(f"\033[1;33m[*] Chờ 15 giây để mở nhóm tiếp theo...\033[0m")
                        time.sleep(15)
            else:
                for idx, pkg in enumerate(found_pkgs):
                    open_tab_only(pkg, "")
                    if idx < len(found_pkgs) - 1:
                        time.sleep(CLONE_LAUNCH_DELAY)
            print("\033[1;32m[+] Hoàn tất mở các tab clone!\033[0m")
            time.sleep(2)
        elif choice == "9":
            handle_send_text()
        elif choice == "0":
            sys.exit(0)
        elif choice == "10":
            backup_menu()
        elif choice == "11":
            cookie_login_menu()
