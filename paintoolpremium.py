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
import signal
import traceback
import select
import struct
import uuid
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # If python-dotenv not installed, manually load .env file
    if os.path.exists('.env'):
        with open('.env', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    os.environ[key.strip()] = val.strip().strip('"').strip("'")

VERSION = "v1.6.5 Beta"

# ==================== GLOBAL CONSTANTS (SERVER_URL / SECRET_KEY) ====================
SERVER_URL = "https://paintool-bot.onrender.com/api/verify"
SECRET_KEY = "PainGamerSecretKey2156#VipTool"
API_URL = SERVER_URL   # alias cũ giữ tương thích

# Online mode flag (không còn bắt buộc phải có requests)
_HAS_REQUESTS = False
try:
    import requests   # chỉ dùng cho những chỗ khác nếu cần; phần xác thực key dùng urllib
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

try:
    import cohere
    _HAS_GROQ = True  # Keep variable name for compatibility
except ImportError:
    _HAS_GROQ = False
LAST_LICENSE_EXPIRES = ""
LAST_LICENSE_REASON = ""
LICENSE_FILE = os.path.join(os.path.expanduser("~"), ".pain_license")
DEVICE_FILE = os.path.join(os.path.expanduser("~"), ".pain_device")
HEARTBEAT_SEC = 600
CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".pain_config.json")
LOG_FILE = os.path.join(os.path.expanduser("~"), ".pain_log.txt")
LOG_MAX_BYTES = 1_000_000

PACKAGE_PREFIX = "com.roblox"
TARGET_LINK = ""
SELECTED_GAME_NAME = "Chưa chọn"
WEBHOOK_URL = ""
DISCORD_UID = ""
SCREENSHOT_PATH = "/sdcard/pain_screenshot.png"

DISCORD_LINK = "https://discord.gg/z7RUNArBuJ"

# ---- COHERE AI Configuration (loaded from environment) ----
GROQ_API_KEY = os.environ.get("COHERE_API_KEY", "")  # Load from env var
GROQ_ENABLED = bool(GROQ_API_KEY)  # Auto-enable if key exists
GROQ_REQUEST_COUNT = 0
GROQ_QUOTA_LIMIT = 8500
_GROQ_CLIENT = None  # Now stores Cohere client
GROQ_WEEKLY_ALERTS = []

AUTO_REJOIN_MODE = 1
DELAY_REJOIN_MINUTES = 1
CLONE_LAUNCH_DELAY = 10
stop_start = False
START_UP_TIME = None

# ---- Auto Clear Data / Khôi phục tab kẹt ----
AUTO_CLEAR_DATA = True
FREEZE_TIMEOUT_MIN = 4
CLEAR_COOLDOWN_SEC = 600

# ---- Sao lưu & khôi phục dữ liệu tab ----
AUTO_BACKUP = True
BACKUP_INTERVAL_MIN = 30
BACKUP_STABLE_SECONDS = 120
BACKUP_DIR = "/sdcard/PainBackup"
BACKUP_EXCLUDE = ("cache", "code_cache")

ROBLOX_ERROR_CODES = [str(c) for c in range(258, 291)] + ["517", "522", "523", "524", "529", "610", "769", "770", "771", "772", "773"]

KICK_PHRASES = [
    "you have been kicked", "you were kicked", "kicked from the game", "kicked from this experience",
    "disconnected from game", "unexpected disconnection", "same account launched",
    "lost connection to the game server", "connection attempt failed", "failed to connect to the game",
    "you have been disconnected",
]
CRASH_PHRASES = ["fatal exception", "fatal signal"]

VIP_EXPIRED_PHRASES = [
    "private server is no longer available",
    "private server is invalid",
    "unable to join this private server",
    "this private server is full",
    "private server no longer exists",
    "private server link has expired",
    "invalid or expired private server",
    "the private server you are trying to join no longer exists",
]

GAME_STATUS_CHECK_SEC = 120
GAME_STATUS_RECENT_UPDATE_MIN = 3
GAME_STATUS_PAUSED = False
GAME_STATUS_REASON = ""
LAST_GAME_STATUS = {}
_UNIVERSE_ID_CACHE = {}

LAUNCH_VERIFY_SECONDS = 30
LAUNCH_MAX_RETRY = 3
MAP_LOAD_WAIT = 15
RETRY_COUNTDOWN_SECONDS = 5
LOG_STATE = {}
LOGCAT_BASELINE = {}
LAST_ACTIVITY = {}
LAST_CLEAR = {}
LAST_SOFT_JOIN = {}
JOINED_AT = {}
LAST_BACKUP = {}
NEEDS_LOGIN = set()
LOG_SOURCE_WORKS = False

ALERT_STYLES = {
    "critical": {"color": 0xED4245, "icon": "🔴", "label": "LỖI NẶNG"},
    "lobby":    {"color": 0xFEE75C, "icon": "🟡", "label": "VĂNG LOBBY"},
    "success":  {"color": 0x57F287, "icon": "🟢", "label": "REJOIN THÀNH CÔNG"},
    "stopped":  {"color": 0x95A5A6, "icon": "⚪", "label": "TOOL DỪNG"},
    "aborted":  {"color": 0xE67E22, "icon": "⛔", "label": "TOOL DỪNG BẤT THƯỜNG"},
    "warn":     {"color": 0xFEE75C, "icon": "🟡", "label": "CẢNH BÁO"},
    "restart":  {"color": 0x3498DB, "icon": "🔄", "label": "TỰ ĐỘNG RESTART"},
    "hop":      {"color": 0x9B59B6, "icon": "🔀", "label": "ĐỔI SERVER"},
}
PING_LEVELS = ("critical", "aborted")
ALERT_COOLDOWN_SEC = 20
_ALERT_LAST = {}
REJOIN_COUNT = {}
ACCOUNTS = {}
CYCLE_START = None
_LOG_LOCK = threading.Lock()

# ==================== NHẬT KÝ FILE ====================
def log_event(kind, pkg=None, detail="", code=None, rejoin=None):
    try:
        parts = [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), str(kind).ljust(11), pkg or "-"]
        if code:
            parts.append(f"code={code}")
        if rejoin is not None:
            parts.append(f"rejoin#{rejoin}")
        if detail:
            parts.append(str(detail).replace("\n", " "))
        line = " | ".join(parts)
        with _LOG_LOCK:
            try:
                if os.path.getsize(LOG_FILE) > LOG_MAX_BYTES:
                    with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
                        tail = f.readlines()[-2000:]
                    with open(LOG_FILE, "w", encoding="utf-8") as f:
                        f.writelines(tail)
            except OSError:
                pass
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception:
        pass

def fmt_duration(sec):
    sec = int(max(0, sec))
    h, r = divmod(sec, 3600)
    m, sc = divmod(r, 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{sc:02d}s"
    return f"{sc}s"

def tab_state(pkg):
    if not is_app_running(pkg):
        return "Đã tắt", False
    if not is_app_in_foreground(pkg):
        return "Lobby", None
    if pkg in JOINED_AT:
        return "Trong map", True
    return "Đang vào", None

def read_app_version(pkg):
    out = sh(f"dumpsys package {shlex.quote(pkg)} 2>/dev/null | grep -m1 versionName", timeout=10)
    m = re.search(r"versionName=(\S+)", out or "")
    return m.group(1) if m else None

def check_app_versions(packages):
    changed = False
    for pkg in packages:
        v = read_app_version(pkg)
        if not v:
            continue
        old = ROBLOX_VERSIONS.get(pkg)
        if old is None:
            ROBLOX_VERSIONS[pkg] = v
            changed = True
        elif old != v:
            ROBLOX_VERSIONS[pkg] = v
            changed = True
            log_event("APP_UPDATE", pkg, f"Roblox {old} → {v}")
            notify_async("warn", "Roblox đã cập nhật",
                         f"`{pkg}`: {old} → {v}. Nếu lỗi mới xuất hiện, hãy kiểm tra sau bản cập nhật này.",
                         pkg=pkg)
    if changed:
        save_config_file()

def print_status_table(packages=None):
    try:
        packages = packages or get_all_packages()
        w = ui_width()
        inner = w - 4
        now = time.time()
        total = fmt_duration(now - START_UP_TIME.timestamp()) if START_UP_TIME else "0s"
        if AUTO_REJOIN_MODE == 2:
            if CYCLE_START:
                left = DELAY_REJOIN_MINUTES * 60 - (now - CYCLE_START)
                nxt = fmt_duration(left) if left > 0 else "đang rejoin..."
            else:
                nxt = "—"
        else:
            nxt = "không theo chu kỳ (dò lỗi liên tục)"
        sw, rw, mw, ew = 11, 3, 7, 8
        nw = max(8, inner - sw - rw - mw - ew - 4)
        states = [(pkg,) + tab_state(pkg) for pkg in packages]
        running = sum(1 for _p, _t, st in states if st is not False)
        print(box_top(w))
        print(box_row(f"{C.WHT}TRẠNG THÁI TAB{C.R}", w, "center"))
        print(box_sep(w))
        print(box_kv("Chạy tổng", f"{C.WHT}{total}{C.R}", w))
        print(box_kv("Cơ chế", f"{C.WHT}{get_rejoin_mode_str()}{C.R}", w))
        print(box_kv("Rejoin kế", f"{C.WHT}{nxt}{C.R}", w))
        if RUN_LIMIT_HOURS and START_UP_TIME:
            left_s = RUN_LIMIT_HOURS * 3600 - (now - START_UP_TIME.timestamp())
            col_left = C.YEL if left_s < 600 else C.WHT
            print(box_kv("Còn lại", f"{col_left}{fmt_duration(max(0, left_s))}{C.R}", w))
        if GAME_STATUS_PAUSED:
            print(box_kv("Game", f"{C.YEL}Tạm dừng rejoin — {clip(GAME_STATUS_REASON, inner - 24)}{C.R}", w))
        if NEXT_AUTO_RESTART and AUTO_RESTART_HOURS:
            rl = NEXT_AUTO_RESTART - now
            print(box_kv("Restart kế", f"{C.WHT}{fmt_duration(rl) if rl > 0 else 'sắp tới'} ({auto_restart_label()}){C.R}", w))
        print(box_kv("Tab chạy", f"{C.WHT}{running}/{len(packages)}{C.R}", w))
        print(box_sep(w))
        print(box_row(f"{C.GRY}{pad('Tab', nw)} {pad('Trạng thái', sw)} {pad('RJ', rw)} {pad('Executor', ew)} {pad('Map', mw)}{C.R}", w))
        for pkg, text, st in states:
            short = pkg[len(PACKAGE_PREFIX):].lstrip(".") if pkg.startswith(PACKAGE_PREFIX) and pkg != PACKAGE_PREFIX else pkg
            if ALIASES.get(pkg):
                short = ALIASES[pkg]
            if ACCOUNTS.get(pkg):
                short = f"{short} ({ACCOUNTS[pkg]})"
            in_map = fmt_duration(now - JOINED_AT[pkg]) if pkg in JOINED_AT and st else "—"
            exe = EXECUTOR_BINDING.get(pkg, "—")
            exe_display = exe if exe in EXECUTOR_NAMES else "—"
            row = (f"{pad(clip(short, nw), nw)} {pad(dot(st) + ' ' + clip(text, sw - 2), sw)} "
                   f"{pad(str(REJOIN_COUNT.get(pkg, 0)), rw)} {pad(exe_display, ew)} {pad(in_map, mw)}")
            print(box_row(row, w))
        print(box_bot(w))
    except Exception as e:
        print(f"\033[1;31m[!] Không hiển thị được bảng trạng thái: {e}\033[0m")

def notify_tool_stopped(reason, unexpected=False):
    if not WEBHOOK_URL:
        return
    up = fmt_duration(time.time() - START_UP_TIME.timestamp()) if START_UP_TIME else "?"
    total = sum(REJOIN_COUNT.values())
    print("\033[1;33m[*] Đang gửi cảnh báo dừng tool lên Discord...\033[0m")
    send_detailed_alert("aborted" if unexpected else "stopped", "Tool đã dừng",
                        f"Tool đã dừng sau **{up}** chạy, tổng cộng **{total}** lần rejoin.",
                        reason=reason,
                        action="Cần mở lại tool để tiếp tục treo máy" if unexpected else "Người dùng chủ động dừng, không cần xử lý")

# ---- Cảnh báo RAM thấp ----
LOW_RAM_ALERT = True
LOW_RAM_MB = 500
LOW_RAM_AUTO_CLEAN = True
LOW_RAM_COOLDOWN_SEC = 300
_LOW_RAM_LAST = 0

# ---- Kiểm tra cập nhật ----
UPDATE_URL = "https://paintool-bot.onrender.com/api/version"
UPDATE_INFO = {"latest": None, "status": None}

# ---- Profile & hẹn giờ ----
PROFILES = {}
SCHEDULE = {"start": "", "stop": ""}
SCHED_FIRED = {}
STOP_REASON = ""
RUN_LIMIT_HOURS = 0
QUIET_HOURS = {"enabled": False, "start": "23:00", "end": "07:00"}
STOP_TIMER = {"enabled": False, "hours": 6, "close_apps": False}
MONITOR_ONLY = False
SCREEN_ARCHIVE = {"enabled": False}
ROBLOX_VERSIONS = {}
SHOT_DIR = "/sdcard/Pictures/PainTool"
SHOT_KEEP = 50
_LISTENER_GEN = 0

# ---- Game-specific profiles ----
GAME_PROFILES = {}
PACKAGE_GAMES = {}

# ==================== BAN PATTERN TRACKING ====================
BAN_TRACKER = {
    "error_262_count": 0,
    "error_262_streak": 0,
    "rejoin_fail_count": 0,
    "cookie_change_count": 0,
    "cookie_change_time": [],
    "ban_risk_percent": 0,
    "ban_warning": "",
    "last_reset_time": time.time(),
    "is_paused": False,
    "pause_until": 0
}

# ==================== SELECTED PACKAGES (User Choice) ====================
SELECTED_PACKAGES = []
SELECT_ALL_PACKAGES = True
EXECUTOR_BINDING = {}

def _valid_hhmm(v):
    return isinstance(v, str) and bool(re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v))

# ==================== CẢNH BÁO RAM THẤP ====================
def get_free_ram_mb():
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except Exception:
        pass
    return None

def check_low_ram(packages):
    global _LOW_RAM_LAST
    if not LOW_RAM_ALERT:
        return
    free = get_free_ram_mb()
    if free is None or free >= LOW_RAM_MB:
        return
    now = time.time()
    if now - _LOW_RAM_LAST < LOW_RAM_COOLDOWN_SEC:
        return
    _LOW_RAM_LAST = now
    msg = f"RAM trống chỉ còn {free} MB (ngưỡng {LOW_RAM_MB} MB)."
    print(f"\033[1;33m[!] {msg}\033[0m")
    action = None
    if LOW_RAM_AUTO_CLEAN:
        if root_mode():
            for pkg in packages:
                sh(f"rm -rf /data/data/{pkg}/cache/* /data/data/{pkg}/code_cache/*")
            sh("sync && echo 3 > /proc/sys/vm/drop_caches")
            after = get_free_ram_mb()
            action = f"Đã tự dọn cache và RAM (trống: {free} MB → {after if after is not None else 'N/A'} MB)"
            print(f"\033[1;32m[✓] {action}\033[0m")
        else:
            action = "Không tự dọn được vì máy không có root"
            print(f"\033[1;31m[!] {action}\033[0m")
    log_event("LOW_RAM", detail=f"{free}MB trống" + (f" | {action}" if action else ""))
    notify_async("warn", "RAM thấp", "Máy sắp thiếu RAM, tab có thể bị treo hoặc văng.", reason=msg, action=action)

# ==================== KIỂM TRA CẬP NHẬT ====================
def _parse_ver(v):
    m = re.search(r"(\d+(?:\.\d+)+)", v or "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else None

def fetch_latest_version():
    out = run_cmd(["curl", "-s", "-m", "8", UPDATE_URL], timeout=12)
    if not out or out.lstrip().startswith("<"):
        return None
    try:
        d = json.loads(out)
        v = (d.get("version") or d.get("latest") or "") if isinstance(d, dict) else str(d)
    except Exception:
        v = out.strip().splitlines()[0][:40]
    return v if _parse_ver(v) else None

def update_available():
    cur, new = _parse_ver(VERSION), _parse_ver(UPDATE_INFO.get("latest"))
    return bool(cur and new and new > cur)

def update_status_line():
    st = UPDATE_INFO.get("status")
    if st == "checking":
        return f"{C.YEL}Đang kiểm tra phiên bản...{C.R}"
    if st == "new":
        return f"{C.YEL}Có bản mới {UPDATE_INFO.get('latest')} (đang dùng {VERSION}). Lấy tại Discord.{C.R}"
    if st == "latest":
        return f"{C.GRN}Bạn đang dùng bản mới nhất ({VERSION}).{C.R}"
    if st == "fail":
        return f"{C.GRY}Không kiểm tra được phiên bản (bỏ qua).{C.R}"
    return ""

def check_update_on_launch(hwid):
    UPDATE_INFO["status"] = "checking"
    license_screen(hwid)
    try:
        latest = fetch_latest_version()
    except Exception:
        latest = None
    UPDATE_INFO["latest"] = latest
    if not latest:
        UPDATE_INFO["status"] = "fail"
    elif update_available():
        UPDATE_INFO["status"] = "new"
    else:
        UPDATE_INFO["status"] = "latest"

# ==================== PROFILE ====================
def profile_snapshot():
    return {"target_link": TARGET_LINK, "selected_game_name": SELECTED_GAME_NAME if TARGET_LINK else "",
            "auto_rejoin_mode": AUTO_REJOIN_MODE, "delay_rejoin_minutes": DELAY_REJOIN_MINUTES,
            "package_prefix": PACKAGE_PREFIX}

def apply_profile(p):
    global TARGET_LINK, SELECTED_GAME_NAME, AUTO_REJOIN_MODE, DELAY_REJOIN_MINUTES, PACKAGE_PREFIX
    link = p.get("target_link")
    if isinstance(link, str) and link.strip():
        TARGET_LINK = link.strip()
        name = p.get("selected_game_name")
        SELECTED_GAME_NAME = name.strip() if isinstance(name, str) and name.strip() else (
            f"Game ID: {TARGET_LINK}" if TARGET_LINK.isdigit() else "Server VIP Custom")
    else:
        TARGET_LINK, SELECTED_GAME_NAME = "", "Chưa chọn"
    if p.get("auto_rejoin_mode") in (1, 2) and not isinstance(p.get("auto_rejoin_mode"), bool):
        AUTO_REJOIN_MODE = p["auto_rejoin_mode"]
    d = p.get("delay_rejoin_minutes")
    if isinstance(d, int) and not isinstance(d, bool) and d > 0:
        DELAY_REJOIN_MINUTES = d
    pref = p.get("package_prefix")
    if isinstance(pref, str) and pref.strip():
        PACKAGE_PREFIX = pref.strip()

def profile_summary(p):
    game = p.get("selected_game_name") if p.get("target_link") else "chưa chọn game"
    mode = "Auto rejoin" if p.get("auto_rejoin_mode", 1) == 1 else f"Delay {p.get('delay_rejoin_minutes', DELAY_REJOIN_MINUTES)}p"
    return f"{game or 'Game'} · {mode} · {p.get('package_prefix', PACKAGE_PREFIX)}"

def pick_profile(prompt):
    names = sorted(PROFILES)
    if not names:
        msg_err("Chưa có profile nào. Chọn [1] để lưu cấu hình hiện tại.")
        return None
    for i, n in enumerate(names, 1):
        print(f" {C.LPUR}{i:>2}.{C.R} {C.WHT}{n}{C.R} {C.GRY}({clip(profile_summary(PROFILES[n]), 40)}){C.R}")
    c = input(prompt).strip()
    if c.isdigit() and 1 <= int(c) <= len(names):
        return names[int(c) - 1]
    if c not in ("", "0"):
        msg_err("Lựa chọn không hợp lệ.")
    return None

# ==================== HẸN GIỜ TỰ CHẠY / TỰ DỪNG ====================
def _parse_hhmm(raw):
    m = re.fullmatch(r"\s*(\d{1,2})\s*[:h.]\s*(\d{2})\s*", raw or "")
    if not m:
        return None
    hh, mm = int(m.group(1)), int(m.group(2))
    return f"{hh:02d}:{mm:02d}" if (hh < 24 and mm < 60) else None

def _today_at(hhmm, day_offset=0):
    d = datetime.now().replace(hour=int(hhmm[:2]), minute=int(hhmm[3:]), second=0, microsecond=0)
    return d + timedelta(days=day_offset)

def schedule_start_due():
    hhmm = SCHEDULE.get("start")
    if not _valid_hhmm(hhmm):
        return False
    now = datetime.now()
    t = _today_at(hhmm)
    if t <= now < t + timedelta(minutes=10) and SCHED_FIRED.get("start") != now.date():
        SCHED_FIRED["start"] = now.date()
        return True
    return False

def schedule_stop_due():
    hhmm = SCHEDULE.get("stop")
    if not _valid_hhmm(hhmm) or not START_UP_TIME:
        return False
    now = datetime.now()
    for off in (0, -1):
        t = _today_at(hhmm, off)
        if t <= now < t + timedelta(minutes=60) and START_UP_TIME < t:
            return True
    return False

def ask_main(label):
    print(f" {C.PUR}›{C.R} {C.WHT}{label}{C.R} ", end="", flush=True)
    if not _valid_hhmm(SCHEDULE.get("start")):
        return input()
    while True:
        try:
            ready, _, _ = select.select([sys.stdin], [], [], 1)
        except Exception:
            return input()
        if ready:
            line = sys.stdin.readline()
            if not line:
                raise EOFError
            return line.rstrip("\n")
        if schedule_start_due():
            print()
            msg_info(f"Đến giờ hẹn {SCHEDULE['start']}: tự động Start...")
            log_event("SCHEDULE", detail=f"Tự động Start theo hẹn giờ {SCHEDULE['start']}")
            time.sleep(1)
            return "1"

# ---- Biệt danh, kiểm tra mạng, Low Graphics ----
ALIASES = {}
NET_CHECK = True
GFX_FILE = "GlobalBasicSettings_13.xml"
GFX_LOW = True
GFX_FPS = 30
GFX_AUTO = False
AUTO_RESTART_HOURS = 0
AUTO_RESTART_ACTION = "reset"
NEXT_AUTO_RESTART = None
SCREENSHOT_MIN_GAP_SEC = 60
_LAST_SHOT = 0
EXECUTOR_NAMES = ["Delta", "Codex", "ArceusX", "Fluxus", "Hydrogen", "Valyse", "VegaX", "Krampus", "Evon"]

def tab_name(pkg):
    return ALIASES.get(pkg) or pkg

def tab_label(pkg):
    return f"{ALIASES[pkg]} ({pkg})" if ALIASES.get(pkg) else pkg

# ==================== KIỂM TRA MẠNG TRƯỚC KHI REJOIN ====================
def _rc(cmd, timeout=6):
    try:
        return subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL, timeout=timeout).returncode
    except Exception:
        return -1

def is_online():
    if _rc(["ping", "-c", "1", "-W", "3", "8.8.8.8"], timeout=6) == 0:
        return True
    out = run_cmd(["curl", "-s", "-m", "5", "-o", "/dev/null", "-w", "%{http_code}",
                   "http://connectivitycheck.gstatic.com/generate_204"], timeout=8)
    return out.strip() in ("204", "200")

def wait_for_network(label=""):
    if not NET_CHECK or is_online():
        return False, 0
    t0 = time.time()
    print(f"\033[1;31m[!] Mất Internet (ping 8.8.8.8 thất bại). Tạm dừng rejoin, chờ có mạng lại...\033[0m")
    log_event("NET_DOWN", pkg=label or None, detail="Mất Internet, tạm dừng rejoin")
    last_print = time.time()
    while True:
        if wait_with_stop_check(5):
            return True, int(time.time() - t0)
        if is_online():
            break
        if time.time() - last_print >= 30:
            last_print = time.time()
            print(f"\033[1;33m[*] Vẫn chưa có mạng ({int(time.time() - t0)}s)...\033[0m")
    down = int(time.time() - t0)
    print(f"\033[1;32m[✓] Đã có mạng trở lại sau {down}s. Tiếp tục rejoin.\033[0m")
    log_event("NET_UP", detail=f"Mạng trở lại sau {down}s")
    notify_async("warn", "Mất mạng đã khôi phục", f"Máy mất Internet {down}s, tool đã tạm dừng rejoin và tiếp tục lại.",
                 reason=f"Mất Internet {down}s", action="Đã tạm dừng đếm ngược / mở app cho tới khi có mạng")
    return False, down

# ==================== CLIENT KEY INJECTOR ====================
KEY_AUTO = True
KEY_FILES = {}
KEY_VAULT_DIR = os.path.join(os.path.expanduser("~"), ".pain_keyvault")
KEY_SAVE_INTERVAL_SEC = 600
KEY_MAX_BYTES = 64 * 1024

# ==================== PHÁT HIỆN MÀN HÌNH TRẮNG/ĐEN, GUI ĐỨNG, NOT RESPONDING ====================
WB_DETECT = True
OVERLAY_DETECT = True
SCREEN_CHECK_SEC = 15
SCREEN_GRACE_SEC = 60
WB_CONFIRM_COUNT = 3
WB_UNIFORM_RATIO = 0.995
OVERLAY_FREEZE_SEC = 150
SCREEN_COOLDOWN_SEC = 120
MAP_POLL_SEC = 3
WB_JOIN_CONFIRM = 3
JOIN_MARKERS = ("joining game", "connection accepted", "replicator created", "game join succeeded")
SCREEN_STATE = {}
SCREEN_COOLDOWN = {}
LAUNCHED_AT = {}
ANR_SEEN = {}
_SCREEN_LAST_SWEEP = 0
_FRAME_WARNED = False
SCREEN_REASON_KEYS = ("màn hình trắng", "màn hình đen", "not responding", "overlay")
_FRAME_RX = re.compile(r"(?:mFrame|frame)=\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")

def is_screen_reason(reason):
    low = (reason or "").lower()
    return any(k in low for k in SCREEN_REASON_KEYS)

def sh_bytes(cmd, timeout=15):
    args = ["su", "-c", cmd] if root_mode() == "su" else ["sh", "-c", cmd]
    try:
        return subprocess.run(args, capture_output=True, stdin=subprocess.DEVNULL, timeout=timeout).stdout
    except Exception:
        return b""

# ---------- Key vault ----------
def _app_dir(pkg):
    return f"/data/data/{pkg}"

def _is_app_private(path):
    return path.startswith("/data/data/") or path.startswith("/data/user/")

def _key_dir(pkg):
    return os.path.join(KEY_VAULT_DIR, re.sub(r"[^\w.\-]", "_", pkg))

def _key_slot(path):
    return hashlib.sha1(path.encode("utf-8")).hexdigest()[:12]

def _key_index_path():
    return os.path.join(KEY_VAULT_DIR, "index.json")

def _key_index_load():
    try:
        with open(_key_index_path(), "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}

def _key_index_save(idx):
    os.makedirs(KEY_VAULT_DIR, exist_ok=True)
    os.chmod(KEY_VAULT_DIR, 0o700)
    tmp = _key_index_path() + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _key_index_path())

def key_candidates(pkg):
    q = shlex.quote
    roots = [_app_dir(pkg), f"/sdcard/Android/data/{pkg}"] + [f"/sdcard/{n}" for n in EXECUTOR_NAMES]
    cmd = ("find " + " ".join(q(r) for r in roots) +
           " -maxdepth 5 -type f \\( -iname '*key*' -o -iname '*token*' -o -iname '*license*' \\) -size -64k"
           " ! -iname '*keyboard*' ! -iname '*.log' ! -path '*/cache/*' ! -path '*/code_cache/*'"
           " ! -path '*/app_webview/*' ! -path '*/app_textures/*' 2>/dev/null | head -n 40")
    out = sh(cmd, timeout=25)
    return [x.strip() for x in out.splitlines() if x.strip().startswith("/")]

def key_save(pkg):
    paths = KEY_FILES.get(pkg) or []
    if not paths:
        return 0, 0
    d = _key_dir(pkg)
    os.makedirs(d, exist_ok=True)
    os.chmod(KEY_VAULT_DIR, 0o700)
    os.chmod(d, 0o700)
    idx = _key_index_load()
    entries = idx.setdefault(pkg, {})
    changed = skipped = 0
    for path in paths:
        data = sh_bytes(f"cat {shlex.quote(path)} 2>/dev/null")
        if not data or len(data) > KEY_MAX_BYTES:
            skipped += 1
            continue
        slot = _key_slot(path)
        fp = os.path.join(d, slot + ".bin")
        old = None
        if os.path.exists(fp):
            with open(fp, "rb") as f:
                old = f.read()
        if old == data and path in entries:
            continue
        if old is not None:
            os.replace(fp, fp + ".prev")
        tmp = fp + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, fp)
        meta = sh(f"stat -c '%u:%g %a' {shlex.quote(path)}", timeout=5).split()
        entries[path] = {"slot": slot, "saved": int(time.time()),
                         "owner": meta[0] if len(meta) > 0 else "", "mode": meta[1] if len(meta) > 1 else ""}
        changed += 1
    _key_index_save(idx)
    return changed, skipped

def _key_write(pkg, path, fp, meta):
    q = shlex.quote
    private = _is_app_private(path)
    app_owner = ""
    if private:
        app_owner = sh(f"stat -c %u:%g {q(_app_dir(pkg))}", timeout=5).strip()
        if not re.fullmatch(r"\d+:\d+", app_owner):
            return False
    parent = os.path.dirname(path)
    missing, p = [], parent
    while p and p != "/" and p != _app_dir(pkg) and "1" not in sh(f"[ -d {q(p)} ] && echo 1", timeout=5):
        missing.append(p)
        p = os.path.dirname(p)
    sh(f"mkdir -p {q(parent)}", timeout=8)
    if private:
        for m in missing:
            sh(f"chown {app_owner} {q(m)}; restorecon {q(m)} 2>/dev/null", timeout=8)
    sh(f"cat {q(fp)} > {q(path)}", timeout=15)
    if get_file_size(path) != os.path.getsize(fp):
        return False
    if private:
        sh(f"chown {app_owner} {q(path)}", timeout=8)
        mode = meta.get("mode") or ""
        if re.fullmatch(r"[0-7]{3,4}", mode):
            sh(f"chmod {mode} {q(path)}", timeout=8)
        sh(f"restorecon {q(path)} 2>/dev/null", timeout=8)
    return True

def key_ensure(pkg, force=False):
    if not force and not KEY_AUTO:
        return 0
    entries = _key_index_load().get(pkg) or {}
    if not entries or not root_mode():
        return 0
    n = 0
    for path, meta in entries.items():
        fp = os.path.join(_key_dir(pkg), str(meta.get("slot", "")) + ".bin")
        if not os.path.isfile(fp):
            continue
        if not force and get_file_size(path) > 0:
            continue
        if _key_write(pkg, path, fp, meta):
            n += 1
    if n:
        log_event("KEY", pkg, f"Đã chèn lại {n} file key/token từ vault")
        print(f"\033[1;32m[✓] Key Injector: đã chèn lại {n} file key/token cho {tab_label(pkg)} (không cần nhập key lại).\033[0m")
    return n

def key_ensure_all(packages):
    for pkg in packages:
        if stop_start:
            break
        if KEY_FILES.get(pkg) and not is_app_running(pkg):
            key_ensure(pkg)

def key_autosave(packages):
    now = time.time()
    for pkg in packages:
        if stop_start:
            break
        joined = JOINED_AT.get(pkg)
        if not KEY_FILES.get(pkg) or not joined or now - joined < BACKUP_STABLE_SECONDS or not is_app_running(pkg):
            continue
        try:
            changed, _skipped = key_save(pkg)
        except Exception:
            continue
        if changed:
            log_event("KEY", pkg, f"Đã cập nhật {changed} file key/token trong vault")
            print(f"\033[1;32m[✓] Key Injector: đã lưu / cập nhật {changed} file key cho {tab_label(pkg)}.\033[0m")

def key_label():
    n = sum(len(v) for v in KEY_FILES.values())
    return f"{n} file · {'Bật' if KEY_AUTO else 'Tắt'}" if n else "chưa chọn file"

# ---------- Đọc màn hình ----------
def parse_raw_frame(data):
    if not data or len(data) < 16:
        return None
    w, h, fmt = struct.unpack("<III", data[:12])
    if not (64 <= w <= 8192 and 64 <= h <= 8192) or fmt not in (1, 2):
        return None
    need = w * h * 4
    for hdr in (12, 16):
        if len(data) - hdr == need:
            return (w, h, memoryview(data)[hdr:])
    return None

def capture_frame():
    return parse_raw_frame(sh_bytes("screencap", timeout=20))

def analyze_frame(frame, rect=None, gx=48, gy=80):
    w, h, buf = frame
    l, t, r, b = rect if rect else (0, 0, w, h)
    l, t, r, b = max(0, l), max(0, t), min(w, r), min(h, b)
    if r - l < 64 or b - t < 64:
        return None
    lum = bytearray()
    for j in range(gy):
        y = t + (b - t) * (2 * j + 1) // (2 * gy)
        base = y * w * 4
        for i in range(gx):
            o = base + (l + (r - l) * (2 * i + 1) // (2 * gx)) * 4
            lum.append((buf[o] * 299 + buf[o + 1] * 587 + buf[o + 2] * 114) // 1000)
    n = len(lum)
    med = sorted(lum)[n // 2]
    ratio = sum(1 for v in lum if abs(v - med) <= 8) / n
    kind = "ok"
    if ratio >= WB_UNIFORM_RATIO:
        if med >= 235:
            kind = "white"
        elif med <= 20:
            kind = "black"
    return {"kind": kind, "median": med, "uniform": round(ratio, 4), "fp": hashlib.md5(bytes(lum)).hexdigest()}

def window_snapshot(packages):
    dump = sh("dumpsys window windows", timeout=12)
    if "Window #" not in dump:
        dump = sh("dumpsys window", timeout=12)
    focus = None
    m = re.search(r"mCurrentFocus=Window\{[^}]*?\s([\w.]+)/", dump)
    if m:
        focus = m.group(1)
    anr = set(re.findall(r"Application Not Responding:\s*([\w.]+)", dump))
    rects = {}
    lines = dump.splitlines()
    for i, ln in enumerate(lines):
        if not ln.lstrip().startswith("Window #"):
            continue
        for pkg in packages:
            if pkg in rects or f" {pkg}/" not in ln:
                continue
            for j in range(i + 1, min(i + 80, len(lines))):
                if lines[j].lstrip().startswith("Window #"):
                    break
                mm = _FRAME_RX.search(lines[j])
                if mm:
                    l, t, r, b = (int(x) for x in mm.groups())
                    if r - l >= 100 and b - t >= 100:
                        rects[pkg] = (l, t, r, b)
                    break
    return {"focus": focus, "rects": rects, "anr": anr}

def anr_from_logcat(pkgs):
    out = sh("logcat -d -v epoch -b main -b events -t 600 am_anr:I ActivityManager:E *:S", timeout=8)
    hit = set()
    for line in out.splitlines():
        m = _EPOCH_RX.match(line)
        if not m or ("am_anr" not in line and "ANR in" not in line):
            continue
        ts = float(m.group(1))
        for p in pkgs:
            if p in line and ts > LAUNCHED_AT.get(p, 0) and ts > ANR_SEEN.get(p, 0):
                hit.add(p)
                ANR_SEEN[p] = ts
    return hit

def screen_guard(packages):
    global _SCREEN_LAST_SWEEP, _FRAME_WARNED
    now = time.time()
    if not (WB_DETECT or OVERLAY_DETECT) or now - _SCREEN_LAST_SWEEP < SCREEN_CHECK_SEC or not root_mode():
        return []
    _SCREEN_LAST_SWEEP = now
    running = [p for p in packages if is_app_running(p)]
    for p in list(SCREEN_STATE):
        if p not in running:
            SCREEN_STATE.pop(p, None)
    if not running:
        return []
    cooling = lambda p: now - SCREEN_COOLDOWN.get(p, 0) < SCREEN_COOLDOWN_SEC
    flagged = []
    snap = window_snapshot(running)
    if OVERLAY_DETECT:
        for p in sorted((set(snap["anr"]) | anr_from_logcat(running)) & set(running)):
            if not cooling(p):
                flagged.append((p, "Client / Game Not Responding (ANR): GUI đứng, nút bấm không ăn"))
    done = {p for p, _ in flagged}
    cands = [p for p in running if p not in done and not cooling(p) and not BLACK_SCREEN_ACTIVE
             and now - LAUNCHED_AT.get(p, 0) >= SCREEN_GRACE_SEC
             and (p in snap["rects"] or snap["focus"] == p)]
    if cands:
        frame = capture_frame()
        if frame is None:
            if not _FRAME_WARNED:
                _FRAME_WARNED = True
                print("\033[1;33m[!] Không chụp được màn hình (screencap lỗi) nên chưa kiểm tra được trắng/đen / GUI đứng.\033[0m")
        else:
            for p in cands:
                res = analyze_frame(frame, snap["rects"].get(p))
                if not res:
                    continue
                st = SCREEN_STATE.setdefault(p, {"wb": 0, "fp": None, "since": now})
                if res["kind"] in ("white", "black"):
                    st["wb"] += 1
                    st["fp"] = None
                    if WB_DETECT and st["wb"] >= WB_CONFIRM_COUNT:
                        flagged.append((p, f"Màn hình {'trắng' if res['kind'] == 'white' else 'đen'} kẹt (không tải được tài nguyên game)"))
                    continue
                st["wb"] = 0
                if st["fp"] == res["fp"]:
                    if OVERLAY_DETECT:
                        static = now - st["since"]
                        need = OVERLAY_FREEZE_SEC if LOG_SOURCE_WORKS else OVERLAY_FREEZE_SEC * 2
                        if static >= need and LAST_ACTIVITY.get(p, 0) <= st["since"]:
                            flagged.append((p, f"Overlay / GUI client bị đứng (khung hình không đổi {int(static)}s, không có log mới)"))
                else:
                    st["fp"], st["since"] = res["fp"], now
    for p, _ in flagged:
        SCREEN_COOLDOWN[p] = now
        SCREEN_STATE.pop(p, None)
    return flagged

def screen_view_now(pkg):
    snap = window_snapshot([pkg])
    if pkg in snap["anr"]:
        return "anr"
    if pkg not in snap["rects"] and snap["focus"] != pkg:
        return None
    if BLACK_SCREEN_ACTIVE:
        return None
    frame = capture_frame()
    if frame is None:
        return None
    res = analyze_frame(frame, snap["rects"].get(pkg))
    return res["kind"] if res else None

def wait_map_load(pkg):
    t0 = time.time()
    bad = 0
    joined_hint = False
    while time.time() - t0 < MAP_LOAD_WAIT:
        if wait_with_stop_check(MAP_POLL_SEC):
            return None
        if not is_app_running(pkg):
            return "Game bị tắt / crash (không còn tiến trình)"
        text = read_new_log_text(pkg)
        if scan_text_for_vip_dead(text):
            return "VIP_DEAD: Link VIP Server có dấu hiệu đã hết hạn / không còn tồn tại (Log File)"
        found, reason = scan_text_for_problem(text)
        if found:
            return f"{reason} (Log File)"
        text2 = read_new_logcat_text(pkg)
        if scan_text_for_vip_dead(text2):
            return "VIP_DEAD: Link VIP Server có dấu hiệu đã hết hạn / không còn tồn tại (Logcat)"
        found, reason = scan_text_for_problem(text2, check_crash=True)
        if found:
            return f"{reason} (Logcat)"
        low = (text + "\n" + text2).lower()
        if any(m in low for m in JOIN_MARKERS):
            joined_hint = True
            break
        if (WB_DETECT or OVERLAY_DETECT) and root_mode():
            kind = screen_view_now(pkg)
            if kind == "anr" and OVERLAY_DETECT:
                return "Client / Game Not Responding (ANR): GUI đứng, nút bấm không ăn"
            if kind in ("white", "black") and WB_DETECT:
                bad += 1
                if bad >= WB_JOIN_CONFIRM:
                    return f"Màn hình {'trắng' if kind == 'white' else 'đen'} kẹt (không tải được tài nguyên game)"
            else:
                bad = 0
    if joined_hint:
        print(f"\033[1;32m[*] {tab_label(pkg)}: log xác nhận đã vào map.\033[0m")
    return quick_problem(pkg)

def screen_guard_label():
    return f"trắng/đen {'Bật' if WB_DETECT else 'Tắt'} · ANR/GUI đứng {'Bật' if OVERLAY_DETECT else 'Tắt'}"

def get_rejoin_mode_str():
    if AUTO_REJOIN_MODE == 1:
        return "Auto rejoin vang/crash"
    return f"Delay Rejoin ({DELAY_REJOIN_MINUTES}p)"

def load_saved_config():
    global WEBHOOK_URL, DISCORD_UID, AUTO_CLEAR_DATA, FREEZE_TIMEOUT_MIN, AUTO_BACKUP
    global PACKAGE_PREFIX, TARGET_LINK, SELECTED_GAME_NAME, AUTO_REJOIN_MODE, DELAY_REJOIN_MINUTES
    global LOW_RAM_ALERT, LOW_RAM_MB, LOW_RAM_AUTO_CLEAN, NET_CHECK
    global GFX_LOW, GFX_FPS, GFX_AUTO, AUTO_RESTART_HOURS, AUTO_RESTART_ACTION
    global KEY_AUTO, WB_DETECT, OVERLAY_DETECT, SERVER_HOP, HOP_PING_MS, BLACK_SCREEN
    global GAME_PROFILES, EXECUTOR_BINDING, PACKAGE_GAMES
    global GROQ_API_KEY, GROQ_ENABLED
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
    QUIET_HOURS.update(data.get("quiet_hours", {}))
    STOP_TIMER.update(data.get("stop_timer", {}))
    MONITOR_ONLY = bool(data.get("monitor_only", MONITOR_ONLY))
    SCREEN_ARCHIVE.update(data.get("screen_archive", {}))
    ROBLOX_VERSIONS.update(data.get("app_versions", {}))
    mins = data.get("freeze_timeout_min", FREEZE_TIMEOUT_MIN)
    if isinstance(mins, int) and 3 <= mins <= 5:
        FREEZE_TIMEOUT_MIN = mins
    pref = data.get("package_prefix")
    if isinstance(pref, str) and pref.strip():
        PACKAGE_PREFIX = pref.strip()
    link = data.get("target_link")
    if isinstance(link, str) and link.strip():
        TARGET_LINK = link.strip()
        name = data.get("selected_game_name")
        if isinstance(name, str) and name.strip():
            SELECTED_GAME_NAME = name.strip()
    mode = data.get("auto_rejoin_mode")
    if mode in (1, 2) and not isinstance(mode, bool):
        AUTO_REJOIN_MODE = mode
    dmin = data.get("delay_rejoin_minutes")
    if isinstance(dmin, int) and not isinstance(dmin, bool) and dmin > 0:
        DELAY_REJOIN_MINUTES = dmin
    acc = data.get("accounts", {})
    if isinstance(acc, dict):
        ACCOUNTS.clear()
        ACCOUNTS.update({str(k): str(v) for k, v in acc.items() if isinstance(v, str)})
    LOW_RAM_ALERT = bool(data.get("low_ram_alert", LOW_RAM_ALERT))
    LOW_RAM_AUTO_CLEAN = bool(data.get("low_ram_auto_clean", LOW_RAM_AUTO_CLEAN))
    ram_mb = data.get("low_ram_mb")
    if isinstance(ram_mb, int) and not isinstance(ram_mb, bool) and 200 <= ram_mb <= 4000:
        LOW_RAM_MB = ram_mb
    pr = data.get("profiles")
    if isinstance(pr, dict):
        PROFILES.clear()
        PROFILES.update({str(k): v for k, v in pr.items() if isinstance(v, dict)})
    sch = data.get("schedule")
    if isinstance(sch, dict):
        SCHEDULE["start"] = sch.get("start") if _valid_hhmm(sch.get("start")) else ""
        SCHEDULE["stop"] = sch.get("stop") if _valid_hhmm(sch.get("stop")) else ""
    NET_CHECK = bool(data.get("net_check", NET_CHECK))
    GFX_LOW = bool(data.get("gfx_low", GFX_LOW))
    GFX_AUTO = bool(data.get("gfx_auto", GFX_AUTO))
    fps = data.get("gfx_fps")
    if isinstance(fps, int) and not isinstance(fps, bool) and (fps == 0 or fps in (15, 20, 30)):
        GFX_FPS = fps
    hrs = data.get("auto_restart_hours")
    if isinstance(hrs, int) and not isinstance(hrs, bool) and (hrs == 0 or hrs in (2, 3, 4)):
        AUTO_RESTART_HOURS = hrs
    if data.get("auto_restart_action") in ("clean", "reset"):
        AUTO_RESTART_ACTION = data["auto_restart_action"]
    al = data.get("aliases")
    if isinstance(al, dict):
        ALIASES.clear()
        ALIASES.update({str(k): str(v).strip() for k, v in al.items() if isinstance(v, str) and v.strip()})
    KEY_AUTO = bool(data.get("key_auto", KEY_AUTO))
    WB_DETECT = bool(data.get("wb_detect", WB_DETECT))
    OVERLAY_DETECT = bool(data.get("overlay_detect", OVERLAY_DETECT))
    SERVER_HOP = bool(data.get("server_hop", SERVER_HOP))
    BLACK_SCREEN = bool(data.get("black_screen", BLACK_SCREEN))
    hp = data.get("hop_ping_ms")
    if isinstance(hp, int) and not isinstance(hp, bool) and 200 <= hp <= 2000:
        HOP_PING_MS = hp
    vs = data.get("vip_servers")
    if isinstance(vs, list):
        VIP_SERVERS.clear()
        for v in vs:
            if isinstance(v, str) and valid_vip_link(v) and v not in VIP_SERVERS and len(VIP_SERVERS) < MAX_VIP_SERVERS:
                VIP_SERVERS.append(v)
    kf = data.get("key_files")
    if isinstance(kf, dict):
        KEY_FILES.clear()
        for k, v in kf.items():
            if isinstance(v, list):
                paths = [x for x in v if isinstance(x, str) and x.startswith("/")]
                if paths:
                    KEY_FILES[str(k)] = paths

    gp = data.get("game_profiles")
    if isinstance(gp, dict):
        GAME_PROFILES.clear()
        for game_name, profile in gp.items():
            if isinstance(profile, dict):
                GAME_PROFILES[str(game_name)] = {
                    "delay_rejoin_min": profile.get("delay_rejoin_min", DELAY_REJOIN_MINUTES),
                    "freeze_timeout_sec": profile.get("freeze_timeout_sec", FREEZE_TIMEOUT_MIN * 60),
                    "target_fps": profile.get("target_fps", GFX_FPS),
                    "server_hop_enabled": profile.get("server_hop_enabled", SERVER_HOP),
                }

    eb = data.get("executor_binding")
    if isinstance(eb, dict):
        EXECUTOR_BINDING.clear()
        for pkg, exe in eb.items():
            if isinstance(exe, str) and exe in EXECUTOR_NAMES:
                EXECUTOR_BINDING[str(pkg)] = exe

    pg = data.get("package_games")
    if isinstance(pg, dict):
        PACKAGE_GAMES.clear()
        for pkg, game_data in pg.items():
            if isinstance(game_data, dict):
                PACKAGE_GAMES[str(pkg)] = {
                    "game_name": game_data.get("game_name", ""),
                    "game_id": game_data.get("game_id", ""),
                }

    # COHERE API KEY DISABLED FROM CONFIG - Load from environment variable COHERE_API_KEY instead
    # This prevents storing API keys in config files
    # groq_key = data.get("groq_api_key", "")
    # if isinstance(groq_key, str) and groq_key.strip():
    #     GROQ_API_KEY = groq_key.strip()
    #     GROQ_ENABLED = bool(data.get("groq_enabled", False))

def save_config_file():
    try:
        data = {
            "webhook_url": WEBHOOK_URL,
            "discord_uid": DISCORD_UID,
            "auto_clear_data": AUTO_CLEAR_DATA,
            "freeze_timeout_min": FREEZE_TIMEOUT_MIN,
            "auto_backup": AUTO_BACKUP,
            "quiet_hours": QUIET_HOURS,
            "stop_timer": STOP_TIMER,
            "monitor_only": MONITOR_ONLY,
            "screen_archive": SCREEN_ARCHIVE,
            "app_versions": ROBLOX_VERSIONS,
            "package_prefix": PACKAGE_PREFIX,
            "target_link": TARGET_LINK,
            "selected_game_name": SELECTED_GAME_NAME,
            "auto_rejoin_mode": AUTO_REJOIN_MODE,
            "delay_rejoin_minutes": DELAY_REJOIN_MINUTES,
            "accounts": ACCOUNTS,
            "low_ram_alert": LOW_RAM_ALERT,
            "low_ram_mb": LOW_RAM_MB,
            "low_ram_auto_clean": LOW_RAM_AUTO_CLEAN,
            "profiles": PROFILES,
            "schedule": SCHEDULE,
            "net_check": NET_CHECK,
            "aliases": ALIASES,
            "gfx_low": GFX_LOW,
            "gfx_fps": GFX_FPS,
            "gfx_auto": GFX_AUTO,
            "auto_restart_hours": AUTO_RESTART_HOURS,
            "auto_restart_action": AUTO_RESTART_ACTION,
            "key_auto": KEY_AUTO,
            "key_files": KEY_FILES,
            "wb_detect": WB_DETECT,
            "overlay_detect": OVERLAY_DETECT,
            "server_hop": SERVER_HOP,
            "hop_ping_ms": HOP_PING_MS,
            "vip_servers": VIP_SERVERS,
            "black_screen": BLACK_SCREEN,
            "game_profiles": GAME_PROFILES,
            "executor_binding": EXECUTOR_BINDING,
            "package_games": PACKAGE_GAMES,
            # COHERE API KEY NOT SAVED - Use environment variable COHERE_API_KEY
            # "groq_api_key": GROQ_API_KEY,
            # "groq_enabled": GROQ_ENABLED
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception:
        pass

def clear_screen():
    os.system('stty sane 2>/dev/null')
    os.system('clear')

def print_ascii_banner():
    P1 = "\033[38;5;129m"   # tím sáng
    P2 = "\033[38;5;135m"   # tím trung
    P3 = "\033[38;5;141m"   # tím nhạt
    W  = "\033[1;97m"       # trắng sáng
    DW = "\033[38;5;189m"   # trắng tím nhạt
    AC = "\033[38;5;183m"   # tím pastel (accent)
    LN = "\033[38;5;240m"   # xám đường viền
    RS = "\033[0m"

    print(f"""
{LN}  ╔══════════════════════════════════════════════════════════════╗{RS}
{LN}  ║{RS}                                                              {LN}║{RS}
{LN}  ║{RS}  {P1}██████╗ {P2} █████╗ {P3}██╗{W}███╗  ██╗    {P1}██████╗ {W}███████╗{P2}     {W}██╗{P3}███╗  {P1}██╗{RS}  {LN}║{RS}
{LN}  ║{RS}  {P1}██╔══██╗{P2}██╔══██╗{P3}██║{W}████╗ ██║    {P1}██╔══██╗{W}██╔════╝{P2}     {W}██║{P3}████╗ {P1}██║{RS}  {LN}║{RS}
{LN}  ║{RS}  {P1}██████╔╝{P2}███████║{P3}██║{W}██╔██╗██║    {P1}██████╔╝{W}█████╗  {P2}     {W}██║{P3}██╔██╗{P1}██║{RS}  {LN}║{RS}
{LN}  ║{RS}  {P1}██╔═══╝ {P2}██╔══██║{P3}██║{W}██║╚████║    {P1}██╔══██╗{W}██╔══╝  {P2}     {W}██║{P3}██║╚████║{RS}  {LN}║{RS}
{LN}  ║{RS}  {P1}██║     {P2}██║  ██║{P3}██║{W}██║ ╚███║    {P1}██║  ██║{W}███████╗{P2}     {W}██║{P3}██║ ╚███║{RS}  {LN}║{RS}
{LN}  ║{RS}  {P3}╚═╝     ╚═╝  ╚═╝╚═╝╚═╝  ╚══╝    ╚═╝  ╚═╝╚══════╝     ╚═╝╚═╝  ╚══╝{RS}  {LN}║{RS}
{LN}  ║{RS}                                                              {LN}║{RS}
{LN}  ╚══════════════════════════════════════════════════════════════╝{RS}""")

# ==================== UI HELPERS ====================
class C:
    R = "\033[0m"
    PUR = "\033[1;35m"
    LPUR = "\033[38;5;141m"
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

def msg_done(text):
    print(f"\n {C.GRN}[✓] {text}{C.R}")

def msg_warn(text):
    print(f" {C.YEL}[!] {text}{C.R}")

def msg_cancel(text):
    print(f"\n {C.YEL}[-] {text}{C.R}")

def wait_enter(text="Ấn Enter để tiếp tục..."):
    try:
        input(f"\n {C.GRY}{text}{C.R} ")
    except EOFError:
        pass



def exit_tool():
    try:
        print(f"\n {C.GRN}[✓] Đã thoát tool thành công. Good bye!{C.R}")
        sys.stdout.flush()
        time.sleep(0.5)
    except Exception:
        pass
    finally:
        # Clean exit - force sys.exit to prevent hanging threads/segfault
        import os
        os._exit(0)  # Force exit without cleanup that might crash

def ask(label):
    print(f" {C.PUR}›{C.R} {C.WHT}{label}{C.R} ", end="", flush=True)
    return input()

def with_spinner(label, func, *args, **kwargs):
    box = {}

    def worker():
        try:
            box["v"] = func(*args, **kwargs)
        except Exception as e:
            box["e"] = e

    t = threading.Thread(target=worker, daemon=False)
    t.start()
    frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    t0 = time.time()
    i = 0
    max_timeout = 60  # Absolute timeout: if thread takes >60s, fail
    try:
        while t.is_alive():
            elapsed = time.time() - t0
            if elapsed > max_timeout:
                # Thread is hanging or crashed -> timeout
                sys.stdout.write("\r" + " " * (vlen(label) + 16) + "\r")
                sys.stdout.flush()
                box["e"] = Exception(f"Lỗi hệ thống: Timeout sau {max_timeout}s")
                break
            sys.stdout.write(f"\r {C.LPUR}{frames[i % len(frames)]}{C.R} {C.WHT}{label}{C.R} {C.GRY}({int(elapsed)}s){C.R}   ")
            sys.stdout.flush()
            i += 1
            time.sleep(0.1)
    finally:
        sys.stdout.write("\r" + " " * (vlen(label) + 16) + "\r")
        sys.stdout.flush()
    
    # Wait for thread to finish (with timeout)
    t.join(timeout=5)
    
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

# ==================== HWID (CHỐNG DÙNG CHUNG KEY / GIẢ MẠO ID) ====================
_JUNK_IDS = {"", "unknown", "null", "none", "default", "0", "00000000", "0123456789abcdef", "1234567890",
             "1234567890abcdef", "not specified", "to be filled by o.e.m.", "02:00:00:00:00:00", "00:00:00:00:00:00"}

def _clean_id(value):
    v = str(value or "").strip()
    low = v.lower()
    if low in _JUNK_IDS or len(low) < 4 or len(set(low.replace(":", ""))) <= 2:
        return ""
    return v

def _read_text(path, limit=65536):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read(limit).strip()
    except Exception:
        return ""

def _prop(name):
    return run_cmd(["getprop", name], timeout=5).strip()

def _cpuinfo_field(field):
    for line in _read_text("/proc/cpuinfo").splitlines():
        if line.lower().startswith(field.lower()) and ":" in line:
            return line.split(":", 1)[1].strip()
    return ""

def _device_sig(body):
    return hmac.new(SECRET_KEY.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()

def _load_device_file():
    try:
        with open(DEVICE_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return None, False
    if not isinstance(raw, dict) or not isinstance(raw.get("seed"), str):
        return None, False
    body = json.dumps({"seed": raw.get("seed"), "base": raw.get("base")}, sort_keys=True)
    if not hmac.compare_digest(str(raw.get("sig", "")), _device_sig(body)):
        return None, True
    return raw, False

def _save_device_file(seed, base):
    body = json.dumps({"seed": seed, "base": base}, sort_keys=True)
    data = {"seed": seed, "base": base, "sig": _device_sig(body)}
    tmp = DEVICE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        try:
            os.chmod(tmp, 0o600)
        except Exception:
            pass
        os.replace(tmp, DEVICE_FILE)
    except Exception:
        pass

def get_device_profile():
    problems = []
    s1 = _clean_id(_prop("ro.serialno"))
    s2 = _clean_id(_prop("ro.boot.serialno"))
    if s1 and s2 and len(s1) >= 6 and len(s2) >= 6 and s1.lower() != s2.lower():
        problems.append("serial_mismatch")

    strong = {"serial": s1 or s2}
    strong["soc"] = _clean_id(_read_text("/sys/devices/soc0/serial_number"))
    strong["cpu_serial"] = _clean_id(_cpuinfo_field("Serial"))
    strong["emmc_cid"] = _clean_id(_read_text("/sys/block/mmcblk0/device/cid"))
    mac = _read_text("/sys/class/net/wlan0/address").lower()
    try:
        if len(mac) == 17 and not (int(mac[:2], 16) & 2):
            strong["mac"] = _clean_id(mac)
    except ValueError:
        pass

    abi = _prop("ro.product.cpu.abi").lower()
    try:
        machine = os.uname().machine.lower()
    except Exception:
        machine = ""
    abi_fam = "arm" if abi.startswith(("arm", "aarch")) else ("x86" if abi.startswith(("x86", "i386", "i686")) else "")
    mach_fam = "arm" if machine.startswith(("arm", "aarch")) else ("x86" if machine.startswith(("x86", "i386", "i686")) else "")
    if abi_fam and mach_fam and abi_fam != mach_fam:
        problems.append("arch_mismatch")

    comps = {k: v for k, v in strong.items() if v}
    hard = {
        "board": _prop("ro.product.board"), "brand": _prop("ro.product.brand"),
        "model": _prop("ro.product.model"), "maker": _prop("ro.product.manufacturer"),
        "device": _prop("ro.product.device"), "hardware": _prop("ro.hardware"),
        "abi": abi, "cpu_hw": _cpuinfo_field("Hardware"),
    }
    for k, v in hard.items():
        comps["hw_" + k] = v if v else "unknown"

    dev, tampered = _load_device_file()
    if tampered:
        problems.append("device_file_tampered")
    seed = dev["seed"] if dev else "".join(random.choices("0123456789abcdef", k=32))
    has_strong = any(strong.values())
    if not has_strong:
        comps["seed"] = seed
    if dev is None and not tampered:
        _save_device_file(seed, None)
        dev = {"seed": seed, "base": None}

    raw = "PAIN-HWID-v2|" + "|".join(f"{k}={comps[k]}" for k in sorted(comps))
    return {
        "hwid": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "strong": has_strong,
        "comps": {k: hashlib.sha256(str(v).encode("utf-8")).hexdigest()[:10] for k, v in comps.items()},
        "problems": problems,
        "seed": seed,
        "device": dev,
    }

def get_hwid():
    try:
        return get_device_profile()["hwid"]
    except Exception:
        return hashlib.sha256("default_fallback_hwid".encode()).hexdigest()

def device_integrity_problem(profile):
    probs = profile["problems"]
    if "device_file_tampered" in probs:
        return "File định danh thiết bị bị chỉnh sửa."
    if "serial_mismatch" in probs:
        return "Phát hiện giả mạo thông tin thiết bị (serial không khớp)."
    if "arch_mismatch" in probs:
        return "Phát hiện giả mạo thông tin thiết bị (kiến trúc CPU không khớp)."
    base = (profile.get("device") or {}).get("base")
    if isinstance(base, dict) and base.get("hwid") and base.get("hwid") != profile["hwid"]:
        old, new = base.get("comps") or {}, profile["comps"]
        changed = {k for k in set(old) | set(new) if old.get(k) != new.get(k)}
        if any(k.startswith("hw_") for k in changed):
            return "License này được kích hoạt trên thiết bị khác, không thể dùng trên máy này."
        return "ID thiết bị đã bị thay đổi/giả mạo so với lúc kích hoạt key."
    return None

def fatal_exit(message, purge=True):
    if purge:
        try:
            os.remove(LICENSE_FILE)
        except Exception:
            pass
    try:
        clear_screen()
        print_ascii_banner()
        print()
    except Exception:
        pass
    msg_err(message)
    msg_info("Tool sẽ tự động ngắt và thoát.")
    log_event("LICENSE", detail=message)
    time.sleep(3)
    sys.exit(1)

def kick_out(message):
    try:
        restore_screen_after_run()
    except Exception:
        pass
    try:
        os.remove(LICENSE_FILE)
    except Exception:
        pass
    try:
        log_event("LICENSE", detail=f"KICK: {message}")
        sys.stdout.write(f"\n\n{C.RED}[!] {message}{C.R}\n{C.YEL}[*] Tool tự động ngắt và thoát.{C.R}\n")
        sys.stdout.flush()
    except Exception:
        pass
    time.sleep(2)
    os._exit(1)

_KICK_REASONS = {"hwid_mismatch", "key_not_found", "expired"}
_TRANSIENT_REASONS = {"network", "request_expired", "server_error", "source_code_not_found", "missing_data", "missing_key"}

def license_recheck(key, base_hwid):
    prof = get_device_profile()
    problem = device_integrity_problem(prof)
    if problem:
        return problem
    if prof["hwid"] != base_hwid:
        return "ID thiết bị bị thay đổi trong lúc đang chạy."
    ok, msg = check_license_curl(key)   # ← chữ ký mới: chỉ còn key (không còn hwid)
    if not ok and LAST_LICENSE_REASON in _KICK_REASONS:
        return msg
    return None

_HB_STARTED = False

def _heartbeat_loop(key, base_hwid):
    while True:
        time.sleep(HEARTBEAT_SEC)
        try:
            why = license_recheck(key, base_hwid)
        except Exception:
            continue
        if why:
            kick_out(why)

def device_activated(profile, key):
    global _HB_STARTED
    _save_device_file(profile["seed"], {"hwid": profile["hwid"], "comps": profile["comps"]})
    # HEARTBEAT DISABLED - Prevents spam connection messages and thread cleanup crash on exit
    # if not _HB_STARTED:
    #     _HB_STARTED = True
    #     threading.Thread(target=_heartbeat_loop, args=(key, profile["hwid"]), daemon=True).start()

_LICENSE_REASON_MSG = {
    "hwid_mismatch": "Key này đã được kích hoạt trên thiết bị khác (sai HWID)",
    "expired": "Key đã hết hạn",
    "key_not_found": "Key không tồn tại hoặc đã bị xóa",
    "invalid_signature": "Chữ ký không hợp lệ (tool và server khác SECRET_KEY)",
    "request_expired": "Đồng hồ máy bị lệch giờ, hãy bật giờ tự động rồi thử lại",
    "missing_data": "Thiếu dữ liệu xác thực",
    "missing_key": "Key không được để trống",
    "source_code_not_found": "Server chưa có file paintool_premium.py",
    "server_error": "Lỗi server, thử lại sau",
    "network": "Không kết nối được tới server (kiểm tra mạng)",
}

# ==================== HWID AN TOÀN (FILE-BASED, KHÔNG SUBPROCESS, KHÔNG SEGFAULT) ====================
def get_device_hwid():
    """Lấy HWID an toàn từ file lưu trữ, KHÔNG dùng subprocess để tránh crash trên Termux/UgPhone.

    - Đọc file `.device_hwid` trong thư mục home. Nếu có -> trả về luôn.
    - Chưa có -> sinh UUID mới `ugphone_xxxxxxxxxxxx` (12 ký tự hex), lưu lại để tái sử dụng.
    - Bọc try/except + fallback cứng để không bao giờ crash tool.
    """
    try:
        hwid_file = ".device_hwid"
        if os.path.exists(hwid_file):
            with open(hwid_file, "r") as f:
                hwid = f.read().strip()
                if hwid:
                    return hwid

        # Tạo HWID duy nhất lưu lại cho máy
        hwid = "ugphone_" + str(uuid.uuid4()).replace("-", "")[:12]
        with open(hwid_file, "w") as f:
            f.write(hwid)
        return hwid
    except Exception:
        return "ugphone_fallback_device_123"

# ==================== XÁC THỰC KEY ONLINE (HMAC-SHA256, URLLIB THUẦN PYTHON) ====================
def check_license_curl(key):
    """✓ ONLINE MODE - Xác thực với Express Server qua API (HMAC-SHA256, subprocess curl STABLE).

    - Tự lấy HWID an toàn qua get_device_hwid() (đọc/ghi file UUID).
    - Tạo chữ ký HMAC-SHA256 từ `key:hwid:timestamp` bằng SECRET_KEY.
    - Gửi POST JSON qua subprocess curl (STABLE trên Termux/UgPhone, không urllib segfault).
    - Trả về tuple (bool, str) để tương thích với các caller cũ (with_spinner, license_recheck...).
    - Cập nhật LAST_LICENSE_REASON và LAST_LICENSE_EXPIRES cho hệ thống heartbeat.
    
    TERMUX FIX: Dùng curl subprocess thay urllib — tránh OpenSSL segfault hoàn toàn.
    """
    global LAST_LICENSE_EXPIRES, LAST_LICENSE_REASON

    error_map = {
        "missing_data": "Dữ liệu gửi lên không đủ!",
        "missing_key": "Key không được để trống!",
        "request_expired": "Thời gian thiết bị lệch quá 30s so với máy chủ!",
        "invalid_signature": "Chữ ký bảo mật không hợp lệ (Sai SECRET_KEY)!",
        "key_not_found": "Key không tồn tại trên hệ thống!",
        "expired": "Key bản quyền đã hết hạn sử dụng!",
        "hwid_mismatch": "Key đã được liên kết với thiết bị (HWID) khác!",
        "source_code_not_found": "Không tìm thấy file mã nguồn trên Server!",
        "server_error": "Lỗi xử lý nội bộ của Server!",
    }

    if not key:
        LAST_LICENSE_REASON = "missing_data"
        print("[!] Key không được để trống!")
        return False, "[!] Key không được để trống!"

    hwid = get_device_hwid()
    timestamp = int(time.time())

    # Tạo chữ ký HMAC-SHA256 bảo mật khớp với index.js
    raw_data = f"{key}:{hwid}:{timestamp}"
    signature = hmac.new(
        SECRET_KEY.encode("utf-8"),
        raw_data.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    payload = {
        "key": key,
        "hwid": hwid,
        "timestamp": timestamp,
        "signature": signature,
    }

    # Print statements removed to prevent spam - feedback shown via with_spinner instead

    try:
        # TERMUX FIX: Dùng curl subprocess thay urllib để tránh OpenSSL crash
        # curl stable trên termux, không trigger segfault như urllib
        data_json = json.dumps(payload)
        
        # Tạo temp file để lưu JSON payload (tránh shell injection)
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tf:
            tf.write(data_json)
            temp_file = tf.name
        
        try:
            # curl command: POST JSON từ file, timeout 45s, insecure (tránh SSL cert check)
            cmd = [
                "curl",
                "-s",                          # silent
                "-m", "45",                    # timeout 45s
                "-k",                          # insecure (skip SSL cert verify)
                "-X", "POST",                  # POST method
                "-H", "Content-Type: application/json",
                "-d", f"@{temp_file}",        # data từ file
                SERVER_URL                     # endpoint
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=50,
                stdin=subprocess.DEVNULL
            )
            
            if result.returncode != 0:
                LAST_LICENSE_REASON = "network"
                return False, f"[!] Thất bại: Không thể kết nối tới Server (curl error {result.returncode})."
            
            response_body = result.stdout.strip()
            if not response_body:
                LAST_LICENSE_REASON = "server_error"
                return False, "[!] Server trả về phản hồi trống!"
            
            try:
                data = json.loads(response_body)
            except json.JSONDecodeError:
                LAST_LICENSE_REASON = "server_error"
                return False, "[!] Server trả về phản hồi không hợp lệ!"

            if data.get("valid") is True:
                LAST_LICENSE_EXPIRES = data.get("expires", "2099-12-31")
                LAST_LICENSE_REASON = "ok"
                return True, "[+] Kích hoạt bản quyền thành công!"

            reason = data.get("reason", "server_error")
            LAST_LICENSE_REASON = reason
            msg = error_map.get(reason, f"Lỗi không xác định ({reason})")
            return False, f"[!] Thất bại: {msg}"

        finally:
            # Xóa temp file
            try:
                os.remove(temp_file)
            except Exception:
                pass

    except subprocess.TimeoutExpired:
        LAST_LICENSE_REASON = "network"
        print("[!] Thất bại: Kết nối bị timeout (>45s).")
        return False, "[!] Thất bại: Kết nối bị timeout (>45s)."

    except Exception as e:
        LAST_LICENSE_REASON = "server_error"
        print(f"[!] Thất bại: Lỗi hệ thống ({str(e)})")
        return False, f"[!] Thất bại: Lỗi hệ thống ({str(e)})"

def _clear_device_lock():
    try:
        dev_data, tampered = _load_device_file()
        if dev_data and isinstance(dev_data, dict):
            seed = dev_data.get("seed", "")
            base = dev_data.get("base", {})
            if isinstance(base, dict) and "locked_hwid" in base:
                del base["locked_hwid"]
                if "activation_time" in base:
                    del base["activation_time"]
                if "hwid_history" in base:
                    del base["hwid_history"]
                _save_device_file(seed, base)
                log_event("INFO", detail="Đã xóa khóa HWID sau khi reset từ bot")
    except Exception as e:
        log_event("WARN", detail=f"Không xóa được khóa HWID: {e}")

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
    st_line = update_status_line()
    if st_line:
        print(f" {st_line}")
        print()
    print(f" {C.GRY}Nhập 0 hoặc exit để thoát.{C.R}")
    if note:
        print(f"\n {note}")
    print()

def notify_bot_hwid_linked(key_str, hwid_str, discord_id=""):
    try:
        timestamp = int(time.time())
        rawData = f"{key_str}:{hwid_str}:{timestamp}"
        signature = hmac.new(
            SECRET_KEY.encode(),
            rawData.encode(),
            hashlib.sha256
        ).hexdigest()

        payload = {
            "key": key_str,
            "hwid": hwid_str,
            "timestamp": timestamp,
            "signature": signature,
            "discord_id": discord_id
        }

        cmd = [
            "curl", "-s", "-X", "POST",
            "https://paintool-bot.onrender.com/api/link-hwid",
            "-H", "Content-Type: application/json",
            "-d", json.dumps(payload),
            "--max-time", "5"
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=6)
            if result.returncode == 0:
                log_event("INFO", detail="Bot notification: HWID linked successfully")
                return True
        except Exception as e:
            log_event("WARN", detail=f"Bot notification failed (curl): {str(e)}")

        return False
    except Exception as e:
        log_event("ERROR", detail=f"notify_bot_hwid_linked error: {str(e)}")
        return False

def authenticate():
    """✓ XÁC THỰC BẢN QUYỀN - Logic rõ ràng:
    1. Nếu file .pain_license tồn tại & xác thực thành công -> return ngay (thoát hàm)
    2. Nếu xác thực thất bại -> xóa file, hiển thị lỗi, chuyển sang nhập key thủ công
    3. Chỉ vào while True nếu không có file hoặc file không hợp lệ
    """
    profile = get_device_profile()
    hwid = profile["hwid"]
    problem = device_integrity_problem(profile)
    if problem:
        fatal_exit(problem)
    
    # ==================== BƯỚC 1: SKIP AUTO-LOAD (REMOVED) ====================
    # Auto-save and auto-load license file DISABLED per user request
    # Always require manual key entry every session
    
    # ==================== BƯỚC 2: NHẬP KEY THỦ CÔNG (LUÔN BẮT BUỘC) ====================
    check_update_on_launch(hwid)
    note = None
    while True:
        license_screen(hwid, note)
        note = None
        input_key = ask("Nhập Key:").strip()
        
        if input_key.lower() in ("exit", "0"):
            exit_tool()
        
        if not input_key:
            continue
        
        is_valid, response_text = with_spinner("Đang kết nối máy chủ", check_license_curl, input_key)
        
        if is_valid:
            # ✓ Xác thực key thành công -> Kích hoạt (KHÔNG LƯU FILE)
            # Auto-save DISABLED per user request
            device_activated(profile, input_key)
            extra = f" Hạn dùng đến: {LAST_LICENSE_EXPIRES}" if LAST_LICENSE_EXPIRES else ""
            msg_ok(f"Xác thực Key thành công!{extra}")
            notify_bot_hwid_linked(input_key, hwid)
            time.sleep(1)
            return  # ← THOÁT NGAY KHÔNG LỰC VÒNG WHILE
        
        # ✗ Xác thực thất bại -> Hiển thị lỗi & chờ nhập lại
        if LAST_LICENSE_REASON == "hwid_mismatch":
            fatal_exit(response_text)
        
        if LAST_LICENSE_REASON in _TRANSIENT_REASONS:
            note = f"{C.YEL}[!] {response_text}. Kiểm tra mạng rồi thử lại.{C.R}"
        else:
            note = f"{C.RED}[!] Thất bại: {response_text}.{C.R}"

def send_webhook(message, with_image=False):
    global _LAST_SHOT
    if BLACK_SCREEN_ACTIVE:
        with_image = False
    if not webhook_active():
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

        if with_image and (time.time() - _LAST_SHOT) < SCREENSHOT_MIN_GAP_SEC:
            with_image = False
        if with_image:
            _LAST_SHOT = time.time()
            try:
                os.remove(SCREENSHOT_PATH)
            except OSError:
                pass
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
    if "màn hình trắng" in low or "màn hình đen" in low:
        return "Màn hình trắng/đen kẹt"
    if "not responding" in low:
        return "Client Not Responding"
    if "overlay" in low:
        return "Overlay / GUI client bị đứng"
    if "treo" in low:
        return "Tab treo cứng"
    return "Bị Kick / Mất kết nối"

# ==================== COHERE AI ENGINE (replaced Groq) ====================
def init_groq():
    global _GROQ_CLIENT, GROQ_ENABLED
    if not _HAS_GROQ or not GROQ_API_KEY or "PLACEHOLDER" in GROQ_API_KEY:
        GROQ_ENABLED = False
        return False
    try:
        _GROQ_CLIENT = cohere.ClientV2(api_key=GROQ_API_KEY)
        GROQ_ENABLED = True
        return True
    except Exception:
        GROQ_ENABLED = False
        return False

def groq_analyze(prompt, max_tokens=300):
    global GROQ_REQUEST_COUNT, _GROQ_CLIENT
    if not GROQ_ENABLED or not _GROQ_CLIENT or GROQ_REQUEST_COUNT >= GROQ_QUOTA_LIMIT:
        return None
    try:
        response = _GROQ_CLIENT.messages.create(
            model="command-r-v1:0",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        GROQ_REQUEST_COUNT += 1
        return response.content[0].text if response.content else None
    except Exception:
        return None

def ai_error_analysis(pkg, error_code, error_reason):
    if not GROQ_ENABLED:
        return None
    prompt = f"""Bạn là expert phân tích lỗi Roblox. Phân tích lỗi này (JSON output chỉ):

Package: {pkg}
Error Code: {error_code}
Reason: {error_reason}

Output JSON này chính xác:
{{"root_cause": "nguyên nhân gốc", "confidence": 0.9, "recovery_actions": ["hành động 1", "hành động 2"]}}"""
    resp = groq_analyze(prompt, max_tokens=200)
    if not resp:
        return None
    try:
        start = resp.find('{')
        end = resp.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(resp[start:end])
    except Exception:
        pass
    return None

def ai_recovery_suggestion(pkg, error_code):
    if not GROQ_ENABLED:
        return None
    prompt = f"""Bạn là expert Roblox recovery. Gợi ý 3 hành động để khôi phục từ error {error_code}.

Output JSON:
{{"actions": [{{"action": "tắt tab", "success_rate": 85}}, ...]}}"""
    resp = groq_analyze(prompt, max_tokens=150)
    if not resp:
        return None
    try:
        start = resp.find('{')
        end = resp.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(resp[start:end])
    except Exception:
        pass
    return None

def ai_summarize_alerts(alerts_list):
    if not GROQ_ENABLED or len(alerts_list) < 3:
        return None
    alerts_text = "\n".join(f"- {a}" for a in alerts_list[-5:])
    prompt = f"""Tóm tắt {len(alerts_list)} alerts thành 2-3 dòng chuyên nghiệp:

{alerts_text}

Summary (2-3 dòng tối đa):"""
    resp = groq_analyze(prompt, max_tokens=100)
    return resp if resp else None

def ai_weekly_insights():
    if not GROQ_ENABLED or not GROQ_WEEKLY_ALERTS:
        return None
    total_alerts = len(GROQ_WEEKLY_ALERTS)
    critical_count = sum(1 for a in GROQ_WEEKLY_ALERTS if "critical" in a.lower())
    success_count = sum(1 for a in GROQ_WEEKLY_ALERTS if "success" in a.lower())

    prompt = f"""Viết report insights tuần (100 từ) từ dữ liệu:
- Tổng alerts: {total_alerts}
- Lỗi nặng: {critical_count}
- Rejoin thành công: {success_count}
- Uptime tool: tuần này

Format: 2-3 dòng summary + 2-3 gợi ý cải thiện."""
    resp = groq_analyze(prompt, max_tokens=150)
    return resp if resp else None

# ==================== END GROQ AI ENGINE ====================

def format_alert_description(pkg, reason, took=None):
    lines = []

    if pkg:
        tab_name = ALIASES.get(pkg) if ALIASES.get(pkg) else pkg[len(PACKAGE_PREFIX):].lstrip(".")
        lines.append(f"**Tab:** `{tab_name}`")

    if reason:
        lines.append(f"**Nguyên nhân:** {reason}")

    if took is not None:
        lines.append(f"**Thời gian xử lý:** {took}s")

    if pkg and pkg in JOINED_AT:
        uptime = int(time.time() - JOINED_AT[pkg])
        lines.append(f"**Thời gian trong map:** {fmt_duration(uptime)}")

    if pkg and ACCOUNTS.get(pkg):
        lines.append(f"**Tài khoản:** {ACCOUNTS[pkg]}")

    return "\n".join(lines) if lines else "Đã phát hiện lỗi và đang xử lý."

def send_detailed_alert(level, title, description, pkg=None, reason=None, action=None, took=None):
    if not WEBHOOK_URL:
        return

    try:
        style = ALERT_STYLES.get(level, ALERT_STYLES["critical"])
        now = time.time()

        fields = []

        if pkg:
            tab_alias = ALIASES.get(pkg) or pkg[len(PACKAGE_PREFIX):].lstrip(".")
            fields.append({
                "name": "📦 Tab",
                "value": f"`{tab_alias}`\n`{pkg}`",
                "inline": True
            })

        fields.append({
            "name": "🎮 Game",
            "value": SELECTED_GAME_NAME or "Chưa chọn",
            "inline": True
        })

        if pkg and ACCOUNTS.get(pkg):
            fields.append({
                "name": "👤 Tài khoản",
                "value": ACCOUNTS[pkg],
                "inline": True
            })

        if reason or took:
            details = []

            if reason:
                details.append(f"📍 **Lỗi:** {reason}")

            if took is not None:
                details.append(f"⏱️ **Xử lý trong:** {took}s")

            if pkg and pkg in JOINED_AT:
                uptime = int(now - JOINED_AT[pkg])
                details.append(f"📊 **Trong map:** {fmt_duration(uptime)}")

            if details:
                fields.append({
                    "name": "⚠️ Chi tiết lỗi",
                    "value": "\n".join(details),
                    "inline": False
                })

        if pkg:
            rj_count = REJOIN_COUNT.get(pkg, 0)
            total_uptime = fmt_duration(int(now - START_UP_TIME.timestamp())) if START_UP_TIME else "?"

            fields.append({
                "name": "📈 Thống kê",
                "value": f"**Rejoin:** {rj_count} lần\n**Uptime tool:** {total_uptime}",
                "inline": True
            })

        net_status = "🟢 Online" if is_online() else "🔴 Offline"
        fields.append({
            "name": "🌐 Mạng",
            "value": net_status,
            "inline": True
        })

        if GROQ_ENABLED and level == "critical" and reason:
            error_code = None
            for code in ROBLOX_ERROR_CODES:
                if code in reason:
                    error_code = code
                    break

            if error_code:
                ai_insights = ai_error_analysis(pkg, error_code, reason)
                if ai_insights:
                    try:
                        root_cause = ai_insights.get("root_cause", "Không xác định")
                        confidence = int(ai_insights.get("confidence", 0) * 100)
                        fields.append({
                            "name": "🤖 AI Analysis",
                            "value": f"**Nguyên nhân:** {root_cause}\n**Độ chính xác:** {confidence}%",
                            "inline": False
                        })
                        if GROQ_WEEKLY_ALERTS is not None:
                            GROQ_WEEKLY_ALERTS.append(f"Critical: {reason}")
                    except Exception:
                        pass

        if action:
            fields.append({
                "name": "🛠️ Hành động",
                "value": action,
                "inline": False
            })

        embed_obj = {
            "author": {
                "name": f"{style['icon']} {style['label']}",
                "icon_url": "https://i.postimg.cc/gJbhCmHL/Pain-Gamer.png"
            },
            "title": title,
            "description": description or format_alert_description(pkg, reason, took),
            "color": style["color"],
            "fields": fields,
            "footer": {
                "text": f"PAIN TOOL {VERSION} • Alert System",
                "icon_url": "https://i.postimg.cc/gJbhCmHL/Pain-Gamer.png"
            },
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        }

        payload_dict = {
            "username": "PAIN TOOL REJOIN VIP",
            "avatar_url": "https://i.postimg.cc/gJbhCmHL/Pain-Gamer.png",
            "embeds": [embed_obj]
        }

        if level in PING_LEVELS and not in_quiet_hours():
            mention = "@everyone" + (f" <@{DISCORD_UID}>" if DISCORD_UID else "")
            payload_dict["content"] = mention
            payload_dict["allowed_mentions"] = {"parse": ["everyone", "users"]}

        payload_json = json.dumps(payload_dict, ensure_ascii=False)
        run_cmd([
            "curl", "-s", "-X", "POST", WEBHOOK_URL,
            "-H", "Content-Type: application/json",
            "-d", payload_json
        ], timeout=10)

        log_event("ALERT_SENT", pkg=pkg, detail=f"{level}: {title}")

    except Exception as e:
        log_event("ALERT_ERR", pkg=pkg, detail=f"Gửi alert lỗi: {e}")

def handle_send_text():
    if not WEBHOOK_URL:
        clear_screen()
        section_title("SEND TEXT TO DISCORD")
        msg_err("Chưa cài Webhook URL. Vào Mục [5] để nhập Webhook của bạn trước khi dùng Send Text.")
        wait_enter()
        return
    while True:
        clear_screen()
        section_title("SEND TEXT TO DISCORD")
        text_target = WEBHOOK_URL
        print(f" {C.GRY}Gửi tới: webhook của bạn (đã cài ở mục [5]){C.R}")
        content_input = input("Nhập nội dung muốn gửi (Để trống để thoát): ").strip()
        if not content_input:
            msg_cancel("Đã thoát Send Text, quay về menu chính.")
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

        msg_info("Đang gửi nội dung lên Discord...")
        try:
            payload = json.dumps(embed_data)
            code = run_cmd(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-X", "POST", text_target,
                            "-H", "Content-Type: application/json", "-d", payload], timeout=20)
            if code in ("200", "204"):
                msg_done("Đã gửi nội dung thành công qua Webhook!")
            else:
                msg_err(f"Gửi webhook thất bại (mã phản hồi: {code or 'không kết nối được'}). Kiểm tra mạng rồi thử lại.")
        except Exception as e:
            msg_err(f"Lỗi gửi webhook: {e}")
        wait_enter("Ấn Enter để gửi tiếp / quay lại...")

# ==================== PERIODIC STATUS EMBED (5 MINUTES) ====================
def build_status_embed(packages):
    try:
        now = time.time()

        running_tabs = [p for p in packages if is_app_running(p)]
        total_uptime = now - START_UP_TIME.timestamp() if START_UP_TIME else 0
        total_rejoin = sum(REJOIN_COUNT.values())
        in_map_tabs = [p for p in running_tabs if p in JOINED_AT and is_app_in_foreground(p)]

        fields = []

        fields.append({
            "name": "📊 Trạng thái Tab",
            "value": f"**Chạy:** {len(running_tabs)}/{len(packages)} | **Trong Map:** {len(in_map_tabs)}",
            "inline": True
        })

        fields.append({
            "name": "⏱️ Thời gian chạy",
            "value": f"`{fmt_duration(int(total_uptime))}`",
            "inline": True
        })

        fields.append({
            "name": "🔄 Tổng rejoin",
            "value": f"**{total_rejoin}** lần",
            "inline": True
        })

        fields.append({
            "name": "🎮 Game",
            "value": f"{SELECTED_GAME_NAME or 'Chưa chọn'}",
            "inline": True
        })

        mode_label = "Auto rejoin" if AUTO_REJOIN_MODE == 1 else f"Delay {DELAY_REJOIN_MINUTES}p"
        fields.append({
            "name": "⚙️ Cơ chế",
            "value": mode_label,
            "inline": True
        })

        net_status = "🟢 Online" if is_online() else "🔴 Offline"
        fields.append({
            "name": "🌐 Mạng",
            "value": net_status,
            "inline": True
        })

        if running_tabs:
            tab_info = []
            for pkg in running_tabs[:5]:
                short = ALIASES.get(pkg) or pkg[len(PACKAGE_PREFIX):].lstrip(".")
                status = "🟢" if (pkg in JOINED_AT and is_app_in_foreground(pkg)) else "🟡"
                rj = REJOIN_COUNT.get(pkg, 0)
                tab_info.append(f"{status} {short} (RJ: {rj})")

            if tab_info:
                fields.append({
                    "name": "📱 Chi tiết tab",
                    "value": "\n".join(tab_info),
                    "inline": False
                })

        if GAME_STATUS_PAUSED:
            fields.append({
                "name": "⏸️ Trạng thái game",
                "value": f"**Tạm dừng:** {clip(GAME_STATUS_REASON, 80)}",
                "inline": False
            })

        if len(running_tabs) == 0:
            embed_color = 0xFF0000
        elif len(in_map_tabs) < len(running_tabs):
            embed_color = 0xFFD700
        else:
            embed_color = 0x00FF00

        embed_obj = {
            "title": "📋 Báo cáo trạng thái định kỳ (5 phút)",
            "description": f"Cập nhật tự động từ PAIN TOOL REJOIN VIP",
            "color": embed_color,
            "fields": fields,
            "footer": {"text": f"MADE BY PAIN • {VERSION} | Auto-report every 5 min"},
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        }

        return embed_obj

    except Exception as e:
        log_event("EMBED_ERR", detail=f"build_status_embed lỗi: {e}")
        return None

def send_periodic_status_embed(packages):
    if not WEBHOOK_URL:
        return

    try:
        embed_obj = build_status_embed(packages)
        if not embed_obj:
            return

        payload_dict = {
            "username": "PAIN TOOL REJOIN VIP",
            "avatar_url": "https://i.postimg.cc/gJbhCmHL/Pain-Gamer.png",
            "embeds": [embed_obj],
            "content": ""
        }

        payload_json = json.dumps(payload_dict, ensure_ascii=False)
        run_cmd([
            "curl", "-s", "-X", "POST", WEBHOOK_URL,
            "-H", "Content-Type: application/json",
            "-d", payload_json
        ], timeout=10)

        log_event("PERIODIC_EMBED", detail="Gửi báo cáo 5 phút thành công")

    except Exception as e:
        log_event("PERIODIC_EMBED_ERR", detail=f"Gửi periodic embed lỗi: {e}")

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
    out = run_cmd(["pm", "list", "packages"])
    pkgs = []
    for line in out.splitlines():
        if PACKAGE_PREFIX in line and ":" in line:
            pkgs.append(line.split(":", 1)[1].strip())
    return sorted(set(pkgs))

# ==================== ROOT / SHELL ====================
_ROOT_MODE = "unknown"

def root_mode():
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
    if root_mode() == "su":
        return run_cmd(["su", "-c", cmd], timeout=timeout)
    return run_cmd(["sh", "-c", cmd], timeout=timeout)

def sh_args(args, timeout=15, merge_stderr=False):
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
    markers = ("mCurrentFocus", "mFocusedApp", "mResumedActivity", "topResumedActivity")
    dump = sh("dumpsys window displays", timeout=5)
    if not any(m in dump for m in markers):
        dump = sh("dumpsys activity activities", timeout=5)
    if not any(m in dump for m in markers):
        return True
    return pkg in dump

def close_game(pkg):
    sh(f"am force-stop {pkg}")
    sh(f"am kill {pkg}")
    time.sleep(0.5)
    for _ in range(3):
        if not is_app_running(pkg):
            break
        sh(f"kill -9 $(pidof {pkg})", timeout=5)
        time.sleep(0.5)

def build_deep_link(pkg=None):
    link = (HOP_OVERRIDE.get(pkg) or HOP_CURRENT.get(pkg) or TARGET_LINK) if pkg else TARGET_LINK
    if not link:
        return None
    if link.startswith("roblox://") or link.startswith("http"):
        return link
    return f"roblox://placeId={link}"

def launch_commands(pkg, enter_map=True, soft=False):
    clear = [] if soft else ["--activity-clear-task"]
    deep_link = build_deep_link(pkg) if enter_map else None
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
    path = get_latest_log_file(pkg)
    LOG_STATE[pkg] = (path, get_file_size(path) if path else 0)
    LOGCAT_BASELINE[pkg] = time.time()
    LAST_ACTIVITY[pkg] = time.time()
    LAUNCHED_AT[pkg] = time.time()
    SCREEN_STATE.pop(pkg, None)
    JOINED_AT.pop(pkg, None)

def open_game(pkg, hard=False, enter_map=True):
    running = is_app_running(pkg)
    if hard and running:
        close_game(pkg)
        time.sleep(1)
        running = False
    if not running:
        key_ensure(pkg)
    mark_launched(pkg)
    if running:
        LAST_SOFT_JOIN[pkg] = time.time()
    for cmd in launch_commands(pkg, enter_map=enter_map, soft=running):
        out = sh_args(cmd, merge_stderr=True).lower()
        if not any(w in out for w in ("error", "exception", "unable to resolve", "unknown option")):
            return True
    return False

def quick_problem(pkg):
    if not is_app_running(pkg):
        return "Game bị tắt / crash (không còn tiến trình)"
    if not is_app_in_foreground(pkg):
        return "Không thấy cửa sổ game"
    has_error, reason = check_package_error(pkg)
    return reason if has_error else None

def retry_countdown(pkg, why):
    if NET_CHECK:
        stopped, _down = wait_for_network(pkg)
        if stopped:
            return True
    print(f"\033[1;33m[-] {tab_label(pkg)}: {why}. Sau {RETRY_COUNTDOWN_SECONDS}s sẽ tắt Đa nhiệm và vào lại...\033[0m")
    print("\033[1;33m    Đếm ngược: ", end="", flush=True)
    for sec in range(RETRY_COUNTDOWN_SECONDS, 0, -1):
        print(f"{sec}..", end=" ", flush=True)
        if wait_with_stop_check(1):
            print("\033[0m")
            return True
    print("\033[0m")
    return False

def join_map(pkg, hard=False):
    for attempt in range(1, LAUNCH_MAX_RETRY + 1):
        if stop_start:
            return False
        if NET_CHECK:
            stopped, _down = wait_for_network(pkg)
            if stopped:
                return False
        print(f"\033[1;33m[*] Vào Map {tab_label(pkg)} (lần {attempt}/{LAUNCH_MAX_RETRY})...\033[0m")
        open_game(pkg, hard=(hard or attempt > 1))

        started = False
        for _ in range(max(1, LAUNCH_VERIFY_SECONDS // 2)):
            if wait_with_stop_check(2):
                return False
            if is_app_running(pkg):
                started = True
                break
        if not started:
            print(f"\033[1;31m[!] {tab_label(pkg)} chưa lên sau {LAUNCH_VERIFY_SECONDS}s.\033[0m")
            log_event("JOIN_ERR", pkg, f"lần {attempt}/{LAUNCH_MAX_RETRY}: app không lên sau {LAUNCH_VERIFY_SECONDS}s")
            if attempt < LAUNCH_MAX_RETRY and retry_countdown(pkg, "Tab không lên được game"):
                return False
            continue

        print(f"\033[1;33m[*] {tab_label(pkg)} đã bật. Chờ {MAP_LOAD_WAIT}s để Map ổn định...\033[0m")
        problem = wait_map_load(pkg)
        if stop_start:
            return False
        if not problem:
            JOINED_AT[pkg] = time.time()
            print(f"\033[1;32m[+] {tab_label(pkg)} đã vào Map.\033[0m")
            return True
        if problem.startswith("VIP_DEAD:"):
            handle_vip_dead(pkg, problem[len("VIP_DEAD:"):].strip())
            return False
        print(f"\033[1;31m[!] {tab_label(pkg)} chưa vào được Map [{problem}].\033[0m")
        log_event("JOIN_ERR", pkg, f"lần {attempt}/{LAUNCH_MAX_RETRY}: {problem}")
        if attempt < LAUNCH_MAX_RETRY and retry_countdown(pkg, "Tab không vào lại được game"):
            return False

    print(f"\033[1;31m[!] Không vào được Map {tab_label(pkg)} sau {LAUNCH_MAX_RETRY} lần.\033[0m")
    update_ban_tracker(rejoin_failed=True)  # Track rejoin failure
    return False

# ==================== PHÁT HIỆN KICK / VĂNG / CRASH ====================
_CODE_REGEXES = [
    re.compile(r"error\s*code[:\s=]*\(?(\d{3})\b"),
    re.compile(r"disconnection\s*notification[^0-9\n]{0,40}(\d{3})\b"),
    re.compile(r"sending\s*disconnect\s*with\s*reason[:\s]*(\d{3})\b"),
    re.compile(r"\bcode[:\s=]+(\d{3})\b"),
]

def scan_text_for_problem(text, check_crash=False):
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

def scan_text_for_vip_dead(text):
    if not text:
        return False
    low = text.lower()
    return any(p in low for p in VIP_EXPIRED_PHRASES)

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
    global LOG_SOURCE_WORKS
    LAST_ACTIVITY[pkg] = time.time()
    LOG_SOURCE_WORKS = True

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
        offset = 0
    LOG_STATE[pkg] = (path, size)
    if size <= offset:
        return ""
    text = sh(f"tail -c +{offset + 1} '{path}'", timeout=8)
    if text:
        note_activity(pkg)
    return text

_EPOCH_RX = re.compile(r"^\s*(\d{9,11}\.\d+)")

def read_new_logcat_text(pkg):
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

def extract_error_codes(text):
    found = []
    for m in re.finditer(r"(?:error\s*code|errorcode|code|mã(?:\s*lỗi)?)\s*[:=]?\s*(\d{3})\b", text, re.I):
        if m.group(1) not in found:
            found.append(m.group(1))
    return found

def scan_crash_reason(pkg):
    path = get_latest_log_file(pkg)
    if not path:
        return None
    out = sh(f"tail -n 400 {shlex.quote(path)} 2>/dev/null", timeout=8) or ""
    codes, hit = [], None
    for line in reversed(out.splitlines()):
        low = line.lower()
        for c in extract_error_codes(line):
            if c not in codes:
                codes.append(c)
        if hit is None and (any(p in low for p in CRASH_PHRASES) or any(p in low for p in KICK_PHRASES)):
            hit = line.strip()[:160]
        if hit and codes:
            break
    parts = []
    if codes:
        parts.append("mã " + ", ".join(codes[:3]))
    if hit:
        parts.append(hit)
    return " · ".join(parts) if parts else None

def _crash_detail(pkg, base):
    try:
        detail = scan_crash_reason(pkg)
    except Exception:
        detail = None
    return f"{base} | {detail}" if detail else base

def detect_problem(pkg):
    if stop_start:
        return None
    if not is_app_running(pkg):
        return _crash_detail(pkg, "Tab bị tắt Đa nhiệm / Game crash (không còn tiến trình)")

    if not is_app_in_foreground(pkg):
        print(f"\033[1;33m[-] {tab_label(pkg)} bị thoát ra Màn hình chính/Lobby. Đang đếm ngược 5s...\033[0m")
        if wait_with_stop_check(5):
            return None
        if stop_start:
            return None
        if not is_app_running(pkg):
            return _crash_detail(pkg, "Tab bị tắt Đa nhiệm / Game crash (không còn tiến trình)")
        if not is_app_in_foreground(pkg):
            return "Bị thoát ra Màn hình chính / Lobby"
        return None

    has_error, reason = check_package_error(pkg)
    if has_error:
        # Track error 262 (soft ban indicator)
        if reason and "262" in str(reason):
            update_ban_tracker(error_code=262)
        return reason
    return None

def in_quiet_hours():
    if not QUIET_HOURS.get("enabled"):
        return False
    try:
        sh_, sm_ = map(int, str(QUIET_HOURS["start"]).split(":"))
        eh_, em_ = map(int, str(QUIET_HOURS["end"]).split(":"))
    except Exception:
        return False
    now = datetime.now()
    cur = now.hour * 60 + now.minute
    start, end = sh_ * 60 + sm_, eh_ * 60 + em_
    if start == end:
        return False
    if start < end:
        return start <= cur < end
    return cur >= start or cur < end

def archive_screenshot(tag):
    try:
        os.makedirs(SHOT_DIR, exist_ok=True)
        data = sh_bytes("screencap -p", timeout=20)
        if not data:
            return
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", tag)[:40].strip("_") or "alert"
        name = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + safe + ".png"
        with open(os.path.join(SHOT_DIR, name), "wb") as f:
            f.write(data)
        files = sorted(f for f in os.listdir(SHOT_DIR) if f.endswith(".png"))
        for old in files[:-SHOT_KEEP]:
            try:
                os.remove(os.path.join(SHOT_DIR, old))
            except Exception:
                pass
    except Exception:
        pass

def notify_async(level, title, description, pkg=None, reason=None, action=None, took=None, cooldown=None):
    if SCREEN_ARCHIVE.get("enabled") and level in PING_LEVELS:
        threading.Thread(target=archive_screenshot, args=(title,), daemon=True).start()
    if not WEBHOOK_URL:
        return
    key = (level, pkg, title)
    now = time.time()
    cd = cooldown if isinstance(cooldown, (int, float)) else ALERT_COOLDOWN_SEC
    if now - _ALERT_LAST.get(key, 0) < cd:
        return
    _ALERT_LAST[key] = now
    threading.Thread(target=send_detailed_alert, args=(level, title, description, pkg, reason, action, took), daemon=True).start()

def report_rejoin_result(pkg, ok, started, action):
    if stop_start:
        return
    took = int(time.time() - started)
    log_event("REJOIN_OK" if ok else "REJOIN_FAIL", pkg,
              f"{action}; mất {took}s" if ok else f"không vào được Map sau {LAUNCH_MAX_RETRY} lần thử ({action}); mất {took}s",
              rejoin=REJOIN_COUNT.get(pkg))
    if ok:
        notify_async("success", "Rejoin thành công", f"`{pkg}` đã vào lại Map.", pkg=pkg, action=action, took=took)
    else:
        notify_async("critical", "Rejoin thất bại", f"`{pkg}` không vào lại được Map sau {LAUNCH_MAX_RETRY} lần thử.",
                     pkg=pkg, reason=f"Không vào được Map sau {LAUNCH_MAX_RETRY} lần thử",
                     action="Tool tiếp tục theo dõi và sẽ thử lại", took=took)

def handle_vip_dead(pkg, problem):
    cur = HOP_CURRENT.get(pkg) or TARGET_LINK
    print(f"\033[1;31m[!] {tab_label(pkg)}: {problem}\033[0m")
    log_event("VIP_EXPIRED", pkg, problem, rejoin=REJOIN_COUNT.get(pkg))
    if cur in VIP_SERVERS:
        try:
            VIP_SERVERS.remove(cur)
            save_config_file()
        except ValueError:
            pass
        action = f"Đã tự gỡ link VIP server này khỏi danh sách xoay vòng (còn {len(VIP_SERVERS)} link)."
        if VIP_SERVERS:
            nxt, _kind, desc = pick_hop_target(pkg)
            if nxt:
                HOP_CURRENT[pkg] = nxt
                action += f" Lần vào map kế tiếp sẽ dùng {desc}."
    else:
        action = "Đây là link/ID chính ở mục Set up > Chọn game. Hãy đổi sang link VIP server mới."
    notify_async("critical", "VIP Server đã hết hạn", f"`{pkg}`: {problem}", pkg=pkg, reason=problem, action=action)

def recover_tab(pkg, reason):
    if stop_start:
        return
    running = is_app_running(pkg)
    recently_soft = (time.time() - LAST_SOFT_JOIN.get(pkg, 0)) < 90
    hard = running and ("Crash" in reason or recently_soft or is_screen_reason(reason))
    if not running:
        action = "Tab đã tắt, mở lại và vào Map"
    elif hard:
        action = "Tắt hẳn tab rồi vào lại Map"
    else:
        action = "Tab còn mở, chỉ vào lại Map (không tắt Đa nhiệm)"

    level = classify_reason(reason)
    REJOIN_COUNT[pkg] = REJOIN_COUNT.get(pkg, 0) + 1
    m_code = re.search(r"Mã Lỗi (\d{3})", reason)
    log_event("LOBBY" if level == "lobby" else ("SCREEN" if is_screen_reason(reason) else "KICK"), pkg, f"{reason} -> {action}",
              code=m_code.group(1) if m_code else None, rejoin=REJOIN_COUNT[pkg])
    color = "\033[1;33m" if level == "lobby" else "\033[1;31m"
    print(f"{color}[-] Phát hiện {tab_label(pkg)} lỗi [{reason}]! {action}...\033[0m")
    notify_async(level, alert_title_for(reason, level), f"`{pkg}` gặp sự cố, tool đang xử lý.",
                 pkg=pkg, reason=reason, action=action)
    
    if MONITOR_ONLY:
        log_event("MONITOR", pkg, f"chỉ theo dõi: không rejoin ({reason})")
        return
    # Apply per-package game profile trước khi rejoin
    game_name = get_game_for_package(pkg)
    if game_name and game_name in GAME_PROFILES:
        apply_game_profile(game_name)
    
    started = time.time()
    ok = join_map(pkg, hard=hard)
    report_rejoin_result(pkg, ok, started, action)

# ==================== BACKUP / RESTORE DATA TAB ====================
def backup_path(pkg, prev=False):
    return f"{BACKUP_DIR}/{pkg}{'.prev' if prev else ''}.tar"

def backup_size(pkg, prev=False):
    return get_file_size(backup_path(pkg, prev))

def backup_info(pkg):
    size = backup_size(pkg)
    if size <= 0:
        return None
    when = sh(f"stat -c %y '{backup_path(pkg)}'", timeout=5).split(".")[0]
    return size, when

def _tar_rc(out):
    m = re.search(r"__RC__(\d+)", out or "")
    return int(m.group(1)) if m else -1

def backup_tab(pkg, stop_first=False):
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
    if _tar_rc(out) not in (0, 1) or get_file_size(tmp) <= 0:
        sh(f"rm -f {shlex.quote(tmp)}", timeout=8)
        return False, "tar lỗi (thiếu dung lượng hoặc không ghi được vào /sdcard)"
    sh(f"[ -f {shlex.quote(cur)} ] && mv -f {shlex.quote(cur)} {shlex.quote(prev)}; mv -f {shlex.quote(tmp)} {shlex.quote(cur)}", timeout=15)
    size = backup_size(pkg)
    if size <= 0:
        return False, "không lưu được file backup"
    return True, f"{round(size / 1024 / 1024, 1)} MB"

def restore_tab(pkg, prev=False, clear_first=True):
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
    sh(f"chown -R {owner} {data_dir}", timeout=60)
    sh(f"restorecon -R {data_dir} 2>/dev/null", timeout=60)
    return True, "đã khôi phục dữ liệu"

def should_auto_backup(pkg):
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
    if not (AUTO_CLEAR_DATA and LOG_SOURCE_WORKS):
        return False
    if not is_app_running(pkg):
        return False
    last = LAST_ACTIVITY.get(pkg)
    if last is None:
        LAST_ACTIVITY[pkg] = time.time()
        return False
    return (time.time() - last) >= FREEZE_TIMEOUT_MIN * 60

def recover_frozen_tab(pkg):
    if MONITOR_ONLY:
        log_event("MONITOR", pkg, "chỉ theo dõi: bỏ qua xử lý tab treo")
        return
    now = time.time()
    in_cooldown = (now - LAST_CLEAR.get(pkg, 0)) < CLEAR_COOLDOWN_SEC
    has_backup = bool(root_mode()) and (backup_size(pkg) > 0 or backup_size(pkg, prev=True) > 0)
    reason = f"Tab treo hơn {FREEZE_TIMEOUT_MIN} phút không có log"
    REJOIN_COUNT[pkg] = REJOIN_COUNT.get(pkg, 0) + 1
    log_event("FREEZE", pkg, reason, rejoin=REJOIN_COUNT[pkg])
    started = time.time()

    if has_backup and not in_cooldown:
        action = "Xóa data (pm clear) → khôi phục backup → mở lại vào Map"
        print(f"\033[1;31m[!] {tab_label(pkg)} treo > {FREEZE_TIMEOUT_MIN} phút không có log! Xóa data (pm clear) → khôi phục backup → mở lại...\033[0m")
        notify_async("critical", "Tab treo cứng", f"`{pkg}` treo, tool đang khôi phục.", pkg=pkg, reason=reason, action=action)
        LAST_CLEAR[pkg] = now
        ok, msg = restore_tab(pkg, prev=False)
        if not ok and backup_size(pkg, prev=True) > 0:
            ok, msg = restore_tab(pkg, prev=True)
        if ok:
            print(f"\033[1;32m[+] {tab_label(pkg)}: {msg}.\033[0m")
        else:
            NEEDS_LOGIN.add(pkg)
            print(f"\033[1;31m[!] {tab_label(pkg)}: khôi phục lỗi ({msg}). Tab có thể mất login, cần đăng nhập lại.\033[0m")
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
    print(f"\033[1;31m[!] {tab_label(pkg)} treo > {FREEZE_TIMEOUT_MIN} phút không có log ({why}) → chỉ tắt hẳn tab rồi mở lại.\033[0m")
    notify_async("critical", "Tab treo cứng", f"`{pkg}` treo, tool tắt tab và mở lại (không xóa data).",
                 pkg=pkg, reason=f"{reason} ({why})", action=action)
    close_game(pkg)
    joined = join_map(pkg, hard=True)
    report_rejoin_result(pkg, joined, started, action)

# ==================== VÒNG LẶP CHÍNH ====================
def listen_for_stop(gen=None):
    global stop_start

    def alive():
        return not stop_start and (gen is None or gen == _LISTENER_GEN)

    while alive():
        try:
            try:
                ready, _, _ = select.select([sys.stdin], [], [], 1)
            except Exception:
                ready = [sys.stdin]
            if not ready:
                continue
            line = sys.stdin.readline()
            if not line:
                break
            user_input = line.strip().lower()
            if user_input == "0":
                stop_start = True
                break
            elif user_input in ("s", "status"):
                print_status_table()
        except Exception:
            break

def wait_with_stop_check(seconds, message=""):
    if message:
        print(message)
    for _ in range(seconds):
        if stop_start:
            return True
        time.sleep(1)
    return False

def update_ban_tracker(error_code=None, rejoin_failed=False, cookie_changed=False):
    """Update ban tracking metrics - phát hiện mẫu bị ban"""
    global BAN_TRACKER
    
    current_time = time.time()
    
    # Track lỗi 262 (soft ban indicator)
    if error_code == 262:
        BAN_TRACKER["error_262_count"] += 1
        BAN_TRACKER["error_262_streak"] += 1
        if BAN_TRACKER["error_262_streak"] >= 3:
            BAN_TRACKER["ban_warning"] = "CẢNH BÁO: Có thể bị SOFT BAN (3+ lỗi 262)"
    else:
        BAN_TRACKER["error_262_streak"] = 0
    
    # Track rejoin failures
    if rejoin_failed:
        BAN_TRACKER["rejoin_fail_count"] += 1
        if BAN_TRACKER["rejoin_fail_count"] >= 5:
            BAN_TRACKER["is_paused"] = True
            BAN_TRACKER["pause_until"] = current_time + 300  # 5 phút
            BAN_TRACKER["ban_warning"] = "DỪNG 5 PHÚT: Rejoin thất bại 5 lần - tránh HARD BAN"
    
    # Track cookie changes
    if cookie_changed:
        BAN_TRACKER["cookie_change_count"] += 1
        BAN_TRACKER["cookie_change_time"].append(current_time)
        
        # Clean up old timestamps (keep last 1 hour)
        cutoff = current_time - 3600
        BAN_TRACKER["cookie_change_time"] = [t for t in BAN_TRACKER["cookie_change_time"] if t > cutoff]
        
        if len(BAN_TRACKER["cookie_change_time"]) >= 10:
            BAN_TRACKER["ban_warning"] = "CẢNH BÁO: Thay cookie 10+ lần/giờ - Roblox canh"
    
    # Calculate ban risk percentage
    risk = 0
    if BAN_TRACKER["error_262_streak"] >= 3:
        risk += 35
    if BAN_TRACKER["rejoin_fail_count"] >= 5:
        risk += 40
    if len(BAN_TRACKER["cookie_change_time"]) >= 10:
        risk += 25
    
    BAN_TRACKER["ban_risk_percent"] = min(risk, 100)
    
    # Auto pause if risk > 45%
    if BAN_TRACKER["ban_risk_percent"] > 45 and not BAN_TRACKER["is_paused"]:
        BAN_TRACKER["is_paused"] = True
        BAN_TRACKER["pause_until"] = current_time + 300
        BAN_TRACKER["ban_warning"] = f"AUTO PAUSE: Ban risk {BAN_TRACKER['ban_risk_percent']}% - Tạm dừng 5 phút"

def check_ban_status():
    """Check và display ban status - hiển thị trạng thái hiện tại"""
    global BAN_TRACKER
    
    current_time = time.time()
    
    # Check if pause timeout elapsed
    if BAN_TRACKER["is_paused"] and current_time > BAN_TRACKER["pause_until"]:
        BAN_TRACKER["is_paused"] = False
        BAN_TRACKER["ban_warning"] = ""
        BAN_TRACKER["rejoin_fail_count"] = 0
        print("[✓] Pause kết thúc - An toàn, tiếp tục...")
    
    if BAN_TRACKER["is_paused"]:
        remaining = int(BAN_TRACKER["pause_until"] - current_time)
        print(f"[!] PAUSED: {remaining}s còn lại - {BAN_TRACKER['ban_warning']}")
        return False
    
    if BAN_TRACKER["ban_risk_percent"] > 0:
        status = "NGUY HIỂM" if BAN_TRACKER["ban_risk_percent"] > 70 else "CẢNH BÁO" if BAN_TRACKER["ban_risk_percent"] > 45 else "AN TOÀN"
        print(f"[*] Ban risk: {BAN_TRACKER['ban_risk_percent']}% {status}")
        if BAN_TRACKER["ban_warning"]:
            print(f"    {BAN_TRACKER['ban_warning']}")
        return BAN_TRACKER["ban_risk_percent"] <= 45
    
    print("[✓] An toàn - Không phát hiện rủi ro")
    return True

def display_ban_stats():
    """Hiển thị thống kê ban tracking"""
    print("\n" + "="*60)
    print("BAN PATTERN TRACKING STATS")
    print("="*60)
    print(f"Lỗi 262 liên tiếp:        {BAN_TRACKER['error_262_streak']}/3 (nếu ≥3)")
    print(f"Rejoin thất bại:          {BAN_TRACKER['rejoin_fail_count']}/5 (dừng nếu ≥5)")
    print(f"Cookie thay đổi/giờ:      {len(BAN_TRACKER['cookie_change_time'])}/10 (nếu ≥10)")
    print(f"Ban risk:                 {BAN_TRACKER['ban_risk_percent']}% ", end="")
    if BAN_TRACKER["ban_risk_percent"] > 70:
        print("NGUY HIỂM")
    elif BAN_TRACKER["ban_risk_percent"] > 45:
        print("CẢNH BÁO")
    else:
        print("AN TOÀN")
    if BAN_TRACKER["ban_warning"]:
        print(f"Cảnh báo:                 {BAN_TRACKER['ban_warning']}")
    print("="*60 + "\n")

def reset_ban_tracker():
    """Reset ban tracking - sử dụng khi muốn reset toàn bộ"""
    global BAN_TRACKER
    BAN_TRACKER = {
        "error_262_count": 0,
        "error_262_streak": 0,
        "rejoin_fail_count": 0,
        "cookie_change_count": 0,
        "cookie_change_time": [],
        "ban_risk_percent": 0,
        "ban_warning": "",
        "last_reset_time": time.time(),
        "is_paused": False,
        "pause_until": 0
    }
    print("[✓] Ban tracking reset")

def menu_package_operation():
    """Menu quản lý packages - nhập packages + chọn số lượng chạy"""
    global SELECTED_PACKAGES, SELECT_ALL_PACKAGES, PACKAGE_GAMES, PACKAGE_PREFIX
    
    while True:
        os.system("clear" if os.name == "posix" else "cls")
        print("\n" + "="*60)
        print("QUẢN LÝ PACKAGES")
        print("="*60)
        
        packages_list = list(PACKAGE_GAMES.keys()) if PACKAGE_GAMES else []
        
        print(f"\nPrefix hiện tại: {PACKAGE_PREFIX}")
        print(f"Tổng packages: {len(packages_list)}")
        
        if SELECTED_PACKAGES:
            print(f"Chạy: {len(SELECTED_PACKAGES)} package(s)")
            for i, pkg in enumerate(SELECTED_PACKAGES, 1):
                print(f"  {i}. {pkg}")
        else:
            print("Chạy: Tất cả packages")
        
        print("\n" + "-"*60)
        print("1. Nhập package")
        print("2. Chọn package muốn chạy")
        print("q. Quay lại menu chính")
        print("-"*60)
        
        choice = input("\nChọn: ").strip().lower()
        
        if choice == 'q':
            break
        elif choice == '1':
            menu_choose_game_with_package()
        elif choice == '2':
            menu_select_package_count()
        else:
            print("Lựa chọn không hợp lệ")
            time.sleep(1)

def menu_select_mode():
    """Menu chọn chế độ: Custom Count hoặc Selective"""
    global SELECTED_PACKAGES, SELECT_ALL_PACKAGES, PACKAGE_GAMES
    
    packages_list = list(PACKAGE_GAMES.keys())
    if not packages_list:
        print("\nChưa có packages nào")
        time.sleep(1)
        return
    
    os.system("clear" if os.name == "posix" else "cls")
    print("\n" + "="*60)
    print("CHỌN CHẾ ĐỘ CHẠY PACKAGES")
    print("="*60)
    print(f"\nTổng cộng: {len(packages_list)} packages khả dụng\n")
    
    print("1. Custom Count Mode")
    print("   → Nhập số N để chạy N packages đầu tiên")
    print("   → Ví dụ: nhập 5 → chạy packages 1-5\n")
    
    print("2. Selective Mode")
    print("   → Chọn riêng packages muốn chạy")
    print("   → Ví dụ: chọn 1, 3, 5 → chỉ chạy packages này\n")
    
    print("q. Quay lại menu chính\n")
    
    choice = input("Chọn chế độ [1/2/q]: ").strip().lower()
    
    if choice == '1':
        menu_custom_count_mode(packages_list)
    elif choice == '2':
        menu_selective_mode(packages_list)
    elif choice == 'q':
        return
    else:
        print("Lựa chọn không hợp lệ")
        time.sleep(1)

def menu_custom_count_mode(packages_list):
    """Chế độ Custom Count: user nhập số N để chạy N packages đầu"""
    global SELECTED_PACKAGES, SELECT_ALL_PACKAGES
    
    os.system("clear" if os.name == "posix" else "cls")
    print("\n" + "="*60)
    print("CUSTOM COUNT MODE - CHẠY N PACKAGES ĐẦU")
    print("="*60)
    print(f"\nTổng cộng: {len(packages_list)} packages khả dụng\n")
    
    for i, pkg in enumerate(packages_list, 1):
        print(f"{i:2}. {pkg}")
    
    print("\n" + "-"*60)
    print("Cách sử dụng:")
    print("  • Nhập số: Chạy N packages đầu (ví dụ: 5 → chạy 5 packages đầu)")
    print("  • Nhập 0: Chạy tất cả packages")
    print("  • Nhập q: Quay lại")
    print("-"*60)
    
    user_input = input("\nNhập số lượng (0 = tất cả): ").strip().lower()
    
    if user_input == 'q':
        return
    
    try:
        count = int(user_input)
        if count == 0:
            SELECTED_PACKAGES = packages_list.copy()
            SELECT_ALL_PACKAGES = True
            print(f"\nChạy tất cả {len(packages_list)} packages")
        elif 1 <= count <= len(packages_list):
            SELECTED_PACKAGES = packages_list[:count]
            SELECT_ALL_PACKAGES = False
            print(f"\nChạy {count} packages đầu:")
            for i, pkg in enumerate(SELECTED_PACKAGES, 1):
                print(f"    {i}. {pkg}")
        else:
            print(f"Số không hợp lệ (1-{len(packages_list)})")
            time.sleep(1)
            return
        
        time.sleep(2)
    except ValueError:
        print("Vui lòng nhập số")
        time.sleep(1)

def menu_selective_mode(packages_list):
    """Chế độ Selective: user chọn riêng packages muốn chạy"""
    global SELECTED_PACKAGES, SELECT_ALL_PACKAGES
    
    selected = []
    
    while True:
        os.system("clear" if os.name == "posix" else "cls")
        print("\n" + "="*60)
        print("SELECTIVE MODE - CHỌN PACKAGES RIÊNG")
        print("="*60)
        print(f"\nTổng cộng: {len(packages_list)} packages khả dụng")
        print(f"Đã chọn: {len(selected)} packages\n")
        
        # Hiển thị danh sách với dấu ✓
        for i, pkg in enumerate(packages_list, 1):
            mark = "✓" if pkg in selected else " "
            print(f"{i:2}. [{mark}] {pkg}")
        
        print("\n" + "-"*60)
        print("Nhập số để chọn/bỏ chọn (ví dụ: 1 2 4 hoặc 1,2,4)")
        print("  • Nhập 'ok': Xác nhận và lưu lựa chọn")
        print("  • Nhập 'reset': Xóa tất cả lựa chọn")
        print("  • Nhập 'q': Hủy và quay lại")
        print("-"*60)
        
        user_input = input("\nNhập lựa chọn: ").strip().lower()
        
        if user_input == 'q':
            return
        elif user_input == 'ok':
            if not selected:
                print("Chưa chọn packages nào")
                time.sleep(1)
                continue
            SELECTED_PACKAGES = selected.copy()
            SELECT_ALL_PACKAGES = False
            print(f"\nĐã chọn {len(selected)} packages:")
            for pkg in selected:
                print(f"    • {pkg}")
            time.sleep(2)
            return
        elif user_input == 'reset':
            selected = []
            print("✓ Đã xóa tất cả lựa chọn")
            time.sleep(1)
        else:
            # Parse input: "1 2 3" hoặc "1,2,3"
            try:
                indices = []
                for part in user_input.replace(',', ' ').split():
                    idx = int(part.strip())
                    if 1 <= idx <= len(packages_list):
                        indices.append(idx - 1)
                    else:
                        print(f"Số {idx} không hợp lệ (1-{len(packages_list)})")
                        time.sleep(1)
                        continue
                
                # Toggle selection
                for idx in indices:
                    pkg = packages_list[idx]
                    if pkg in selected:
                        selected.remove(pkg)
                        print(f"Đã bỏ chọn: {pkg}")
                    else:
                        selected.append(pkg)
                        print(f"Đã thêm: {pkg}")
                    time.sleep(0.3)
                
                time.sleep(1)
            except ValueError:
                print("Vui lòng nhập số (ví dụ: 1 2 3)")
                time.sleep(1)

def menu_select_package_count():
    """Menu chọn packages - gọi hàm selector chế độ"""
    menu_select_mode()

def get_active_packages():
    """Trả về danh sách packages cần chạy (filtered by selection)"""
    global SELECTED_PACKAGES, SELECT_ALL_PACKAGES
    
    if SELECT_ALL_PACKAGES or not SELECTED_PACKAGES:
        return list(PACKAGE_GAMES.keys())
    else:
        return SELECTED_PACKAGES

def launch_all(packages, hard=False):
    # Check ban status before launching
    if not check_ban_status():
        print(f"[!] Tool PAUSED do ban risk. Không thể khởi chạy.")
        return
    
    # Filter packages by user selection
    active_packages = [pkg for pkg in packages if pkg in get_active_packages()]
    if not active_packages:
        print("[!] Không có packages được chọn. Vui lòng chọn packages.")
        return
    
    total = len(active_packages)
    packages = active_packages  # Use filtered list
    if total >= 4:
        batch_size = 3
        for i in range(0, total, batch_size):
            if stop_start: break
            for idx_b, pkg in enumerate(packages[i:i + batch_size]):
                if stop_start: break
                print(f"\033[1;36m[*] Đang khởi chạy Tab [{i + idx_b + 1}/{total}]: {tab_label(pkg)}\033[0m")
                join_map(pkg, hard=hard)
            if i + batch_size < total and not stop_start:
                print(f"\033[1;33m[*] Chờ 15 giây để mở nhóm tiếp theo...\033[0m")
                if wait_with_stop_check(15): break
    else:
        for idx, pkg in enumerate(packages):
            if stop_start: break
            print(f"\033[1;36m[*] Đang khởi chạy Tab [{idx + 1}/{total}]: {tab_label(pkg)}\033[0m")
            join_map(pkg, hard=hard)
            if idx < total - 1:
                print(f"\033[1;33m[*] Chờ {CLONE_LAUNCH_DELAY}s...\033[0m")
                if wait_with_stop_check(CLONE_LAUNCH_DELAY): break

# ==================== KIỂM TRA TRƯỚC KHI START ====================
# Điền package của từng executor nếu muốn tool kiểm tra app đã cài chưa, ví dụ {"Delta": "com.example.delta"}
EXECUTOR_PACKAGE_MAP = {}

def preflight_items():
    """Trả về danh sách (trạng thái, bắt buộc, nội dung). Trạng thái: ok / warn / fail."""
    items = []
    installed = list_installed_packages()
    if installed:
        items.append(("ok", True, f"Tab clone: {len(installed)} tab"))
    else:
        items.append(("fail", True, f"Không có tab clone nào (prefix: {PACKAGE_PREFIX})"))

    if not SELECT_ALL_PACKAGES and not SELECTED_PACKAGES:
        items.append(("fail", True, "Chưa chọn packages nào để chạy"))

    if TARGET_LINK:
        items.append(("ok", False, f"Game: {SELECTED_GAME_NAME or TARGET_LINK}"))
    else:
        items.append(("warn", False, "Chưa chọn game: tool chỉ mở app, không vào Map"))

    if webhook_active():
        items.append(("ok", False, "Webhook: đã cài"))
    else:
        items.append(("warn", False, "Chưa cài Webhook: không nhận được cảnh báo"))

    bound = {p: e for p, e in EXECUTOR_BINDING.items() if e in EXECUTOR_NAMES}
    if not bound:
        items.append(("warn", False, "Chưa gán executor cho tab nào"))
    else:
        items.append(("ok", False, f"Executor đã gán: {len(bound)} tab"))
        if EXECUTOR_PACKAGE_MAP:
            pm_out = run_cmd(["pm", "list", "packages"])
            present = {line.split(":", 1)[1].strip() for line in pm_out.splitlines() if ":" in line}
            for exe in sorted(set(bound.values())):
                pkg_exe = EXECUTOR_PACKAGE_MAP.get(exe)
                if pkg_exe and pkg_exe not in present:
                    items.append(("warn", False, f"Executor {exe} chưa được cài trên máy"))
    return items

def preflight_gate():
    """Hiện bảng kiểm tra. Trả về True nếu được phép Start."""
    clear_screen()
    section_title("KIỂM TRA TRƯỚC KHI START")
    items = preflight_items()
    icon = {"ok": f"{C.GRN}✓{C.R}", "warn": f"{C.YEL}!{C.R}", "fail": f"{C.RED}✗{C.R}"}
    for status, _req, text in items:
        print(f" {icon[status]} {text}")
    print()
    if any(st == "fail" for st, _r, _t in items):
        msg_err("Chưa đủ điều kiện để Start. Sửa các mục ✗ rồi thử lại.")
        wait_enter()
        return False
    if any(st == "warn" for st, _r, _t in items):
        ans = ask("Vẫn tiếp tục Start? [y/N]:").strip().lower()
        return ans in ("y", "yes")
    return True

def start_tool():
    global stop_start, START_UP_TIME, CYCLE_START, STOP_REASON, _LISTENER_GEN, NEXT_AUTO_RESTART, _HOP_LAG, _HOP_PAUSE_UNTIL
    global GAME_STATUS_PAUSED, GAME_STATUS_REASON, RUN_LIMIT_HOURS
    if not preflight_gate():
        return
    RUN_LIMIT_HOURS = float(STOP_TIMER["hours"]) if STOP_TIMER.get("enabled") and float(STOP_TIMER.get("hours") or 0) > 0 else 0
    if RUN_LIMIT_HOURS:
        msg_info(f"Giới hạn thời gian chạy: {RUN_LIMIT_HOURS:g} giờ" + (" (sẽ tắt các clone khi hết giờ)" if STOP_TIMER.get("close_apps") else ""))
    stop_start = False
    CYCLE_START = None
    STOP_REASON = ""
    GAME_STATUS_PAUSED = False
    GAME_STATUS_REASON = ""
    _LISTENER_GEN += 1
    gen = _LISTENER_GEN
    if _valid_hhmm(SCHEDULE.get("start")) and datetime.now() >= _today_at(SCHEDULE["start"]):
        SCHED_FIRED["start"] = datetime.now().date()
    clear_screen()
    print_ascii_banner()
    packages = get_all_packages()
    START_UP_TIME = datetime.now()
    log_event("START", detail=f"{len(packages)} tab | game={SELECTED_GAME_NAME} | {get_rejoin_mode_str()}")
    for state in (LOG_STATE, LOGCAT_BASELINE, LAST_ACTIVITY, LAST_CLEAR, LAST_SOFT_JOIN, JOINED_AT, LAST_BACKUP, REJOIN_COUNT, SCREEN_STATE, LAUNCHED_AT, SCREEN_COOLDOWN, ANR_SEEN, HOP_OVERRIDE, HOP_CURRENT, HOP_LAST):
        state.clear()
    HOP_LOG.clear()
    _HOP_LAG = 0
    _HOP_PAUSE_UNTIL = 0

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
    if LOW_RAM_ALERT:
        print(f"\033[1;32m[*] Cảnh báo RAM thấp: BẬT (dưới {LOW_RAM_MB} MB{', tự dọn cache' if LOW_RAM_AUTO_CLEAN else ''}).\033[0m")
    if _valid_hhmm(SCHEDULE.get("stop")):
        print(f"\033[1;32m[*] Hẹn giờ tự dừng: {SCHEDULE['stop']}\033[0m")
    if AUTO_RESTART_HOURS:
        print(f"\033[1;32m[*] Lịch tự động restart: {auto_restart_label()}.\033[0m")
    if KEY_FILES:
        print(f"\033[1;32m[*] Key Injector: {key_label()} (tự chèn lại key khi bị reset / xóa data).\033[0m")
    if WB_DETECT or OVERLAY_DETECT:
        if root_mode():
            print(f"\033[1;32m[*] Phát hiện màn hình: {screen_guard_label()} (quét mỗi {SCREEN_CHECK_SEC}s, chế độ 1).\033[0m")
        else:
            print("\033[1;31m[!] Máy không có root: phát hiện trắng/đen / GUI đứng không hoạt động.\033[0m")
    if GFX_AUTO and (GFX_LOW or GFX_FPS):
        print(f"\033[1;32m[*] Graphics Optimizer tự áp dụng: {gfx_settings_label()}.\033[0m")
    if BLACK_SCREEN:
        print("\033[1;32m[*] Black Screen: BẬT (hạ độ sáng về 0 sau khi các tab đã vào map; bấm 0 để dừng thì trả lại độ sáng).\033[0m")
    if SERVER_HOP:
        print(f"\033[1;32m[*] Auto Server Hop: BẬT (độ trễ > {HOP_PING_MS}ms {HOP_CHECKS} lần liên tiếp thì đổi server; {len(VIP_SERVERS)} VIP server).\033[0m")
    report_on = webhook_active()
    if report_on:
        print("\033[1;32m[*] Báo cáo Discord (kèm ảnh chụp màn hình) mỗi 5 phút: BẬT.\033[0m")
    else:
        print("\033[1;33m[*] Báo cáo Discord mỗi 5 phút: TẮT (chưa set Webhook URL, tool sẽ không chụp ảnh màn hình).\033[0m")
    if report_on:
        print("\033[1;32m[*] Cảnh báo Discord: BẬT  \033[1;31m● Đỏ\033[0m Kick/Crash  \033[1;33m● Vàng\033[0m Lobby  \033[1;32m● Xanh\033[0m Rejoin thành công")
    if len(packages) >= 4:
        print(f"\033[1;33m[*] Số lượng tab >= 4, áp dụng mở nhóm 3 tab, cách nhau 15 giây.\033[0m")
    else:
        print(f"\033[1;33m[*] Delay mở mỗi tab clone: {CLONE_LAUNCH_DELAY} giây.\033[0m")
    print("\033[1;33m[*] Bấm 0 + Enter để dừng Start  |  Bấm s + Enter để xem bảng trạng thái các tab.\033[0m")
    print(f"\033[1;33m[*] Nhật ký ghi tại: {LOG_FILE}\033[0m")
    print("--------------------------------------------------")

    listener = threading.Thread(target=listen_for_stop, args=(gen,), daemon=True)
    listener.start()

    def _on_kill_signal(signum, frame):
        name = signal.Signals(signum).name
        log_event("STOP", detail=f"Nhận tín hiệu {name} (Termux bị đóng / tool bị kill)")
        notify_tool_stopped(f"Tool bị đóng đột ngột (tín hiệu {name})", unexpected=True)
        raise SystemExit(0)

    old_handlers = {}
    for sig_name in ("SIGTERM", "SIGHUP"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try:
                old_handlers[sig] = signal.signal(sig, _on_kill_signal)
            except Exception:
                pass

    apply_gfx_on_start(packages)
    key_ensure_all(packages)
    launch_all(packages)

    if not stop_start and report_on:
        send_webhook(f"Bắt đầu theo dõi {len(packages)} tab clone.", with_image=True)

    start_time = time.time()
    CYCLE_START = start_time
    last_auto_restart = start_time
    NEXT_AUTO_RESTART = start_time + AUTO_RESTART_HOURS * 3600 if AUTO_RESTART_HOURS else None
    last_webhook_time = time.time()
    last_cleanup_time = time.time()
    last_packages_time = time.time()
    last_freeze_check = 0
    last_backup_check = time.time()
    last_ram_check = 0
    last_key_save = time.time()
    last_hop_check = time.time()
    last_game_status_check = 0
    last_version_check = time.time()
    last_countdown = time.time()
    check_app_versions(packages)

    try:
        if BLACK_SCREEN and not stop_start:
            ok_bs, msg_bs = black_screen_on()
            col_bs = "\033[1;32m[✓]" if ok_bs else "\033[1;31m[!]"
            print(f"{col_bs} Black Screen: {msg_bs}.\033[0m")
            log_event("BLACKSCREEN", detail=f"bật: {msg_bs}" if ok_bs else f"không bật được: {msg_bs}")
        while not stop_start:
            if schedule_stop_due():
                STOP_REASON = "schedule"
                print(f"\n\033[1;33m[*] Đến giờ hẹn dừng {SCHEDULE['stop']}, đang dừng Start...\033[0m")
                stop_start = True
                break
            if RUN_LIMIT_HOURS and START_UP_TIME and (datetime.now() - START_UP_TIME).total_seconds() >= RUN_LIMIT_HOURS * 3600:
                STOP_REASON = "duration"
                print(f"\n\033[1;33m[*] Đã chạy đủ {RUN_LIMIT_HOURS:g} giờ, đang dừng Start...\033[0m")
                stop_start = True
                break
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

            if TARGET_LINK and not stop_start and (current_time - last_game_status_check) >= GAME_STATUS_CHECK_SEC:
                last_game_status_check = current_time
                threading.Thread(target=check_game_status, daemon=True).start()

            if GAME_STATUS_PAUSED:
                pass
            elif AUTO_REJOIN_MODE == 1:
                for pkg in packages:
                    if stop_start: break
                    reason = detect_problem(pkg)
                    if reason:
                        recover_tab(pkg, reason)
                if not stop_start:
                    for pkg, why_screen in screen_guard(packages):
                        if stop_start: break
                        recover_tab(pkg, why_screen)

            elif AUTO_REJOIN_MODE == 2:
                if elapsed_minutes >= DELAY_REJOIN_MINUTES:
                    print(f"\033[1;33m[*] Chu kỳ {DELAY_REJOIN_MINUTES}p hoàn tất. Tắt Đa nhiệm và vào lại Map toàn bộ tab...\033[0m")
                    for _p in packages:
                        REJOIN_COUNT[_p] = REJOIN_COUNT.get(_p, 0) + 1
                        # Apply per-package game profile trước khi rejoin Mode 2
                        game_name = get_game_for_package(_p)
                        if game_name and game_name in GAME_PROFILES:
                            apply_game_profile(game_name)
                    log_event("CYCLE", detail=f"Hết chu kỳ {DELAY_REJOIN_MINUTES}p, tắt Đa nhiệm và vào lại {len(packages)} tab")
                    launch_all(packages, hard=True)
                    start_time = time.time()
                    CYCLE_START = start_time

            if not stop_start and not MONITOR_ONLY and auto_restart_due(last_auto_restart):
                do_auto_restart(packages)
                last_auto_restart = time.time()
                NEXT_AUTO_RESTART = last_auto_restart + AUTO_RESTART_HOURS * 3600
                if AUTO_RESTART_ACTION == "reset":
                    start_time = last_auto_restart
                    CYCLE_START = start_time
                if stop_start:
                    break

            if AUTO_CLEAR_DATA and not stop_start and (time.time() - last_freeze_check) >= 10:
                last_freeze_check = time.time()
                net_down = NET_CHECK and not is_online()
                for pkg in packages:
                    if stop_start: break
                    if AUTO_REJOIN_MODE == 2:
                        collect_new_logs(pkg)
                    if net_down:
                        LAST_ACTIVITY[pkg] = time.time()
                    elif is_tab_frozen(pkg):
                        recover_frozen_tab(pkg)

            if AUTO_BACKUP and not stop_start and (time.time() - last_backup_check) >= 60:
                last_backup_check = time.time()
                for pkg in packages:
                    if stop_start: break
                    if is_app_running(pkg) and should_auto_backup(pkg):
                        ok, msg = backup_tab(pkg)
                        LAST_BACKUP[pkg] = time.time()
                        color = "\033[1;32m[+]" if ok else "\033[1;31m[!]"
                        print(f"{color} Auto Backup {tab_label(pkg)}: {msg}\033[0m")
                        break

            if KEY_AUTO and not stop_start and (time.time() - last_key_save) >= KEY_SAVE_INTERVAL_SEC:
                last_key_save = time.time()
                key_autosave(packages)

            if not stop_start and (time.time() - last_ram_check) >= 30:
                last_ram_check = time.time()
                check_low_ram(packages)

            if SERVER_HOP and not stop_start and (time.time() - last_hop_check) >= HOP_INTERVAL_SEC:
                last_hop_check = time.time()
                hop_check(packages)

            if (time.time() - last_webhook_time) >= 300:
                last_webhook_time = time.time()
                if report_on:
                    print("\033[1;32m[*] Đã đủ 5 phút, đang gửi báo cáo trạng thái định kỳ (Im lặng, không ping)...\033[0m")
                    t = threading.Thread(target=send_periodic_status_embed, args=(packages,), daemon=True)
                    t.start()
                print_status_table(packages)

            if RUN_LIMIT_HOURS and START_UP_TIME and (time.time() - last_countdown) >= 60:
                last_countdown = time.time()
                left_s = RUN_LIMIT_HOURS * 3600 - (datetime.now() - START_UP_TIME).total_seconds()
                col_left = C.YEL if left_s < 600 else C.GRY
                print(f"{col_left}[⏱] Còn lại {fmt_duration(max(0, left_s))} trước khi tự dừng{C.R}")
            if (time.time() - last_version_check) >= 600:
                last_version_check = time.time()
                threading.Thread(target=check_app_versions, args=(packages,), daemon=True).start()

            if wait_with_stop_check(2): break

        if stop_start:
            restore_screen_after_run()
            if STOP_REASON == "schedule":
                why = f"Đến giờ hẹn dừng {SCHEDULE['stop']}"
                print(f"\n\033[1;32m[✓] Đã dừng Start theo hẹn giờ ({SCHEDULE['stop']}). Quay lại menu...\033[0m")
            elif STOP_REASON == "duration":
                why = f"Đã chạy đủ {RUN_LIMIT_HOURS:g} giờ theo giới hạn"
                print(f"\n\033[1;32m[✓] Đã dừng Start sau {RUN_LIMIT_HOURS:g} giờ. Quay lại menu...\033[0m")
            else:
                why = "Người dùng bấm 0 để dừng Start"
                print("\n\033[1;31m[!] Đã dừng Start. Quay lại menu...\033[0m")
            if STOP_REASON in ("duration", "schedule") and STOP_TIMER.get("close_apps"):
                print("\033[1;33m[*] Đang tắt các clone...\033[0m")
                for _pkg in list_installed_packages():
                    close_game(_pkg)
                why += " | đã tắt các clone"
            log_event("STOP", detail=why)
            notify_tool_stopped(why)
            time.sleep(1.5)
            return

    except KeyboardInterrupt:
        stop_start = True
        restore_screen_after_run()
        print("\n\033[1;31m[!] Đã dừng Start.\033[0m")
        log_event("STOP", detail="Bị ngắt bằng Ctrl+C")
        notify_tool_stopped("Bị ngắt bằng Ctrl+C")
        time.sleep(1)
        return

    except Exception as e:
        stop_start = True
        restore_screen_after_run()
        err = f"{type(e).__name__}: {e}"
        print(f"\n\033[1;31m[!] Tool dừng do lỗi không mong muốn: {err}\033[0m")
        try:
            fr = traceback.extract_tb(e.__traceback__)[-1]
            where = f"{os.path.basename(fr.filename)}:{fr.lineno} trong {fr.name}()"
        except Exception:
            where = "không rõ vị trí"
        log_event("CRASH", detail=f"{err} | {where}")
        notify_tool_stopped(f"Lỗi không mong muốn: {err}", unexpected=True)
        wait_enter()
        return

    finally:
        restore_screen_after_run()
        NEXT_AUTO_RESTART = None
        for sig, handler in old_handlers.items():
            try:
                signal.signal(sig, handler)
            except Exception:
                pass

# ==================== CHẾ ĐỘ MÀN HÌNH ĐEN (BLACK SCREEN) ====================
BLACK_SCREEN = False
BLACK_SCREEN_ACTIVE = False
SCREEN_RESTORE_FILE = os.path.join(os.path.expanduser("~"), ".pain_screen_restore.json")

def _settings_get(key):
    out = sh(f"settings get system {key}", timeout=6).strip()
    return out if re.fullmatch(r"-?\d{1,5}", out) else None

def _settings_put(key, value):
    sh(f"settings put system {key} {int(value)}", timeout=6)
    return _settings_get(key) == str(int(value))

def _screen_state_load():
    try:
        with open(SCREEN_RESTORE_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return None
    if not isinstance(d, dict) or not re.fullmatch(r"\d{1,5}", str(d.get("level", ""))):
        return None
    mode = d.get("mode")
    return {"level": str(d["level"]), "mode": str(mode) if re.fullmatch(r"\d", str(mode)) else None,
            "poweroff": bool(d.get("poweroff"))}

def _screen_state_save(state):
    try:
        tmp = SCREEN_RESTORE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
        try:
            os.chmod(tmp, 0o600)
        except Exception:
            pass
        os.replace(tmp, SCREEN_RESTORE_FILE)
        return True
    except Exception:
        return False

def black_screen_on():
    global BLACK_SCREEN_ACTIVE
    if BLACK_SCREEN_ACTIVE:
        return True, "đã ở chế độ màn hình đen"
    st = _screen_state_load()
    if st is None:
        level = _settings_get("screen_brightness")
        if level is None:
            return False, "không đọc được độ sáng màn hình (cấp quyền 'Sửa đổi cài đặt hệ thống' cho Termux)"
        st = {"level": level, "mode": _settings_get("screen_brightness_mode"), "poweroff": False}
        if not _screen_state_save(st):
            return False, "không ghi được file khôi phục độ sáng nên không dám đổi (tránh kẹt màn hình đen)"
    if st["mode"] is not None:
        _settings_put("screen_brightness_mode", 0)
    if not _settings_put("screen_brightness", 0):
        black_screen_off()
        return False, "máy không cho đổi độ sáng (không có quyền ghi cài đặt hệ thống)"
    BLACK_SCREEN_ACTIVE = True
    out = sh("cmd display power-off 0", timeout=8).lower()
    if not any(w in out for w in ("unknown", "error", "exception", "usage", "not found", "denied", "invalid")):
        st["poweroff"] = True
        _screen_state_save(st)
        return True, "đã hạ độ sáng về 0 và tắt hiển thị (app vẫn chạy ngầm)"
    return True, "đã hạ độ sáng về 0 (máy này không hỗ trợ lệnh tắt hiển thị)"

def black_screen_off():
    global BLACK_SCREEN_ACTIVE
    st = _screen_state_load()
    if st is None:
        BLACK_SCREEN_ACTIVE = False
        return False, "không có gì để khôi phục"
    if st["poweroff"]:
        sh("cmd display power-on 0", timeout=8)
    ok = _settings_put("screen_brightness", int(st["level"]))
    if st["mode"] is not None:
        ok = _settings_put("screen_brightness_mode", int(st["mode"])) and ok
    BLACK_SCREEN_ACTIVE = False
    if ok:
        try:
            os.remove(SCREEN_RESTORE_FILE)
        except OSError:
            pass
        return True, f"đã khôi phục độ sáng gốc ({st['level']})"
    return False, "chưa khôi phục được độ sáng (file khôi phục vẫn được giữ, thử lại bằng mục Black Screen > Khôi phục)"

def restore_screen_if_needed():
    if os.path.exists(SCREEN_RESTORE_FILE):
        ok, msg = black_screen_off()
        print(f" {C.GRN if ok else C.YEL}[{'✓' if ok else '!'}] Lần chạy trước chưa khôi phục màn hình: {msg}.{C.R}")
        time.sleep(1.2)

# BLACK SCREEN FUNCTIONS DISABLED - Not compatible with UgPhone
# def menu_black_screen():
#     global BLACK_SCREEN
#     clear_screen()
#     section_title("CHẾ ĐỘ MÀN HÌNH ĐEN (BLACK SCREEN)")
#     ...

def black_screen_label():
    return "Tắt"  # Always off - not supported on UgPhone

# ==================== AUTO SERVER HOP (ĐỔI SERVER KHI LAG) ====================
SERVER_HOP = False
HOP_PING_MS = 500
HOP_CHECKS = 3
HOP_INTERVAL_SEC = 30
HOP_COOLDOWN_SEC = 600
HOP_MAX_PER_HOUR = 6
VIP_SERVERS = []
MAX_VIP_SERVERS = 10
HOP_OVERRIDE = {}
HOP_CURRENT = {}
HOP_LAST = {}
HOP_LOG = []
_HOP_LAG = 0
_HOP_PAUSE_UNTIL = 0
_HOP_RX_LINK = re.compile(r"(?:https://(?:www\.|web\.)?roblox\.com/|roblox://)[^\s'\"`;|<>$\\]{1,280}")
_HOP_RX_ID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

def valid_vip_link(s):
    return bool(s) and len(s) <= 300 and bool(_HOP_RX_LINK.fullmatch(s))

def place_id_of(link):
    link = (link or "").strip()
    if re.fullmatch(r"\d{4,}", link):
        return link
    m = re.search(r"placeId=(\d{4,})", link) or re.search(r"/games/(\d{4,})", link)
    return m.group(1) if m else None

def get_universe_id(place_id):
    if place_id in _UNIVERSE_ID_CACHE:
        return _UNIVERSE_ID_CACHE[place_id]
    out = run_cmd(["curl", "-s", "-m", "10", "-w", "\n%{http_code}",
                   f"https://apis.roblox.com/universes/v1/places/{place_id}/universe"], timeout=14)
    body, _, code = out.rpartition("\n")
    if code.strip() != "200":
        return None
    try:
        uid = json.loads(body).get("universeId")
    except Exception:
        return None
    if isinstance(uid, int):
        _UNIVERSE_ID_CACHE[place_id] = uid
        return uid
    return None

def fetch_game_status(place_id):
    uid = get_universe_id(place_id)
    if not uid:
        return None
    out = run_cmd(["curl", "-s", "-m", "10", "-w", "\n%{http_code}",
                   f"https://games.roblox.com/v1/games?universeIds={uid}"], timeout=14)
    body, _, code = out.rpartition("\n")
    if code.strip() != "200":
        return None
    try:
        rows = json.loads(body).get("data", [])
    except Exception:
        return None
    if not rows:
        return None
    g = rows[0]
    try:
        playing = int(g.get("playing", 0))
    except (TypeError, ValueError):
        playing = 0
    updated_dt = None
    updated_raw = g.get("updated")
    if updated_raw:
        try:
            updated_dt = datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))
        except Exception:
            updated_dt = None
    return {"playing": playing, "updated": updated_dt, "checked_at": time.time()}

def check_game_status():
    global GAME_STATUS_PAUSED, GAME_STATUS_REASON, LAST_GAME_STATUS
    pid = place_id_of(TARGET_LINK)
    if not pid:
        return
    status = fetch_game_status(pid)
    if status is None:
        return
    LAST_GAME_STATUS = status
    recent_update = False
    if status["updated"]:
        age_min = (datetime.now(timezone.utc) - status["updated"]).total_seconds() / 60.0
        recent_update = 0 <= age_min < GAME_STATUS_RECENT_UPDATE_MIN
    should_pause = (status["playing"] == 0) or recent_update
    if should_pause and not GAME_STATUS_PAUSED:
        GAME_STATUS_PAUSED = True
        GAME_STATUS_REASON = ("Game đang bảo trì / không có người chơi" if status["playing"] == 0
                               else "Game vừa mới update (server cũ sắp đóng)")
        print(f"\033[1;33m[!] {GAME_STATUS_REASON}. Tạm dừng dò lỗi/rejoin để tránh spam vào server đang sập...\033[0m")
        log_event("GAME_PAUSE", detail=f"{GAME_STATUS_REASON} | playing={status['playing']}")
        notify_async("warn", "Tạm dừng Rejoin", f"{GAME_STATUS_REASON} (đang chơi: {status['playing']} người).",
                     action="Tool sẽ tự kiểm tra lại và chạy tiếp khi game ổn định.")
    elif not should_pause and GAME_STATUS_PAUSED:
        GAME_STATUS_PAUSED = False
        GAME_STATUS_REASON = ""
        print(f"\033[1;32m[+] Game đã ổn định trở lại ({status['playing']} người đang chơi). Tiếp tục dò lỗi/rejoin.\033[0m")
        log_event("GAME_RESUME", detail=f"playing={status['playing']}")
        notify_async("restart", "Tiếp tục Rejoin", f"Game đã ổn định trở lại ({status['playing']} người đang chơi).",
                     action="Tool tiếp tục theo dõi và tự rejoin như bình thường.")

def measure_latency_ms(samples=3):
    vals = []
    for _ in range(samples):
        out = run_cmd(["curl", "-s", "-o", "/dev/null", "-m", "5", "-w", "%{time_connect}", "https://www.roblox.com/"], timeout=8).strip()
        try:
            v = float(out) * 1000
        except ValueError:
            continue
        vals.append(v if v > 0 else 5000)
    if not vals:
        return None
    vals.sort()
    return int(vals[len(vals) // 2])

def fetch_public_servers(place_id):
    url = f"https://games.roblox.com/v1/games/{place_id}/servers/Public?sortOrder=Asc&excludeFullGames=true&limit=100"
    out = run_cmd(["curl", "-s", "-m", "10", "-w", "\n%{http_code}", url], timeout=14)
    body, _, code = out.rpartition("\n")
    if code.strip() != "200":
        return []
    try:
        rows = json.loads(body).get("data", [])
    except Exception:
        return []
    servers = []
    for r in rows if isinstance(rows, list) else []:
        try:
            sid = str(r["id"])
            playing, maxp = int(r["playing"]), int(r["maxPlayers"])
        except (KeyError, TypeError, ValueError):
            continue
        ping = r.get("ping")
        if _HOP_RX_ID.fullmatch(sid) and maxp > 0:
            servers.append({"id": sid, "playing": playing, "max": maxp, "ping": ping if isinstance(ping, (int, float)) else None})
    return servers

def pick_public_server(servers, avoid=None):
    ok = [s for s in servers if s["id"] != avoid and s["playing"] < s["max"]]
    if not ok:
        return None
    good = [s for s in ok if s["ping"] is None or s["ping"] <= HOP_PING_MS] or ok
    good.sort(key=lambda s: (s["playing"], s["ping"] or 0))
    pool = [s for s in good if s["playing"] >= 1][:5] or good[:5]
    return random.choice(pool)

def pick_hop_target(pkg):
    cur = HOP_CURRENT.get(pkg) or TARGET_LINK
    if VIP_SERVERS:
        if cur in VIP_SERVERS:
            nxt = VIP_SERVERS[(VIP_SERVERS.index(cur) + 1) % len(VIP_SERVERS)]
        else:
            nxt = VIP_SERVERS[0]
        if nxt != cur:
            return nxt, "vip", f"VIP server #{VIP_SERVERS.index(nxt) + 1}"
    pid = place_id_of(TARGET_LINK)
    if not pid:
        return None, "", "không xác định được Place ID của game"
    s = pick_public_server(fetch_public_servers(pid), avoid=None)
    if not s:
        return None, "", "không lấy được danh sách server public (Roblox giới hạn truy cập hoặc không còn server trống)"
    return (f"roblox://experiences/start?placeId={pid}&gameInstanceId={s['id']}", "public",
            f"server public {s['playing']}/{s['max']} người" + (f", ping {int(s['ping'])}ms" if s["ping"] is not None else ""))

def do_server_hop(pkg, why):
    if MONITOR_ONLY:
        return
    now = time.time()
    HOP_LAST[pkg] = now
    link, kind, desc = pick_hop_target(pkg)
    if not link:
        print(f"{C.YEL}[!] {tab_label(pkg)}: chưa đổi được server ({desc}).{C.R}")
        log_event("HOP_FAIL", pkg, f"{why}; {desc}")
        return False
    HOP_LOG.append(now)
    print(f"{C.YEL}[*] {tab_label(pkg)}: {why} → đổi sang {desc}...{C.R}")
    log_event("HOP", pkg, f"{why} -> {desc}")
    notify_async("hop", "Đổi server", f"`{pkg}` đổi sang {desc}.", pkg=pkg, reason=why,
                 action="Tắt hẳn tab rồi vào server mới (vào không được thì quay lại game gốc)")
    HOP_OVERRIDE[pkg] = link
    started = time.time()
    try:
        ok = join_map(pkg, hard=True)
    finally:
        HOP_OVERRIDE.pop(pkg, None)
    if ok and kind == "vip":
        HOP_CURRENT[pkg] = link
    if not ok and not stop_start:
        print(f"{C.YEL}[!] {tab_label(pkg)}: server mới không vào được, quay lại game gốc...{C.R}")
        HOP_CURRENT.pop(pkg, None)
        ok = join_map(pkg, hard=True)
    report_rejoin_result(pkg, ok, started, f"Đổi server ({desc})")
    return ok

def hop_check(packages):
    global _HOP_LAG, _HOP_PAUSE_UNTIL
    now = time.time()
    if now < _HOP_PAUSE_UNTIL:
        return
    if NET_CHECK and not is_online():
        _HOP_LAG = 0
        return
    lat = measure_latency_ms()
    if lat is None:
        return
    if lat <= HOP_PING_MS:
        _HOP_LAG = 0
        return
    _HOP_LAG += 1
    print(f"{C.YEL}[!] Độ trễ tới Roblox {lat}ms > {HOP_PING_MS}ms ({_HOP_LAG}/{HOP_CHECKS} lần đo liên tiếp).{C.R}")
    if _HOP_LAG < HOP_CHECKS:
        return
    recent = [t for t in HOP_LOG if now - t < 1200]
    if len(recent) >= max(2, len(packages)):
        _HOP_PAUSE_UNTIL = now + 1800
        _HOP_LAG = 0
        msg = f"Đã đổi server {len(recent)} lần trong 20 phút mà độ trễ vẫn {lat}ms: nhiều khả năng do mạng của máy."
        print(f"{C.YEL}[!] {msg} Tạm dừng Auto Server Hop 30 phút.{C.R}")
        log_event("HOP_PAUSE", detail=msg)
        notify_async("warn", "Tạm dừng Auto Server Hop", msg, action="Kiểm tra Wi-Fi / 4G của máy", cooldown=1800)
        return
    for pkg in packages:
        if stop_start:
            return
        if pkg not in JOINED_AT or not is_app_running(pkg):
            continue
        if now - HOP_LAST.get(pkg, 0) < HOP_COOLDOWN_SEC:
            continue
        if len([t for t in HOP_LOG if now - t < 3600]) >= HOP_MAX_PER_HOUR * max(1, len(packages)):
            continue
        _HOP_LAG = 0
        do_server_hop(pkg, f"Độ trễ tới Roblox {lat}ms > {HOP_PING_MS}ms")
        return

def hop_label():
    return f"Bật · ngưỡng {HOP_PING_MS}ms · {len(VIP_SERVERS)} VIP" if SERVER_HOP else "Tắt"

def menu_vip_servers():
    while True:
        clear_screen()
        section_title("DANH SÁCH VIP SERVER")
        if VIP_SERVERS:
            for i, v in enumerate(VIP_SERVERS, 1):
                print(f" {C.LPUR}{i}.{C.R} {clip(v, ui_width() - 8)}")
        else:
            print(f" {C.GRY}(chưa có VIP server nào, khi cần đổi tool sẽ chọn Public server ít người){C.R}")
        print(f" {C.GRY}Đã có {len(VIP_SERVERS)}/{MAX_VIP_SERVERS}. Dán link VIP server của game (https://www.roblox.com/... hoặc roblox://...).{C.R}")
        print(f"{C.LPUR}[1]{C.R} {C.WHT}Thêm link VIP server{C.R}")
        print(f"{C.LPUR}[2]{C.R} {C.WHT}Xóa link (theo số thứ tự){C.R}")
        print(f"{C.RED}[0] Quay lại{C.R}")
        sub = input("Chọn: ").strip()
        if sub == "0":
            return
        if sub == "1":
            if len(VIP_SERVERS) >= MAX_VIP_SERVERS:
                msg_err(f"Đã đủ {MAX_VIP_SERVERS} link, hãy xóa bớt trước.")
                time.sleep(1.8)
                continue
            link = input("Dán link VIP server (Enter để hủy): ").strip()
            if not link:
                continue
            if not valid_vip_link(link):
                msg_err("Link không hợp lệ (chỉ nhận link roblox.com hoặc roblox://, không chứa khoảng trắng / ký tự lạ).")
            elif link in VIP_SERVERS:
                msg_warn("Link này đã có trong danh sách.")
            else:
                VIP_SERVERS.append(link)
                save_config_file()
                msg_done(f"Đã thêm VIP server #{len(VIP_SERVERS)} và lưu cấu hình.")
            time.sleep(1.8)
        elif sub == "2":
            if not VIP_SERVERS:
                msg_warn("Chưa có link nào để xóa.")
                time.sleep(1.5)
                continue
            n = input("Nhập số thứ tự link cần xóa (Enter để hủy): ").strip()
            if n.isdigit() and 1 <= int(n) <= len(VIP_SERVERS):
                VIP_SERVERS.pop(int(n) - 1)
                save_config_file()
                msg_done("Đã xóa link và lưu cấu hình.")
            elif n:
                msg_err("Số thứ tự không hợp lệ.")
            time.sleep(1.5)
        else:
            invalid_choice(sub)

def menu_server_hop():
    global SERVER_HOP, HOP_PING_MS
    clear_screen()
    section_title("AUTO SERVER HOP (ĐỔI SERVER KHI LAG)")
    print(f" {C.GRY}Trạng thái:{C.R} {C.WHT}{'BẬT' if SERVER_HOP else 'TẮT'}{C.R}   {C.GRY}Ngưỡng:{C.R} {C.WHT}{HOP_PING_MS}ms{C.R}   {C.GRY}VIP server:{C.R} {C.WHT}{len(VIP_SERVERS)}{C.R}")
    print(f" Khi độ trễ tới Roblox vượt ngưỡng {HOP_CHECKS} lần đo liên tiếp (mỗi {HOP_INTERVAL_SEC}s), tool đổi 1 tab sang")
    print(" VIP server khác trong danh sách; không có danh sách thì chọn Public server ít người. Mỗi tab đổi tối đa")
    print(f" 1 lần/{HOP_COOLDOWN_SEC // 60} phút. {C.GRY}Độ trễ đo từ máy tới Roblox, không phải số ping hiển thị trong game; nếu đổi nhiều")
    print(f" lần mà vẫn lag thì tool tạm dừng 30 phút vì lỗi nhiều khả năng ở mạng của máy.{C.R}")
    print(f"{C.LPUR}[1]{C.R} {C.WHT}Bật{C.R}")
    print(f"{C.LPUR}[2]{C.R} {C.WHT}Tắt{C.R}")
    print(f"{C.LPUR}[3]{C.R} {C.WHT}Đổi ngưỡng độ trễ (200-2000 ms){C.R}")
    print(f"{C.LPUR}[4]{C.R} {C.WHT}Quản lý danh sách VIP server{C.R}")
    print(f"{C.LPUR}[5]{C.R} {C.WHT}Đo độ trễ tới Roblox ngay{C.R}")
    print(f"{C.RED}[0] Quay lại{C.R}")
    sub = input("Chọn: ").strip()
    if sub == "1":
        SERVER_HOP = True
    elif sub == "2":
        SERVER_HOP = False
    elif sub == "3":
        raw = input("Nhập ngưỡng (ms, 200-2000): ").strip()
        if raw.isdigit() and 200 <= int(raw) <= 2000:
            HOP_PING_MS = int(raw)
        else:
            msg_err("Chỉ nhận số từ 200 đến 2000.")
            time.sleep(1.5)
            return
    elif sub == "4":
        menu_vip_servers()
        return
    elif sub == "5":
        msg_info("Đang đo độ trễ tới Roblox (3 lần)...")
        lat = measure_latency_ms()
        if lat is None:
            msg_err("Không đo được (máy không có lệnh curl).")
        else:
            (msg_done if lat <= HOP_PING_MS else msg_warn)(f"Độ trễ tới Roblox: {lat}ms (ngưỡng {HOP_PING_MS}ms).")
        wait_enter()
        return
    elif sub == "0":
        msg_cancel("Đã quay lại menu Set up.")
        time.sleep(0.8)
        return
    else:
        msg_cancel("Lựa chọn không hợp lệ, không có gì thay đổi.")
        time.sleep(1.2)
        return
    save_config_file()
    msg_done(f"Auto Server Hop: {'BẬT' if SERVER_HOP else 'TẮT'}, ngưỡng {HOP_PING_MS}ms. Đã lưu cấu hình.")
    time.sleep(2)

def restore_screen_after_run():
    if BLACK_SCREEN_ACTIVE:
        ok, msg = black_screen_off()
        print(f"{C.GRN if ok else C.YEL}[{'✓' if ok else '!'}] Black Screen: {msg}.{C.R}")
        log_event("BLACKSCREEN", detail=f"tắt: {msg}")


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
    if SCHEDULE.get("start") or SCHEDULE.get("stop"):
        print(box_kv("Hẹn giờ", f"{dot(True)} {C.WHT}Chạy {SCHEDULE.get('start') or '--:--'} · Dừng {SCHEDULE.get('stop') or '--:--'}{C.R}", w, lw))
    if AUTO_RESTART_HOURS:
        print(box_kv("Auto Restart", f"{dot(True)} {C.WHT}{clip(auto_restart_label(), vw - 2)}{C.R}", w, lw))
    if update_available():
        print(box_kv("Cập nhật", f"{dot(None)} {C.YEL}Có bản mới {UPDATE_INFO['latest']}{C.R}", w, lw))
    print(box_sep(w))
    print(box_row(f"{C.PUR}▸ MENU{C.R}", w))

    entries = [
        ("1", "Start"),
        ("2", "Set up"),
        ("3", "Package prefix"),
        ("4", "Change ID"),
        ("5", "Set Webhook URL"),
        ("6", "Xóa cache"),
        ("7", "Import auto execute"),
        ("8", "Mở tab clone"),
        ("9", "Send Text"),
        ("10", "Backup / Restore"),
        ("11", "Cookie Roblox"),
        ("12", "Xem log"),
        ("13", "Thống kê độ ổn định"),
        ("14", "Hồ sơ theo game"),
        ("15", "Gán executor cho tab"),
        ("16", "Ban Tracking Stats"),
        ("17", "Autoexec Manager"),
        ("0", "Exit"),
    ]

    def cell(entry, width):
        k, label = entry
        kc = C.RED if k == "0" else (C.GRN if k == "1" else C.LPUR)
        lc = C.RED if k == "0" else C.WHT
        return f"{kc}{pad('[' + k + ']', 4)}{C.R} {lc}{clip(label, width - 5)}{C.R}"

    colw = inner // 2
    half = (len(entries) + 1) // 2
    for i in range(half):
        right = cell(entries[i + half], inner - colw) if i + half < len(entries) else ""
        print(box_row(pad(cell(entries[i], colw), colw) + right, w))
    print(box_bot(w))

# ==================== MENU SET UP / BACKUP ====================
def setup_auto_rejoin():
    global AUTO_REJOIN_MODE, DELAY_REJOIN_MINUTES
    clear_screen()
    section_title("SET UP AUTO REJOIN")
    print(f"{C.LPUR}[1]{C.R} {C.WHT}Auto rejoin vang/crash{C.R}")
    print(f"{C.LPUR}[2]{C.R} {C.WHT}Delay rejoin (Hết chu kỳ tự tắt Đa nhiệm rồi vào lại Map){C.R}")
    mode = input("Chọn cơ chế [1/2]: ").strip()
    if mode == "1":
        AUTO_REJOIN_MODE = 1
        save_config_file()
        msg_done("Đã chọn cơ chế: Auto rejoin vang/crash và lưu cấu hình!")
    elif mode == "2":
        AUTO_REJOIN_MODE = 2
        mins = input("Nhập thời gian chu kỳ (phút): ").strip()
        if mins.isdigit() and int(mins) > 0:
            DELAY_REJOIN_MINUTES = int(mins)
            save_config_file()
            msg_done(f"Đã cài Delay Rejoin thành công: {DELAY_REJOIN_MINUTES} phút/chu kỳ và lưu cấu hình!")
        else:
            save_config_file()
            msg_done("Đã chọn cơ chế: Delay Rejoin và lưu cấu hình.")
            msg_warn(f"Thời gian nhập không hợp lệ, giữ nguyên chu kỳ {DELAY_REJOIN_MINUTES} phút.")
    else:
        msg_cancel("Lựa chọn không hợp lệ, giữ nguyên cơ chế hiện tại: " + get_rejoin_mode_str())
    time.sleep(2)

def setup_auto_clear():
    global AUTO_CLEAR_DATA, FREEZE_TIMEOUT_MIN
    clear_screen()
    section_title("AUTO CLEAR DATA / KHÔI PHỤC TAB KẸT")
    print(f"Trạng thái: {'BẬT' if AUTO_CLEAR_DATA else 'TẮT'} | Ngưỡng treo: {FREEZE_TIMEOUT_MIN} phút")
    print("Tab không có log mới quá ngưỡng -> xóa data (pm clear) -> khôi phục backup (giữ login) -> mở lại vào Map.")
    print("Chỉ xóa data khi tab đã có backup; chưa có backup thì chỉ tắt hẳn tab rồi mở lại.")
    print(f"{C.LPUR}[1]{C.R} {C.WHT}Bật{C.R}")
    print(f"{C.LPUR}[2]{C.R} {C.WHT}Tắt{C.R}")
    print(f"{C.LPUR}[3]{C.R} {C.WHT}Đổi ngưỡng treo (3-5 phút){C.R}")
    print(f"{C.RED}[0] Quay lại{C.R}")
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
            msg_err("Chỉ nhận 3, 4 hoặc 5 phút. Giữ nguyên ngưỡng cũ.")
    elif sub == "0":
        msg_cancel("Đã quay lại menu Set up.")
        time.sleep(0.8)
        return
    else:
        msg_cancel("Lựa chọn không hợp lệ, không có gì thay đổi.")
        time.sleep(1.2)
        return
    save_config_file()
    msg_done(f"Đã cập nhật Auto Clear Data: {'BẬT' if AUTO_CLEAR_DATA else 'TẮT'} (ngưỡng {FREEZE_TIMEOUT_MIN} phút) và lưu cấu hình.")
    time.sleep(2)

def setup_auto_backup():
    global AUTO_BACKUP
    clear_screen()
    section_title("AUTO BACKUP DATA TAB")
    print(f"Trạng thái: {'BẬT' if AUTO_BACKUP else 'TẮT'} | Chu kỳ: {BACKUP_INTERVAL_MIN} phút | Thư mục: {BACKUP_DIR}")
    print("Tự backup dữ liệu (đăng nhập, cài đặt) của các tab đang chạy ổn định.")
    print(f"{C.LPUR}[1]{C.R} {C.WHT}Bật{C.R}")
    print(f"{C.LPUR}[2]{C.R} {C.WHT}Tắt{C.R}")
    print(f"{C.RED}[0] Quay lại{C.R}")
    sub = input("Chọn: ").strip()
    if sub == "1":
        AUTO_BACKUP = True
    elif sub == "2":
        AUTO_BACKUP = False
    elif sub == "0":
        msg_cancel("Đã quay lại menu Set up.")
        time.sleep(0.8)
        return
    else:
        msg_cancel("Lựa chọn không hợp lệ, không có gì thay đổi.")
        time.sleep(1.2)
        return
    save_config_file()
    msg_done(f"Đã cập nhật Auto Backup: {'BẬT' if AUTO_BACKUP else 'TẮT'} và lưu cấu hình.")
    time.sleep(2)

def pick_package(packages):
    for i, p in enumerate(packages, 1):
        info = backup_info(p)
        status = f"đã backup lúc {info[1]}" if info else "chưa có backup"
        print(f"\033[1;37m{i}. {tab_label(p)}\033[0m ({status})")
    c = input("Chọn tab (số, 0 để hủy): ").strip()
    if c.isdigit() and 1 <= int(c) <= len(packages):
        return packages[int(c) - 1]
    return None

def backup_menu():
    while True:
        clear_screen()
        section_title("BACKUP / RESTORE DATA TAB")
        print(f"{C.LPUR}[1]{C.R} {C.WHT}Backup tất cả tab{C.R}")
        print(f"{C.LPUR}[2]{C.R} {C.WHT}Restore tất cả tab{C.R}")
        print(f"{C.LPUR}[3]{C.R} {C.WHT}Backup 1 tab{C.R}")
        print(f"{C.LPUR}[4]{C.R} {C.WHT}Restore 1 tab{C.R}")
        print(f"{C.LPUR}[5]{C.R} {C.WHT}Xem danh sách backup{C.R}")
        print(f"{C.RED}[0] Quay lại menu chính{C.R}")
        sub = input("Chọn: ").strip()
        if sub == "0":
            msg_info("Quay lại menu chính...")
            time.sleep(0.6)
            return
        if sub not in ("1", "2", "3", "4", "5"):
            msg_err(f"Lựa chọn '{sub or '(trống)'}' không hợp lệ.")
            time.sleep(1.2)
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
                    print(f"\033[1;32m[+] {tab_label(p)}: {round(info[0] / 1024 / 1024, 1)} MB, {info[1]}{prev}\033[0m")
                else:
                    print(f"\033[1;33m[-] {tab_label(p)}: chưa có backup\033[0m")
            print(f"Thư mục: {BACKUP_DIR}")
            input("Enter để quay lại...")

        elif sub in ("1", "3"):
            targets = packages
            if sub == "3":
                pkg = pick_package(packages)
                if not pkg:
                    msg_cancel("Đã hủy chọn tab.")
                    time.sleep(1)
                    continue
                targets = [pkg]
            if input("Sẽ tắt tab để backup dữ liệu nhất quán. Tiếp tục? (y/n): ").strip().lower() != "y":
                msg_cancel("Đã hủy backup.")
                time.sleep(1)
                continue
            done_n = 0
            for p in targets:
                print(f"\033[1;33m[*] Đang backup {tab_label(p)}...\033[0m")
                ok, msg = backup_tab(p, stop_first=True)
                if ok:
                    NEEDS_LOGIN.discard(p)
                    done_n += 1
                print(f"\033[1;32m[+] {tab_label(p)}: {msg}\033[0m" if ok else f"\033[1;31m[!] {tab_label(p)}: {msg}\033[0m")
            if done_n == len(targets):
                msg_done(f"Backup thành công {done_n}/{len(targets)} tab (lưu ở {BACKUP_DIR}).")
            else:
                msg_warn(f"Backup xong {done_n}/{len(targets)} tab, các tab còn lại bị lỗi (xem thông báo phía trên).")
            wait_enter("Xong. Ấn Enter để quay lại...")

        elif sub in ("2", "4"):
            targets = packages
            if sub == "4":
                pkg = pick_package(packages)
                if not pkg:
                    msg_cancel("Đã hủy chọn tab.")
                    time.sleep(1)
                    continue
                targets = [pkg]
            if input("Sẽ xóa data hiện tại của tab và thay bằng bản backup. Tiếp tục? (y/n): ").strip().lower() != "y":
                msg_cancel("Đã hủy restore.")
                time.sleep(1)
                continue
            done_n = 0
            for p in targets:
                use_prev = False
                if sub == "4" and backup_size(p, prev=True) > 0:
                    use_prev = input("Dùng bản backup cũ hơn? (y = bản cũ, Enter = bản mới nhất): ").strip().lower() == "y"
                print(f"\033[1;33m[*] Đang restore {tab_label(p)}...\033[0m")
                ok, msg = restore_tab(p, prev=use_prev)
                if ok:
                    NEEDS_LOGIN.discard(p)
                    done_n += 1
                print(f"\033[1;32m[+] {tab_label(p)}: {msg}\033[0m" if ok else f"\033[1;31m[!] {tab_label(p)}: {msg}\033[0m")
            if done_n == len(targets):
                msg_done(f"Restore thành công {done_n}/{len(targets)} tab.")
            else:
                msg_warn(f"Restore xong {done_n}/{len(targets)} tab, các tab còn lại bị lỗi (xem thông báo phía trên).")
            print(f" {C.GRY}Mở lại tab bằng Start hoặc mục [8].{C.R}")
            wait_enter("Xong. Ấn Enter để quay lại...")

# ==================== LOGIN COOKIE ROBLOX ====================
COOKIE_NAME = ".ROBLOSECURITY"
COOKIE_HOST = ".roblox.com"
COOKIE_DB_PATHS = ("app_webview/Default/Cookies", "app_webview/Cookies")
COOKIE_FILE_DEFAULT = "/sdcard/cookie.txt"
PKG_NAME_RX = re.compile(r"[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+")

def normalize_cookie(raw):
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
    db = find_cookie_db(pkg)
    if db:
        return db
    msg_info(f"{pkg} chưa có dữ liệu WebView, mở app 1 lần để khởi tạo...")
    open_game(pkg, hard=True, enter_map=False)
    for _ in range(15):
        time.sleep(2)
        db = find_cookie_db(pkg)
        if db:
            time.sleep(3)
            break
    close_game(pkg)
    return db or find_cookie_db(pkg)

def inject_cookie(pkg, cookie):
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
            now_c = int((time.time() + 11644473600) * 1000000)
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
                elif notnull and dflt is None:
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
    pkgs = list_installed_packages()
    print()
    if pkgs:
        print(f" {C.GRY}Package tìm thấy ({PACKAGE_PREFIX}):{C.R}")
        for i, p in enumerate(pkgs, 1):
            acc = ACCOUNTS.get(p)
            tag = f" {C.GRY}← {acc}{C.R}" if acc else ""
            print(f"  {C.LPUR}{i:>2}.{C.R} {C.WHT}{p}{C.R}{' (' + ALIASES[p] + ')' if ALIASES.get(p) else ''}{tag}")
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

    msg_info(f"Đang ghi cookie vào {tab_label(pkg)} (tab sẽ được tắt nếu đang chạy)...")
    ok, msg = inject_cookie(pkg, cookie)
    if not ok:
        msg_err(f"{tab_label(pkg)}: {msg}")
        return False
    NEEDS_LOGIN.discard(pkg)
    if name:
        ACCOUNTS[pkg] = name
        save_config_file()
    msg_ok(f"{tab_label(pkg)}: đăng nhập cookie thành công" + (f" ({name})" if name else "") + ".")

    if ask("Mở tab vào game ngay? (y/n):").strip().lower() == "y":
        if open_game(pkg, hard=True, enter_map=bool(TARGET_LINK)):
            msg_ok("Đã gửi lệnh mở tab.")
            if not TARGET_LINK:
                msg_info("Chưa chọn game nên chỉ mở app (Set up > Chọn game để tự vào Map).")
        else:
            msg_err("Không mở được tab, thử mở bằng tay hoặc mục [8].")
    return True

def cookie_login_submenu():
    """Submenu đăng nhập cookie vào tab"""
    while True:
        clear_screen()
        section_title("ĐĂNG NHẬP COOKIE ROBLOX")
        print(f" {C.GRY}Đăng nhập tài khoản Roblox vào tab clone bằng cookie {COOKIE_NAME}.{C.R}")
        print(f" {C.GRY}Cookie chỉ ghi vào máy, không lưu và không gửi đi đâu.{C.R}")
        print()
        print(f" {C.LPUR}[1]{C.R} {C.WHT}Dán cookie trực tiếp{C.R}")
        print(f" {C.LPUR}[2]{C.R} {C.WHT}Đọc từ file{C.R} {C.GRY}(mỗi dòng 1 cookie){C.R}")
        print(f" {C.LPUR}[3]{C.R} {C.WHT}Lấy từ clipboard{C.R} {C.GRY}(cần Termux:API){C.R}")
        print(f" {C.RED}[0] Quay lại{C.R}")
        print()
        sub = ask("Chọn:").strip()
        if sub == "0":
            msg_info("Quay lại menu chính...")
            time.sleep(0.6)
            return
        if sub not in ("1", "2", "3"):
            msg_err(f"Lựa chọn '{sub or '(trống)'}' không hợp lệ.")
            time.sleep(1.2)
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
                msg_cancel("Chưa nhập cookie, đã hủy.")
                time.sleep(1)
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

def _read_cookies_from_webview_db(pkg):
    """Đọc .ROBLOSECURITY / RBXID từ CSDL cookie WebView của package. Trả về (dict, lý do)."""
    import sqlite3
    q = shlex.quote
    db = find_cookie_db(pkg)
    if not db:
        return {}, "package chưa có dữ liệu WebView (chưa mở app hoặc chưa đăng nhập)"
    work = os.path.join(os.path.expanduser("~"), ".pain_cookie_tmp")
    local = os.path.join(work, "Cookies")
    rows = []
    try:
        shutil.rmtree(work, ignore_errors=True)
        os.makedirs(work, exist_ok=True)
        os.chmod(work, 0o700)
        open(local, "wb").close()
        sh(f"cat {q(db)} > {q(local)}", timeout=15)
        if os.path.getsize(local) <= 0:
            return {}, "không đọc được file cookie của app"
        if "1" in sh(f"[ -f {q(db + '-journal')} ] && echo 1", timeout=5):
            open(local + "-journal", "wb").close()
            sh(f"cat {q(db + '-journal')} > {q(local + '-journal')}", timeout=15)
        con = sqlite3.connect(local, timeout=10)
        try:
            rows = con.execute(
                "SELECT name, value, encrypted_value FROM cookies "
                "WHERE host_key LIKE ? AND name IN (?, ?)",
                ("%roblox.com", COOKIE_NAME, "RBXID"),
            ).fetchall()
        finally:
            con.close()
    except Exception as e:
        return {}, f"lỗi đọc CSDL: {e}"
    finally:
        shutil.rmtree(work, ignore_errors=True)

    found, encrypted_only = {}, False
    for name, value, enc in rows:
        if value:
            found[name] = value
        elif enc:
            encrypted_only = True
    if COOKIE_NAME not in found:
        if encrypted_only:
            return {}, "cookie bị mã hóa, tool không đọc được trên máy này"
        return {}, "không có cookie .ROBLOSECURITY (tài khoản chưa đăng nhập trong package này)"
    return found, None

def _read_cookies_from_prefs(pkg):
    """Dự phòng: đọc cookie từ shared_prefs (XML). Trả về (dict, lý do)."""
    prefs_path = f"/data/data/{pkg}/shared_prefs/"
    q = shlex.quote
    names = sh(f"ls {q(prefs_path)} 2>/dev/null", timeout=5)
    files = [f.strip() for f in names.splitlines() if f.strip().endswith(".xml")]
    if not files:
        return {}, "không tìm thấy shared_prefs của package này"
    content = ""
    for pf in files:
        content += sh(f"cat {q(prefs_path + pf)} 2>/dev/null", timeout=5) + "\n"
    found = {}
    m = re.search(r'name="\.ROBLOSECURITY"[^>]*>\s*([^<]+?)\s*<', content)
    if m:
        found[COOKIE_NAME] = m.group(1)
    m = re.search(r'name="RBXID"[^>]*>\s*([^<]+?)\s*<', content)
    if m:
        found["RBXID"] = m.group(1)
    if COOKIE_NAME not in found:
        return {}, "không có cookie .ROBLOSECURITY trong shared_prefs"
    return found, None

def get_cookie_account():
    """Lấy cookie .ROBLOSECURITY từ package Roblox đã đăng nhập"""
    clear_screen()
    section_title("LẤY COOKIE ACCOUNT ROBLOX")

    print(f"{C.GRY}Tính năng này giúp bạn lấy cookie từ package clone mà bạn đã setup.{C.R}\n")

    if not root_mode():
        msg_err("Máy không có root, không thể lấy cookie từ package.")
        wait_enter()
        return

    packages = get_all_packages()
    if not packages:
        msg_err("Không tìm thấy package Roblox nào trên thiết bị.")
        wait_enter()
        return

    print(f"Tìm thấy {len(packages)} packages:\n")
    for i, pkg in enumerate(packages, 1):
        print(f" {C.LPUR}[{i}]{C.R} {pkg}")

    print(f"\n{C.GRY}(Hoặc nhập tên package trực tiếp, ví dụ: com.roblox.clone1){C.R}\n")
    choice = ask("Chọn package (số hoặc tên):").strip()

    selected_pkg = None
    if choice.isdigit() and 1 <= int(choice) <= len(packages):
        selected_pkg = packages[int(choice) - 1]
    elif choice in packages:
        selected_pkg = choice

    if not selected_pkg:
        msg_err("Package không hợp lệ.")
        wait_enter()
        return

    print(f"\n{C.YEL}[*] Đang lấy cookie từ {selected_pkg}...{C.R}")

    try:
        found, reason = _read_cookies_from_webview_db(selected_pkg)
        if not found:
            found_p, reason_p = _read_cookies_from_prefs(selected_pkg)
            if found_p:
                found, reason = found_p, None
            else:
                reason = reason or reason_p
        if not found:
            msg_warn(f"Không lấy được cookie: {reason}")
            wait_enter()
            return

        found_cookies = []
        if "RBXID" in found:
            found_cookies.append(("RBXID", found["RBXID"]))
        found_cookies.append((COOKIE_NAME, normalize_cookie(found[COOKIE_NAME])))

        print(f"\n{C.GRN}✓ Tìm thấy {len(found_cookies)} cookie:{C.R}\n")
        for name, value in found_cookies:
            print(f"{C.LPUR}[{name}]{C.R}")
            print(f"  {value[:50]}..." if len(value) > 50 else f"  {value}")
            print()

        print(f"{C.YEL}1. Copy toàn bộ cookie (dạng .ROBLOSECURITY){C.R}")
        print(f"{C.YEL}2. Lưu vào file{C.R}")
        print(f"{C.RED}0. Quay lại{C.R}\n")

        sub = ask("Chọn:").strip()

        if sub == "1":
            cookie_value = found_cookies[-1][1]
            print(f"\n{C.GRN}Cookie đã copy:{C.R}\n{cookie_value}\n")
            msg_info("Bạn có thể dán cookie vào mục [11] > [1] Đăng nhập Cookie Roblox")
        elif sub == "2":
            print(f"{C.YEL}[*] Đang lấy tên tài khoản Roblox...{C.R}")
            ok_user, data = roblox_check_cookie(found[COOKIE_NAME])
            if ok_user and isinstance(data, dict) and data.get("name"):
                username = data["name"]
                msg_info(f"Tài khoản: {username} (ID {data.get('id')})")
            else:
                username = found.get("RBXID") or "unknown"
                msg_warn(f"Không lấy được tên tài khoản ({data}). Dùng ID: {username}")

            download_dir = "/sdcard/Download"
            filename = f"cookie-{username}.txt"
            filepath = f"{download_dir}/{filename}"
            try:
                os.makedirs(download_dir, exist_ok=True)
                with open(filepath, "w", encoding="utf-8") as f:
                    for name, value in found_cookies:
                        f.write(f"{value}\n")
                msg_done(f"Đã lưu cookie vào:\n{filepath}")
                print(f"\n{C.GRY}File: {filename}{C.R}")
                print(f"{C.GRY}Thư mục: {download_dir}{C.R}")
            except Exception as e:
                msg_err(f"Lỗi khi lưu file: {str(e)}")
                time.sleep(1)
                return

        wait_enter()

    except Exception as e:
        msg_err(f"Lỗi khi lấy cookie: {str(e)}")
        wait_enter()


def menu_cookie_roblox():
    """Menu chính cho Cookie Roblox - chọn giữa Login hoặc Get Cookie"""
    while True:
        clear_screen()
        section_title("COOKIE ROBLOX")
        
        print(f"{C.GRY}Quản lý cookie Roblox cho các tab clone của bạn{C.R}\n")
        
        print(f"{C.LPUR}[1]{C.R} {C.WHT}Đăng Nhập Cookie Roblox{C.R}")
        print(f"    → Nhập cookie để đăng nhập tài khoản vào tab clone")
        print(f"    → Hỗ trợ: dán trực tiếp, đọc file, clipboard\n")
        
        print(f"{C.LPUR}[2]{C.R} {C.WHT}Lấy Cookie Account Roblox{C.R}")
        print(f"    → Trích xuất cookie từ package Roblox trên thiết bị")
        
        print(f"{C.RED}[0] Quay lại menu chính{C.R}\n")
        
        choice = ask("Chọn chức năng:").strip()
        
        if choice == "1":
            cookie_login_submenu()
        elif choice == "2":
            get_cookie_account()
        elif choice == "0":
            break
        else:
            msg_err(f"Lựa chọn '{choice or '(trống)'}' không hợp lệ.")
            time.sleep(1)

def get_autoexec_path():
    """Lấy đường dẫn thư mục Autoexec"""
    # Common paths
    paths = [
        "/sdcard/Roblox/Autoexec",
        "/sdcard/Autoexec",
        "/sdcard/Download/Autoexec",
        "/storage/emulated/0/Roblox/Autoexec",
    ]
    
    for path in paths:
        if os.path.isdir(path):
            return path
    
    return None

def import_autoexec_script():
    """Mục 7: Nhập script từ user → Tạo file → Gán vào Autoexec"""
    clear_screen()
    section_title("IMPORT AUTO EXECUTE")
    
    print(f"{C.GRY}Nhập script Lua vào tool, tool sẽ tạo file và gán vào Autoexec folder.{C.R}\n")
    
    # Get autoexec path
    autoexec_path = get_autoexec_path()
    if not autoexec_path:
        print(f"{C.GRY}Tạo thư mục Autoexec...{C.R}")
        autoexec_path = "/sdcard/Roblox/Autoexec"
        run_cmd(f"mkdir -p {autoexec_path}")
    
    print(f"{C.GRY}Thư mục Autoexec: {autoexec_path}{C.R}\n")
    
    print(f"{C.YEL}1. Dán script trực tiếp{C.R}")
    print(f"{C.YEL}2. Nhập đường dẫn file script{C.R}")
    print(f"{C.RED}0. Quay lại{C.R}\n")
    
    choice = ask("Chọn:").strip()
    
    if choice == "0":
        return
    
    script_content = None
    script_name = None
    
    if choice == "1":
        # Dán script trực tiếp
        print(f"\n{C.GRY}Dán script của bạn (Nhập 'END' trên dòng riêng để kết thúc):{C.R}\n")
        lines = []
        while True:
            line = input()
            if line.strip().upper() == "END":
                break
            lines.append(line)
        
        script_content = "\n".join(lines)
        if not script_content.strip():
            msg_err("Script không được để trống.")
            wait_enter()
            return
        
        # Ask for script name
        script_name = ask("Nhập tên file script (không cần .lua):").strip()
        if not script_name:
            script_name = f"script_{int(time.time())}"
        
        # Clean filename
        script_name = "".join(c for c in script_name if c.isalnum() or c in ('_', '-')).lower()
        
    elif choice == "2":
        # Đọc từ file
        file_path = ask("Nhập đường dẫn file script:").strip()
        
        if not os.path.exists(file_path):
            msg_err("File không tồn tại.")
            wait_enter()
            return
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                script_content = f.read()
            
            if not script_content.strip():
                msg_err("File script trống.")
                wait_enter()
                return
            
            # Get filename from path
            script_name = os.path.basename(file_path).replace('.lua', '').replace('.txt', '')
            
        except Exception as e:
            msg_err(f"Lỗi đọc file: {str(e)}")
            wait_enter()
            return
    else:
        msg_err("Lựa chọn không hợp lệ.")
        time.sleep(1)
        return
    
    # Create file in Autoexec
    if not script_name.endswith('.lua'):
        script_name += '.lua'
    
    filepath = os.path.join(autoexec_path, script_name)
    
    # Check if file exists
    if os.path.exists(filepath):
        print(f"\n{C.YEL}File {script_name} đã tồn tại.{C.R}")
        print(f"{C.YEL}1. Ghi đè{C.R}")
        print(f"{C.YEL}2. Đổi tên (nhập tên mới){C.R}")
        print(f"{C.RED}0. Hủy{C.R}\n")
        
        sub = ask("Chọn:").strip()
        
        if sub == "0":
            return
        elif sub == "2":
            new_name = ask("Nhập tên mới (không cần .lua):").strip()
            if new_name:
                script_name = new_name if new_name.endswith('.lua') else new_name + '.lua'
                filepath = os.path.join(autoexec_path, script_name)
            else:
                return
    
    # Write file
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(script_content)
        
        msg_done(f"Đã tạo file: {script_name}")
        print(f"{C.GRY}Đường dẫn: {filepath}{C.R}")
        
        # Show assign options
        print(f"\n{C.YEL}Script này dùng cho game nào?{C.R}\n")
        
        games = [
            "Blox Fruit", "King Legacy", "Blade Ball", "Fisch",
            "Pet Simulator 99", "Anime Vanguards", "Steal a Brainrot",
            "Steal an Egg", "Grow a Garden", "Grow a Garden 2", "Khác"
        ]
        
        for i, game in enumerate(games, 1):
            print(f" [{i}] {game}")
        
        game_idx = ask("\nChọn game (số) hoặc Enter để bỏ qua:").strip()
        
        if game_idx and game_idx.isdigit() and 1 <= int(game_idx) <= len(games):
            selected_game = games[int(game_idx) - 1]
            if selected_game != "Khác":
                # Rename file to match game
                game_prefix = selected_game.lower().replace(' ', '_')
                new_script_name = f"{game_prefix}.lua"
                new_filepath = os.path.join(autoexec_path, new_script_name)
                
                try:
                    os.rename(filepath, new_filepath)
                    msg_done(f"Đã gán cho game: {selected_game}")
                    print(f"{C.GRY}Tên file: {new_script_name}{C.R}")
                except Exception as e:
                    msg_warn(f"Không thể đổi tên: {str(e)}")
        
        time.sleep(2)
        
    except Exception as e:
        msg_err(f"Lỗi tạo file: {str(e)}")
        wait_enter()

def menu_autoexec_manager():
    """Quản lý script Autoexec theo game"""
    clear_screen()
    section_title("QUẢN LÝ AUTOEXEC THEO GAME")
    
    autoexec_path = get_autoexec_path()
    if not autoexec_path:
        msg_err("Không tìm thấy thư mục Autoexec trên thiết bị.")
        print(f"{C.GRY}Các đường dẫn tìm kiếm:{C.R}")
        print("  • /sdcard/Roblox/Autoexec")
        print("  • /sdcard/Autoexec")
        print("  • /sdcard/Download/Autoexec")
        wait_enter()
        return
    
    print(f"{C.GRY}Thư mục: {autoexec_path}{C.R}\n")
    
    # Game - Script mapping
    GAME_SCRIPTS = {
        "Blox Fruit": ["bloxfruit", "blox_fruit", "bf"],
        "King Legacy": ["kinglegacy", "king_legacy", "kl"],
        "Blade Ball": ["bladeball", "blade_ball", "bb"],
        "Fisch": ["fisch", "fish"],
        "Pet Simulator 99": ["petsim99", "pet_sim", "ps99"],
        "Anime Vanguards": ["animevanguards", "anime_vanguards", "av"],
        "Steal a Brainrot": ["brainrot", "steal_brainrot"],
        "Steal an Egg": ["egg", "stealegg"],
    }
    
    # Liệt kê scripts
    scripts = [f for f in os.listdir(autoexec_path) if f.lower().endswith('.lua')]
    
    if not scripts:
        msg_err("Không tìm thấy script .lua nào trong thư mục Autoexec.")
        wait_enter()
        return
    
    print(f"Tìm thấy {len(scripts)} scripts:\n")
    
    for i, script in enumerate(scripts, 1):
        is_enabled = not script.endswith('.disabled')
        status = f"{C.GRN}✓{C.R}" if is_enabled else f"{C.RED}✗{C.R}"
        print(f" {status} [{i}] {script}")
    
    print(f"\n{C.YEL}1. Chọn script và gán game{C.R}")
    print(f"{C.YEL}2. Auto-enable script cho game hiện tại{C.R}")
    print(f"{C.YEL}3. Disable tất cả scripts{C.R}")
    print(f"{C.RED}0. Quay lại{C.R}\n")
    
    choice = ask("Chọn:").strip()
    
    if choice == "1":
        # Chọn script
        script_idx = ask("Chọn số script:").strip()
        if not script_idx.isdigit() or int(script_idx) < 1 or int(script_idx) > len(scripts):
            msg_err("Script không hợp lệ.")
            time.sleep(1)
            return
        
        selected_script = scripts[int(script_idx) - 1]
        
        print(f"\nGán {selected_script} cho game nào?\n")
        games = list(GAME_SCRIPTS.keys())
        for i, game in enumerate(games, 1):
            print(f" [{i}] {game}")
        
        game_idx = ask("\nChọn số game:").strip()
        if not game_idx.isdigit() or int(game_idx) < 1 or int(game_idx) > len(games):
            msg_err("Game không hợp lệ.")
            time.sleep(1)
            return
        
        selected_game = games[int(game_idx) - 1]
        
        # Rename script
        old_path = os.path.join(autoexec_path, selected_script)
        new_name = f"{selected_game.lower().replace(' ', '_')}.lua"
        new_path = os.path.join(autoexec_path, new_name)
        
        try:
            os.rename(old_path, new_path)
            msg_done(f"Đã gán {selected_script} → {new_name} ({selected_game})")
        except Exception as e:
            msg_err(f"Lỗi rename: {str(e)}")
        
        time.sleep(2)
    
    elif choice == "2":
        print("\nScript nào được bật để phát hiện game hiện tại?")
        print(f"{C.GRY}(Ví dụ: Blox Fruit.lua = enable khi chơi Blox Fruit){C.R}\n")
        
        # Giả sử current game từ CURRENT_GAME global
        if 'CURRENT_GAME' in globals():
            current_game = CURRENT_GAME
            print(f"Game hiện tại: {current_game}")
            
            # Disable tất cả
            for script in scripts:
                if not script.endswith('.disabled'):
                    old = os.path.join(autoexec_path, script)
                    new = old + '.disabled'
                    try:
                        os.rename(old, new)
                    except:
                        pass
            
            # Enable script của game hiện tại
            for game_name, keywords in GAME_SCRIPTS.items():
                if game_name.lower() in current_game.lower():
                    for script in scripts:
                        for keyword in keywords:
                            if keyword in script.lower():
                                disabled = os.path.join(autoexec_path, script + '.disabled')
                                enabled = os.path.join(autoexec_path, script.replace('.disabled', ''))
                                if os.path.exists(disabled):
                                    try:
                                        os.rename(disabled, enabled)
                                        msg_done(f"Enabled: {script}")
                                    except:
                                        pass
            
            msg_done("Đã cập nhật scripts theo game")
        else:
            msg_warn("Không xác định được game hiện tại")
        
        time.sleep(2)
    
    elif choice == "3":
        # Disable tất cả
        disabled_count = 0
        for script in scripts:
            if not script.endswith('.disabled'):
                old = os.path.join(autoexec_path, script)
                new = old + '.disabled'
                try:
                    os.rename(old, new)
                    disabled_count += 1
                except:
                    pass
        
        msg_done(f"Đã disable {disabled_count} scripts")
        time.sleep(2)

def setup_low_ram():
    global LOW_RAM_ALERT, LOW_RAM_MB, LOW_RAM_AUTO_CLEAN
    clear_screen()
    section_title("CẢNH BÁO RAM THẤP")
    free = get_free_ram_mb()
    print(f"Trạng thái: {'BẬT' if LOW_RAM_ALERT else 'TẮT'} | Ngưỡng: {LOW_RAM_MB} MB | Tự dọn cache: {'BẬT' if LOW_RAM_AUTO_CLEAN else 'TẮT'}")
    print(f"RAM trống hiện tại: {str(free) + ' MB' if free is not None else 'không đọc được'}")
    print("Khi đang Start mà RAM trống dưới ngưỡng: cảnh báo trên màn hình + Discord và tự dọn cache.")
    print(f"{C.LPUR}[1]{C.R} {C.WHT}Bật cảnh báo{C.R}")
    print(f"{C.LPUR}[2]{C.R} {C.WHT}Tắt cảnh báo{C.R}")
    print(f"{C.LPUR}[3]{C.R} {C.WHT}Đổi ngưỡng RAM (MB){C.R}")
    print(f"{C.LPUR}[4]{C.R} {C.WHT}Bật / Tắt tự dọn cache khi RAM thấp{C.R}")
    print(f"{C.RED}[0] Quay lại{C.R}")
    sub = input("Chọn: ").strip()
    if sub == "1":
        LOW_RAM_ALERT = True
        msg = "Đã BẬT cảnh báo RAM thấp"
    elif sub == "2":
        LOW_RAM_ALERT = False
        msg = "Đã TẮT cảnh báo RAM thấp"
    elif sub == "3":
        v = input("Nhập ngưỡng RAM trống (200-4000 MB): ").strip()
        if v.isdigit() and 200 <= int(v) <= 4000:
            LOW_RAM_MB = int(v)
            msg = f"Đã đặt ngưỡng RAM thấp: {LOW_RAM_MB} MB"
        else:
            msg_cancel("Chỉ nhận số từ 200 đến 4000, giữ nguyên ngưỡng hiện tại.")
            time.sleep(1.5)
            return
    elif sub == "4":
        LOW_RAM_AUTO_CLEAN = not LOW_RAM_AUTO_CLEAN
        msg = f"Tự dọn cache khi RAM thấp: {'BẬT' if LOW_RAM_AUTO_CLEAN else 'TẮT'}"
    elif sub == "0":
        msg_cancel("Đã quay lại menu Set up.")
        time.sleep(0.8)
        return
    else:
        msg_cancel("Lựa chọn không hợp lệ, không có gì thay đổi.")
        time.sleep(1.2)
        return
    save_config_file()
    msg_done(msg + " và lưu cấu hình.")
    time.sleep(2)

def menu_profile():
    while True:
        clear_screen()
        section_title("PROFILE CẤU HÌNH")
        if PROFILES:
            for n in sorted(PROFILES):
                print(f" {C.PUR}▸{C.R} {C.WHT}{n}{C.R} {C.GRY}({clip(profile_summary(PROFILES[n]), 42)}){C.R}")
        else:
            print(f" {C.GRY}Chưa có profile nào.{C.R}")
        print(f" {C.GRY}Hiện tại: {clip(profile_summary(profile_snapshot()), 46)}{C.R}\n")
        print(f"{C.LPUR}[1]{C.R} {C.WHT}Lưu cấu hình hiện tại thành profile{C.R}")
        print(f"{C.LPUR}[2]{C.R} {C.WHT}Nạp profile (đổi nhanh){C.R}")
        print(f"{C.LPUR}[3]{C.R} {C.WHT}Xóa profile{C.R}")
        print(f"{C.RED}[0] Quay lại{C.R}")
        sub = input("Chọn: ").strip()
        if sub == "1":
            announce_choice("1", "Lưu profile")
            name = input("Đặt tên profile (vd: Grow-2h): ").strip()[:20]
            if not name:
                msg_cancel("Chưa nhập tên, đã hủy.")
            elif name in PROFILES and input(f"Profile '{name}' đã có, ghi đè? (y/n): ").strip().lower() != "y":
                msg_cancel("Đã hủy, giữ nguyên profile cũ.")
            else:
                PROFILES[name] = profile_snapshot()
                save_config_file()
                msg_done(f"Đã lưu profile '{name}': {profile_summary(PROFILES[name])}")
            wait_enter()
        elif sub == "2":
            announce_choice("2", "Nạp profile")
            n = pick_profile("Nhập số profile cần nạp (Enter để hủy): ")
            if n:
                apply_profile(PROFILES[n])
                save_config_file()
                msg_done(f"Đã nạp profile '{n}': {profile_summary(PROFILES[n])}")
            else:
                msg_cancel("Không nạp profile nào.")
            wait_enter()
        elif sub == "3":
            announce_choice("3", "Xóa profile")
            n = pick_profile("Nhập số profile cần xóa (Enter để hủy): ")
            if n and input(f"Xóa profile '{n}'? (y/n): ").strip().lower() == "y":
                PROFILES.pop(n, None)
                save_config_file()
                msg_done(f"Đã xóa profile '{n}'.")
            else:
                msg_cancel("Không xóa profile nào.")
            wait_enter()
        elif sub == "0":
            msg_info("Quay lại menu Set up...")
            time.sleep(0.6)
            return
        else:
            invalid_choice(sub)

def menu_schedule():
    while True:
        clear_screen()
        section_title("HẸN GIỜ TỰ CHẠY / TỰ DỪNG")
        print(f" {C.GRY}Giờ tự chạy:{C.R} {C.WHT}{SCHEDULE.get('start') or 'tắt'}{C.R}   {C.GRY}Giờ tự dừng:{C.R} {C.WHT}{SCHEDULE.get('stop') or 'tắt'}{C.R}")
        print(f" {C.GRY}Tự chạy: để tool mở ở menu chính, đến giờ sẽ tự Start (mỗi ngày).{C.R}")
        print(f" {C.GRY}Tự dừng: đang Start mà đến giờ này thì tự dừng và quay về menu.{C.R}\n")
        print(f"{C.LPUR}[1]{C.R} {C.WHT}Đặt giờ tự chạy (HH:MM){C.R}")
        print(f"{C.LPUR}[2]{C.R} {C.WHT}Đặt giờ tự dừng (HH:MM){C.R}")
        print(f"{C.LPUR}[3]{C.R} {C.WHT}Tắt hẹn giờ{C.R}")
        print(f"{C.RED}[0] Quay lại{C.R}")
        sub = input("Chọn: ").strip()
        if sub in ("1", "2"):
            key = "start" if sub == "1" else "stop"
            name = "giờ tự chạy" if key == "start" else "giờ tự dừng"
            announce_choice(sub, f"Đặt {name}")
            raw = input("Nhập giờ dạng HH:MM, vd 08:30 (để trống để tắt mốc này): ")
            if not raw.strip():
                SCHEDULE[key] = ""
                save_config_file()
                msg_done(f"Đã tắt {name}.")
            else:
                hhmm = _parse_hhmm(raw)
                if hhmm:
                    SCHEDULE[key] = hhmm
                    if key == "start":
                        SCHED_FIRED.pop("start", None)
                    save_config_file()
                    msg_done(f"Đã đặt {name} = {hhmm} và lưu cấu hình.")
                else:
                    msg_err("Giờ không hợp lệ (dùng HH:MM, từ 00:00 đến 23:59).")
            wait_enter()
        elif sub == "3":
            announce_choice("3", "Tắt hẹn giờ")
            SCHEDULE["start"] = SCHEDULE["stop"] = ""
            save_config_file()
            msg_done("Đã tắt toàn bộ hẹn giờ.")
            wait_enter()
        elif sub == "0":
            msg_info("Quay lại menu Set up...")
            time.sleep(0.6)
            return
        else:
            invalid_choice(sub)

# ==================== BIỆT DANH (ALIAS) ====================
def menu_alias():
    while True:
        clear_screen()
        section_title("BIỆT DANH TAB (ALIAS)")
        packages = list_installed_packages()
        if not packages:
            msg_err(f"Không thấy package nào khớp '{PACKAGE_PREFIX}' (đổi ở mục [3] nếu clone đặt tên khác).")
            wait_enter()
            return
        for i, p in enumerate(packages, 1):
            al = ALIASES.get(p)
            atxt = f"{C.GRN}{al}{C.R}" if al else f"{C.GRY}(chưa đặt){C.R}"
            print(f" {C.LPUR}{i:>2}.{C.R} {C.WHT}{clip(p, 30)}{C.R} → {atxt}")
        print(f" {C.RED} 0. Quay lại{C.R}")
        c = input("Chọn tab để đặt / đổi biệt danh (số): ").strip()
        if c == "0":
            msg_info("Quay lại menu Set up...")
            time.sleep(0.6)
            return
        if not (c.isdigit() and 1 <= int(c) <= len(packages)):
            invalid_choice(c)
            continue
        p = packages[int(c) - 1]
        announce_choice(c, f"Tab {p}")
        name = input("Nhập biệt danh mới, tối đa 20 ký tự (để trống để xóa): ").strip()[:20]
        if name:
            ALIASES[p] = name
            save_config_file()
            msg_done(f"Đã đặt biệt danh: {p} → {name}")
        elif p in ALIASES:
            ALIASES.pop(p)
            save_config_file()
            msg_done(f"Đã xóa biệt danh của {p}.")
        else:
            msg_cancel("Không thay đổi.")
        wait_enter()

# ==================== KIỂM TRA MẠNG (bật / tắt) ====================
def setup_net_check():
    global NET_CHECK
    clear_screen()
    section_title("KIỂM TRA MẠNG TRƯỚC KHI REJOIN")
    print(f"Trạng thái: {'BẬT' if NET_CHECK else 'TẮT'}")
    print("Trước khi mở app / vào Map, tool ping 8.8.8.8. Mất mạng thì tạm dừng đếm ngược và chờ có mạng lại,")
    print("không cố mở app liên tục (gây văng). Đang mất mạng thì tab không bị coi là treo cứng.")
    print(f"{C.LPUR}[1]{C.R} {C.WHT}Bật{C.R}")
    print(f"{C.LPUR}[2]{C.R} {C.WHT}Tắt{C.R}")
    print(f"{C.LPUR}[3]{C.R} {C.WHT}Thử kiểm tra mạng ngay{C.R}")
    print(f"{C.RED}[0] Quay lại{C.R}")
    sub = input("Chọn: ").strip()
    if sub == "1":
        NET_CHECK = True
    elif sub == "2":
        NET_CHECK = False
    elif sub == "3":
        msg_info("Đang ping 8.8.8.8...")
        if is_online():
            msg_done("Có kết nối Internet.")
        else:
            msg_err("Không có kết nối Internet.")
        wait_enter()
        return
    elif sub == "0":
        msg_cancel("Đã quay lại menu Set up.")
        time.sleep(0.8)
        return
    else:
        msg_cancel("Lựa chọn không hợp lệ, không có gì thay đổi.")
        time.sleep(1.2)
        return
    save_config_file()
    msg_done(f"Đã {'BẬT' if NET_CHECK else 'TẮT'} kiểm tra mạng trước khi rejoin và lưu cấu hình.")
    time.sleep(2)

# ==================== LOW GRAPHICS ====================
def _xml_get(xml, name):
    m = re.search(r'<\w+\s+name="' + re.escape(name) + r'"\s*>([^<]*)<', xml)
    return m.group(1).strip() if m else None

def _xml_set(xml, tag, name, value):
    rx = re.compile(r'(<(\w+)\s+name="' + re.escape(name) + r'"\s*>)[^<]*(</\2>)')
    if rx.search(xml):
        return rx.sub(lambda m: m.group(1) + str(value) + m.group(3), xml, count=1)
    i = xml.rfind("</Properties>")
    return xml[:i] + f'<{tag} name="{name}">{value}</{tag}>\n' + xml[i:] if i != -1 else xml

def find_gfx_file(pkg):
    q = shlex.quote
    out = sh(f"find {q('/data/data/' + pkg)} {q('/sdcard/Android/data/' + pkg)} -maxdepth 6 -name {GFX_FILE} 2>/dev/null | head -n 1", timeout=12)
    first = out.splitlines()[0].strip() if out else ""
    return first if first.startswith("/") else None

def gfx_status(pkg):
    path = find_gfx_file(pkg)
    if not path:
        return None
    level = _xml_get(sh(f"cat {shlex.quote(path)}", timeout=10), "GraphicsQualityLevel")
    return "low" if level == "1" else "normal"

def _gfx_write(path, text):
    work = os.path.join(os.path.expanduser("~"), ".pain_gfx_tmp")
    try:
        with open(work, "w", encoding="utf-8") as f:
            f.write(text)
        sh(f"cat {shlex.quote(work)} > {shlex.quote(path)}", timeout=15)
        return get_file_size(path) == os.path.getsize(work)
    except Exception:
        return False
    finally:
        try:
            os.remove(work)
        except Exception:
            pass

# ==================== WEBHOOK: CHỈ CHẠY KHI ĐÃ SET URL ====================
def webhook_active():
    url = (WEBHOOK_URL or "").strip()
    return url.lower().startswith(("https://", "http://"))

# ==================== LỊCH TỰ ĐỘNG RESTART ====================
AUTO_RESTART_CHOICES = (2, 3, 4)
AUTO_RESTART_ACTIONS = {"clean": "Dọn RAM + cache", "reset": "Reset toàn bộ tab (tắt Đa nhiệm + vào lại Map)"}

def auto_restart_label():
    if AUTO_RESTART_HOURS not in AUTO_RESTART_CHOICES:
        return "Tắt"
    return f"Mỗi {AUTO_RESTART_HOURS}h · {'Reset tab' if AUTO_RESTART_ACTION == 'reset' else 'Dọn RAM'}"

def auto_restart_due(last_ts, now=None):
    if AUTO_RESTART_HOURS not in AUTO_RESTART_CHOICES:
        return False
    now = time.time() if now is None else now
    return (now - last_ts) >= AUTO_RESTART_HOURS * 3600

def clean_cache_all(packages):
    for pkg in packages:
        sh(f"rm -rf /data/data/{pkg}/cache/* /data/data/{pkg}/code_cache/*")
    sh("sync && echo 3 > /proc/sys/vm/drop_caches")

def do_auto_restart(packages):
    reset = AUTO_RESTART_ACTION == "reset"
    what = AUTO_RESTART_ACTIONS.get(AUTO_RESTART_ACTION, "")
    ram_before = get_free_ram_mb()
    print(f"\033[1;33m[*] Đã treo liên tục {AUTO_RESTART_HOURS} giờ → tự động restart: {what}...\033[0m")
    log_event("AUTO_RESTART", detail=f"Sau {AUTO_RESTART_HOURS}h treo liên tục: {what} ({len(packages)} tab)")
    notify_async("restart", "Tự động restart",
                 f"Tool đã treo liên tục **{AUTO_RESTART_HOURS} giờ**, đang tự động: **{what}**.",
                 action=what)
    if root_mode():
        clean_cache_all(packages)
        ram_after = get_free_ram_mb()
        if ram_before is not None and ram_after is not None:
            print(f"\033[1;32m[+] Đã dọn cache + RAM: trống {ram_before} MB → {ram_after} MB\033[0m")
    else:
        print("\033[1;31m[!] Máy không có root: không dọn cache/RAM được.\033[0m")
    if reset and not stop_start:
        for pkg in packages:
            REJOIN_COUNT[pkg] = REJOIN_COUNT.get(pkg, 0) + 1
            close_game(pkg)
        if not wait_with_stop_check(3):
            launch_all(packages, hard=True)

def menu_auto_restart():
    global AUTO_RESTART_HOURS, AUTO_RESTART_ACTION
    while True:
        clear_screen()
        section_title("LỊCH TỰ ĐỘNG RESTART")
        print(f"Trạng thái: {auto_restart_label()}")
        print(f"Hành động khi đến hạn: {AUTO_RESTART_ACTIONS.get(AUTO_RESTART_ACTION)}")
        print(f" {C.GRY}Tính từ lúc bấm Start (hoặc lần restart trước). Chỉ chạy khi đang Start.{C.R}")
        print(f"{C.LPUR}[1]{C.R} {C.WHT}Tắt{C.R}")
        print(f"{C.LPUR}[2]{C.R} {C.WHT}Mỗi 2 giờ{C.R}")
        print(f"{C.LPUR}[3]{C.R} {C.WHT}Mỗi 3 giờ{C.R}")
        print(f"{C.LPUR}[4]{C.R} {C.WHT}Mỗi 4 giờ{C.R}")
        print(f"{C.LPUR}[5]{C.R} {C.WHT}Hành động: chỉ dọn RAM + cache{C.R}")
        print(f"{C.LPUR}[6]{C.R} {C.WHT}Hành động: reset toàn bộ tab (tắt Đa nhiệm + vào lại Map){C.R}")
        print(f"{C.RED}[0] Quay lại{C.R}")
        sub = input("Chọn: ").strip()
        if sub == "1":
            AUTO_RESTART_HOURS = 0
        elif sub in ("2", "3", "4"):
            AUTO_RESTART_HOURS = int(sub)
        elif sub == "5":
            AUTO_RESTART_ACTION = "clean"
        elif sub == "6":
            AUTO_RESTART_ACTION = "reset"
        elif sub == "0":
            return
        else:
            invalid_choice(sub)
            continue
        save_config_file()
        msg_done(f"Đã lưu: {auto_restart_label()}")
        time.sleep(1.2)

# ==================== GRAPHICS OPTIMIZER (ĐỒ HỌA THẤP + GIỚI HẠN FPS) ====================
GFX_FPS_CHOICES = (15, 20, 30)

def gfx_settings_label():
    parts = []
    parts.append("Đồ họa thấp" if GFX_LOW else "giữ đồ họa")
    parts.append(f"FPS {GFX_FPS}" if GFX_FPS else "FPS không giới hạn")
    return " · ".join(parts)

def gfx_read(pkg):
    path = find_gfx_file(pkg)
    if not path:
        return None
    xml = sh(f"cat {shlex.quote(path)}", timeout=10)
    cap = _xml_get(xml, "FramerateCap")
    try:
        fps = int(cap) if cap is not None else None
    except ValueError:
        fps = None
    return {"path": path, "low": _xml_get(xml, "GraphicsQualityLevel") == "1", "fps": fps}

def gfx_satisfied(info, low, fps):
    return bool(info) and (not low or info["low"]) and (not fps or info["fps"] == fps)

def gfx_apply(pkg, low=True, fps=0):
    info = gfx_read(pkg)
    if not info:
        return False, f"chưa có file {GFX_FILE} (hãy mở tab 1 lần rồi thử lại)"
    if not low and not fps:
        return False, "chưa chọn mục nào để áp dụng (đồ họa thấp / giới hạn FPS)"
    if gfx_satisfied(info, low, fps):
        return True, "đã đúng cài đặt, không cần đổi"
    q = shlex.quote
    path = info["path"]
    bak = path + ".painbak"
    close_game(pkg)
    xml = sh(f"cat {q(path)}", timeout=10)
    if "<Properties" not in xml:
        return False, "file cài đặt không đúng định dạng"
    if "1" not in sh(f"[ -f {q(bak)} ] && echo 1", timeout=5):
        sh(f"cat {q(path)} > {q(bak)}", timeout=10)
    new = xml
    if low:
        new = _xml_set(new, "int", "GraphicsQualityLevel", 1)
        new = _xml_set(new, "token", "SavedQualityLevel", 1)
    if fps:
        new = _xml_set(new, "int", "FramerateCap", int(fps))
    if not _gfx_write(path, new):
        return False, "ghi file cài đặt không thành công"
    after = gfx_read(pkg)
    if not gfx_satisfied(after, low, fps):
        return False, "ghi xong nhưng kiểm tra lại chưa đúng"
    done = []
    if low:
        done.append("đồ họa thấp nhất")
    if fps:
        done.append(f"giới hạn {fps} FPS")
    return True, "đã đặt " + " + ".join(done)

def gfx_restore(pkg):
    path = find_gfx_file(pkg)
    if not path:
        return False, f"chưa có file {GFX_FILE}"
    q = shlex.quote
    bak = path + ".painbak"
    if "1" not in sh(f"[ -f {q(bak)} ] && echo 1", timeout=5):
        return False, "chưa có bản gốc để khôi phục (tool chưa từng đổi tab này)"
    close_game(pkg)
    sh(f"cat {q(bak)} > {q(path)}", timeout=10)
    sh(f"rm -f {q(bak)}", timeout=5)
    return True, "đã khôi phục đồ họa gốc"

def apply_gfx_on_start(packages):
    if not GFX_AUTO or not (GFX_LOW or GFX_FPS):
        return
    if not root_mode():
        return
    print(f"\033[1;33m[*] Graphics Optimizer: {gfx_settings_label()} cho {len(packages)} tab...\033[0m")
    n_ok = 0
    for pkg in packages:
        if stop_start:
            return
        ok, msg = gfx_apply(pkg, GFX_LOW, GFX_FPS)
        n_ok += 1 if ok else 0
        color = "\033[1;32m[+]" if ok else "\033[1;31m[!]"
        print(f"{color} {tab_label(pkg)}: {msg}\033[0m")
    log_event("GFX_AUTO", detail=f"{gfx_settings_label()}: {n_ok}/{len(packages)} tab")

def menu_low_graphics():
    global GFX_LOW, GFX_FPS, GFX_AUTO
    while True:
        clear_screen()
        section_title("GRAPHICS OPTIMIZER")
        print(f"Cài đặt: {C.WHT}{gfx_settings_label()}{C.R}   Tự áp dụng khi Start: {C.WHT}{'Bật' if GFX_AUTO else 'Tắt'}{C.R}")
        print(f" {C.GRY}Sửa file {GFX_FILE} của từng tab. Tab đang chạy sẽ bị tắt để áp dụng.{C.R}")
        print(f"{C.LPUR}[1]{C.R} {C.WHT}Áp dụng ngay cho tất cả tab{C.R}")
        print(f"{C.LPUR}[2]{C.R} {C.WHT}Đồ họa thấp nhất [{'Bật' if GFX_LOW else 'Tắt'}]{C.R}")
        print(f"{C.LPUR}[3]{C.R} {C.WHT}Giới hạn FPS [{GFX_FPS if GFX_FPS else 'Không giới hạn'}]{C.R}")
        print(f"{C.LPUR}[4]{C.R} {C.WHT}Khôi phục cài đặt gốc (tất cả tab){C.R}")
        print(f"{C.LPUR}[5]{C.R} {C.WHT}Xem trạng thái các tab{C.R}")
        print(f"{C.LPUR}[6]{C.R} {C.WHT}Tự áp dụng khi Start [{'Bật' if GFX_AUTO else 'Tắt'}]{C.R}")
        print(f"{C.RED}[0] Quay lại{C.R}")
        sub = input("Chọn: ").strip()
        if sub == "0":
            return
        if sub == "2":
            GFX_LOW = not GFX_LOW
        elif sub == "3":
            v = input("Giới hạn FPS: 15 / 20 / 30 (nhập 0 = không giới hạn): ").strip()
            if v == "0":
                GFX_FPS = 0
            elif v.isdigit() and int(v) in GFX_FPS_CHOICES:
                GFX_FPS = int(v)
            else:
                msg_err("Chỉ nhận 15, 20, 30 hoặc 0.")
                time.sleep(1.5)
                continue
        elif sub == "6":
            GFX_AUTO = not GFX_AUTO
        elif sub in ("1", "4", "5"):
            if not root_mode():
                msg_err("Cần quyền root để sửa file cài đặt của Roblox.")
                wait_enter()
                continue
            packages = list_installed_packages()
            if not packages:
                msg_err(f"Không thấy package nào khớp '{PACKAGE_PREFIX}'.")
                wait_enter()
                continue
            msg_info("Đang đọc trạng thái đồ họa các tab...")
            infos = {p: gfx_read(p) for p in packages}
            for p in packages:
                i = infos[p]
                if not i:
                    print(f" {dot(None)} {C.WHT}{tab_label(p)}{C.R}: {C.GRY}chưa có file cài đặt{C.R}")
                else:
                    print(f" {dot(i['low'])} {C.WHT}{tab_label(p)}{C.R}: {C.GRY}{'Đồ họa thấp' if i['low'] else 'Đồ họa thường'} · FPS {i['fps'] if i['fps'] else 'mặc định'}{C.R}")
            have = [p for p in packages if infos[p]]
            if sub == "5":
                wait_enter()
                continue
            if not have:
                msg_warn("Chưa tab nào có file cài đặt. Hãy mở các tab 1 lần rồi quay lại.")
                wait_enter()
                continue
            action = f"ÁP DỤNG ({gfx_settings_label()})" if sub == "1" else "KHÔI PHỤC cài đặt gốc"
            if input(f"Bấm Enter để {action} cho {len(have)} tab (nhập 0 để hủy): ").strip() == "0":
                msg_cancel("Đã hủy, không thay đổi gì.")
                wait_enter()
                continue
            n_ok = 0
            for p in have:
                ok, msg = gfx_apply(p, GFX_LOW, GFX_FPS) if sub == "1" else gfx_restore(p)
                n_ok += 1 if ok else 0
                (msg_ok if ok else msg_err)(f"{tab_label(p)}: {msg}")
            log_event("GFX", detail=f"{action}: {n_ok}/{len(have)} tab")
            msg_done(f"Hoàn tất: {n_ok}/{len(have)} tab thành công. Mở lại tab bằng Start hoặc mục [8].")
            wait_enter()
            continue
        else:
            invalid_choice(sub)
            continue
        save_config_file()
        msg_done(f"Đã lưu: {gfx_settings_label()} · Tự áp dụng khi Start: {'Bật' if GFX_AUTO else 'Tắt'}")
        time.sleep(1.2)

# ==================== XEM LOG ====================
LOG_ERROR_KINDS = ("KICK", "CRASH", "FREEZE", "SCREEN", "JOIN_ERR", "REJOIN_FAIL", "LOBBY", "LOW_RAM", "NET_DOWN", "VIP_EXPIRED")
LOG_KIND_COLOR = {
    "KICK": C.RED, "CRASH": C.RED, "FREEZE": C.RED, "JOIN_ERR": C.RED, "REJOIN_FAIL": C.RED,
    "LOBBY": C.YEL, "LOW_RAM": C.YEL, "NET_DOWN": C.YEL, "SCREEN": C.RED, "KEY": C.CYN,
    "REJOIN_OK": C.GRN, "START": C.GRN, "NET_UP": C.GRN,
    "STOP": C.GRY, "HOP": C.CYN, "HOP_FAIL": C.YEL, "HOP_PAUSE": C.YEL, "BLACKSCREEN": C.CYN, "CYCLE": C.CYN, "SCHEDULE": C.CYN, "AUTO_RESTART": C.CYN, "GFX": C.CYN, "GFX_AUTO": C.CYN, "LOW_GFX": C.CYN,
    "VIP_EXPIRED": C.RED, "GAME_PAUSE": C.YEL, "GAME_RESUME": C.GRN,
}

STABILITY_DROP_KINDS = ("KICK", "LOBBY", "SCREEN", "FREEZE", "REJOIN_FAIL", "VIP_EXPIRED")

def parse_log_line(line):
    parts = [p.strip() for p in line.rstrip("\n").split(" | ")]
    if len(parts) < 3:
        return {"time": "", "kind": "", "pkg": "", "code": "", "rejoin": "", "detail": line.strip(), "raw": line.strip()}
    code = rejoin = ""
    detail = []
    for p in parts[3:]:
        if p.startswith("code=") and not code:
            code = p[5:]
        elif re.fullmatch(r"rejoin#\d+", p) and not rejoin:
            rejoin = p[7:]
        else:
            detail.append(p)
    return {"time": parts[0], "kind": parts[1], "pkg": "" if parts[2] == "-" else parts[2],
            "code": code, "rejoin": rejoin, "detail": " | ".join(detail), "raw": line.strip()}

def read_log_entries():
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
            return [parse_log_line(l) for l in f if l.strip()]
    except OSError:
        return []

def filter_log(entries, mode="all", arg=None):
    if mode == "errors":
        return [e for e in entries if e["kind"] in LOG_ERROR_KINDS]
    if mode == "pkg":
        return [e for e in entries if e["pkg"] == arg]
    if mode == "search":
        needle = (arg or "").lower()
        return [e for e in entries if needle and needle in e["raw"].lower()]
    if mode == "session":
        last = max((i for i, e in enumerate(entries) if e["kind"] == "START"), default=0)
        return entries[last:]
    return list(entries)

def wrap_width(text, width):
    lines, cur, w = [], "", 0
    for ch in str(text):
        cw = _cw(ch)
        if w + cw > width:
            lines.append(cur)
            cur, w = "", 0
        cur += ch
        w += cw
    if cur or not lines:
        lines.append(cur)
    return lines

def render_log_entry(e, width):
    color = LOG_KIND_COLOR.get(e["kind"], C.WHT)
    stamp = e["time"][5:] if len(e["time"]) >= 19 else e["time"]
    head = f"{C.GRY}{stamp}{C.R} {color}{e['kind'] or 'LOG'}{C.R}"
    pkg_line = None
    if e["pkg"]:
        room = width - vlen(stamp) - len(e["kind"] or "LOG") - 2
        if room >= 8:
            head += f" {C.WHT}{clip(tab_label(e['pkg']), room)}{C.R}"
        else:
            pkg_line = f"  {C.WHT}{clip(tab_label(e['pkg']), width - 2)}{C.R}"
    extra = []
    if e["code"]:
        extra.append(f"mã lỗi {e['code']}")
    if e["rejoin"]:
        extra.append(f"rejoin #{e['rejoin']}")
    text = " · ".join(extra + ([e["detail"]] if e["detail"] else []))
    out = [head] + ([pkg_line] if pkg_line else [])
    for ln in wrap_width(text, width - 2) if text else []:
        out.append(f"  {C.GRY}{ln}{C.R}")
    return out

def paginate(items, per_page, page):
    total_pages = max(1, -(-len(items) // per_page))
    page = min(max(page, 0), total_pages - 1)
    end = len(items) - page * per_page
    return items[max(0, end - per_page):end], total_pages, page

def show_log_pages(entries, title):
    if not entries:
        msg_warn("Không có dòng log nào khớp.")
        wait_enter()
        return
    page = 0
    while True:
        try:
            rows = shutil.get_terminal_size((58, 24)).lines
        except Exception:
            rows = 24
        per_page = max(4, min(12, (rows - 8) // 3))
        chunk, pages, page = paginate(entries, per_page, page)
        clear_screen()
        section_title(f"{title} ({len(entries)} dòng)")
        width = ui_width() - 2
        for e in chunk:
            for ln in render_log_entry(e, width):
                print(ln)
        print(f"\n {C.GRY}Trang {pages - page}/{pages} (mới nhất ở cuối) · Enter = cũ hơn · n = mới hơn · q = thoát{C.R}")
        cmd = input("› ").strip().lower()
        if cmd in ("q", "0", "x"):
            return
        page = page - 1 if cmd in ("n", "m") else page + 1
        if page < 0:
            page = 0

def menu_view_log():
    while True:
        clear_screen()
        section_title("XEM LOG")
        entries = read_log_entries()
        try:
            size_kb = os.path.getsize(LOG_FILE) // 1024
        except OSError:
            size_kb = 0
        n_err = sum(1 for e in entries if e["kind"] in LOG_ERROR_KINDS)
        print(f" {C.GRY}{LOG_FILE}  ·  {len(entries)} dòng ({size_kb} KB) · {n_err} lỗi{C.R}")
        print(f"{C.LPUR}[1]{C.R} {C.WHT}Xem log mới nhất{C.R}")
        print(f"{C.LPUR}[2]{C.R} {C.WHT}Chỉ xem lỗi (Kick / Crash / Treo / Lobby / Rejoin thất bại...){C.R}")
        print(f"{C.LPUR}[3]{C.R} {C.WHT}Phiên chạy gần nhất (từ lần Start cuối){C.R}")
        print(f"{C.LPUR}[4]{C.R} {C.WHT}Lọc theo tab{C.R}")
        print(f"{C.LPUR}[5]{C.R} {C.WHT}Tìm theo từ khóa / mã lỗi{C.R}")
        print(f"{C.LPUR}[6]{C.R} {C.WHT}Xóa toàn bộ log{C.R}")
        print(f"{C.RED}[0] Quay lại menu chính{C.R}")
        sub = input("Chọn: ").strip()
        if sub == "1":
            show_log_pages(filter_log(entries), "LOG MỚI NHẤT")
        elif sub == "2":
            show_log_pages(filter_log(entries, "errors"), "LOG LỖI")
        elif sub == "3":
            show_log_pages(filter_log(entries, "session"), "PHIÊN GẦN NHẤT")
        elif sub == "4":
            pkgs = sorted({e["pkg"] for e in entries if e["pkg"]})
            if not pkgs:
                msg_warn("Log chưa có dòng nào gắn với tab.")
                wait_enter()
                continue
            for i, p in enumerate(pkgs, 1):
                print(f"\033[1;37m{i}. {tab_label(p)}\033[0m")
            pick = input("Chọn tab (Enter để hủy): ").strip()
            if pick.isdigit() and 1 <= int(pick) <= len(pkgs):
                show_log_pages(filter_log(entries, "pkg", pkgs[int(pick) - 1]), f"LOG TAB {tab_label(pkgs[int(pick) - 1])}")
        elif sub == "5":
            kw = input("Nhập từ khóa hoặc mã lỗi (vd 279, kick, treo): ").strip()
            if kw:
                show_log_pages(filter_log(entries, "search", kw), f"TÌM '{kw}'")
        elif sub == "6":
            if input("Xóa toàn bộ log? Không thể khôi phục. (y/N): ").strip().lower() == "y":
                try:
                    with _LOG_LOCK:
                        open(LOG_FILE, "w", encoding="utf-8").close()
                    msg_done("Đã xóa log.")
                except OSError as e:
                    msg_err(f"Không xóa được log: {e}")
                wait_enter()
        elif sub == "0":
            return
        else:
            invalid_choice(sub)

# ==================== THỐNG KÊ ĐỘ ỔN ĐỊNH ====================
def _parse_log_time(e):
    try:
        return datetime.strptime(e["time"], "%Y-%m-%d %H:%M:%S")
    except (ValueError, KeyError):
        return None

def _game_name_per_entry(entries):
    current = "(không rõ)"
    out = []
    for e in entries:
        if e["kind"] == "START":
            m = re.search(r"game=(.*?)(?: \| |$)", e["detail"])
            if m and m.group(1).strip():
                current = m.group(1).strip()
        out.append(current)
    return out

def build_stability_stats(entries):
    games = _game_name_per_entry(entries)
    per_pkg, per_game = {}, {}
    for e, game in zip(entries, games):
        if e["kind"] not in STABILITY_DROP_KINDS:
            continue
        t = _parse_log_time(e)
        pkg = e["pkg"] or "(không rõ tab)"
        for store, key in ((per_pkg, pkg), (per_game, game)):
            d = store.setdefault(key, {"total": 0, "kinds": {}, "codes": {}, "times": []})
            d["total"] += 1
            d["kinds"][e["kind"]] = d["kinds"].get(e["kind"], 0) + 1
            if e["code"]:
                d["codes"][e["code"]] = d["codes"].get(e["code"], 0) + 1
            if t:
                d["times"].append(t)
    for store in (per_pkg, per_game):
        for d in store.values():
            d["times"].sort()
            gaps = [(b - a).total_seconds() for a, b in zip(d["times"], d["times"][1:])]
            d["avg_gap"] = (sum(gaps) / len(gaps)) if gaps else None
            del d["times"]
    return per_pkg, per_game

def _top_n(counter_dict, n=3):
    return sorted(counter_dict.items(), key=lambda kv: -kv[1])[:n]

def _stability_line(d, vw):
    codes = ", ".join(f"{c}×{n}" for c, n in _top_n(d["codes"])) or "không rõ mã"
    kinds = ", ".join(f"{k}:{n}" for k, n in _top_n(d["kinds"], 4))
    gap = fmt_duration(d["avg_gap"]) if d["avg_gap"] else "—"
    text = f"{d['total']} lần ({kinds}) · mã hay gặp: {codes} · TB giữa 2 lần: {gap}"
    return clip(text, vw)

def menu_stability_stats():
    clear_screen()
    section_title("THỐNG KÊ ĐỘ ỔN ĐỊNH")
    entries = read_log_entries()
    if not entries:
        msg_warn("Chưa có log nào để thống kê. Hãy Start tool một thời gian rồi xem lại mục này.")
        wait_enter()
        return
    per_pkg, per_game = build_stability_stats(entries)
    if not per_pkg and not per_game:
        msg_warn(f"Log có {len(entries)} dòng nhưng chưa ghi nhận lần Kick/Rớt/Treo nào.")
        wait_enter()
        return
    w = ui_width()
    inner = w - 4
    lw = 14
    vw = max(10, inner - lw - 1)
    print(box_top(w))
    print(box_row(f"{C.WHT}THEO TỪNG GAME{C.R}", w, "center"))
    print(box_sep(w))
    for game in sorted(per_game, key=lambda k: -per_game[k]["total"]):
        print(box_kv(clip(game, lw), f"{C.WHT}{_stability_line(per_game[game], vw)}{C.R}", w, lw))
    print(box_sep(w))
    print(box_row(f"{C.WHT}THEO TỪNG TAB{C.R}", w, "center"))
    print(box_sep(w))
    for pkg in sorted(per_pkg, key=lambda k: -per_pkg[k]["total"]):
        label = tab_label(pkg) if pkg != "(không rõ tab)" else pkg
        print(box_kv(clip(label, lw), f"{C.WHT}{_stability_line(per_pkg[pkg], vw)}{C.R}", w, lw))
    print(box_bot(w))
    total_drops = sum(d["total"] for d in per_pkg.values())
    print(f" {C.GRY}Tổng {total_drops} lần kick/rớt trong {len(entries)} dòng log của {LOG_FILE}{C.R}")
    print(f" {C.GRY}Loại tính là 1 lần kick/rớt: {', '.join(STABILITY_DROP_KINDS)}{C.R}")
    wait_enter()


# ==================== AUTO-EXEC MANAGER ====================
def autoexec_dirs():
    dirs = [f"/sdcard/{n}/Autoexec" for n in EXECUTOR_NAMES]
    for pkg in list_installed_packages():
        dirs.append(f"/sdcard/Android/data/{pkg}/files/autoexec")
    return dirs

def _path_exists(p):
    if os.path.exists(p):
        return True
    return bool(root_mode()) and "1" in sh(f"[ -e {shlex.quote(p)} ] && echo 1", timeout=5)

def _ls_dir(d):
    out = run_cmd(["ls", "-1", d])
    if not out and root_mode():
        out = sh(f"ls -1 {shlex.quote(d)} 2>/dev/null", timeout=6)
    return [x.strip() for x in out.splitlines() if x.strip()]

def _move(a, b):
    run_cmd(["mv", "-f", a, b])
    if _path_exists(b) and not _path_exists(a):
        return True
    if root_mode():
        sh(f"mv -f {shlex.quote(a)} {shlex.quote(b)}", timeout=8)
    return _path_exists(b) and not _path_exists(a)

def autoexec_dir_label(d):
    m = re.match(r"/sdcard/([^/]+)/Autoexec$", d)
    if m:
        return m.group(1)
    m = re.match(r"/sdcard/Android/data/([^/]+)/files/autoexec$", d)
    return f"tab: {tab_label(m.group(1))}" if m else d

def scan_autoexec():
    items = []
    for d in autoexec_dirs():
        for fn in sorted(_ls_dir(d)):
            if fn.endswith(".lua.disabled"):
                items.append((d, fn, False))
            elif fn.endswith(".lua"):
                items.append((d, fn, True))
    return items

def toggle_script(item, enable):
    d, fn, cur = item
    if cur == enable:
        return True
    dst = fn[:-len(".disabled")] if enable else fn + ".disabled"
    return _move(f"{d}/{fn}", f"{d}/{dst}")

def autoexec_manager():
    while True:
        clear_screen()
        section_title("AUTO-EXEC MANAGER")
        items = scan_autoexec()
        if not items:
            msg_warn("Không thấy script .lua nào trong các thư mục Autoexec. Dùng [1] Import script mới trước.")
            wait_enter()
            return
        last_dir = None
        for i, (d, fn, en) in enumerate(items, 1):
            if d != last_dir:
                print(f" {C.PUR}▸ {autoexec_dir_label(d)}{C.R}")
                last_dir = d
            mark = f"{C.GRN}[ON ]{C.R}" if en else f"{C.RED}[OFF]{C.R}"
            name = fn[:-len(".disabled")] if fn.endswith(".disabled") else fn
            print(f"  {C.LPUR}{i:>2}.{C.R} {mark} {C.WHT}{name}{C.R}")
        print(f"\n {C.GRY}Nhập số để bật/tắt (nhiều số cách nhau bằng dấu cách) · a = bật tất cả · d = tắt tất cả · 0 = quay lại{C.R}")
        raw = input("Chọn: ").strip().lower()
        if raw == "0":
            msg_info("Quay lại menu Auto Execute...")
            time.sleep(0.6)
            return
        if not raw:
            continue
        if raw in ("a", "d"):
            enable = raw == "a"
            announce_choice(raw, "Bật tất cả script" if enable else "Tắt tất cả script")
            n_ok = sum(1 for it in items if toggle_script(it, enable))
            msg_done(f"Đã {'bật' if enable else 'tắt'} {n_ok}/{len(items)} script.")
            wait_enter()
            continue
        nums = sorted(set(x for x in re.split(r"[,\s]+", raw) if x))
        if not all(x.isdigit() and 1 <= int(x) <= len(items) for x in nums):
            invalid_choice(raw)
            continue
        for x in nums:
            it = items[int(x) - 1]
            new_state = not it[2]
            nm = it[1][:-len(".disabled")] if it[1].endswith(".disabled") else it[1]
            if toggle_script(it, new_state):
                msg_done(f"{nm}: đã {'BẬT' if new_state else 'TẮT'} ({autoexec_dir_label(it[0])})")
            else:
                msg_err(f"{nm}: không đổi được trạng thái (thiếu quyền ghi?)")
        wait_enter()

def menu_import_autoexec():
    while True:
        clear_screen()
        section_title("AUTO EXECUTE")
        print(f"{C.LPUR}[1]{C.R} {C.WHT}Import script mới{C.R}")
        print(f"{C.LPUR}[2]{C.R} {C.WHT}Quản lý script (bật / tắt từng script){C.R}")
        print(f"{C.RED}[0] Quay lại menu chính{C.R}")
        sub = input("Chọn: ").strip()
        if sub == "1":
            announce_choice("1", "Import script mới")
            import_autoexec_script()
        elif sub == "2":
            announce_choice("2", "Quản lý script")
            autoexec_manager()
        elif sub == "0":
            msg_info("Quay lại menu chính...")
            time.sleep(0.6)
            return
        else:
            invalid_choice(sub)

# ==================== GAME PROFILES (THEO TỪ GAME) ====================
def menu_game_profiles():
    while True:
        clear_screen()
        section_title("CÀI ĐẶT HỒSƠ THEO GAME")
        print(f" {C.GRY}Thiết lập delay rejoin, freeze timeout, FPS, server hop riêng cho mỗi game.{C.R}\n")

        if GAME_PROFILES:
            print(f" {C.WHT}Các game đã có hồ sơ riêng ({len(GAME_PROFILES)}):{C.R}")
            for i, (game_name, profile) in enumerate(sorted(GAME_PROFILES.items()), 1):
                delay = profile.get("delay_rejoin_min", DELAY_REJOIN_MINUTES)
                freeze = profile.get("freeze_timeout_sec", FREEZE_TIMEOUT_MIN * 60)
                fps = profile.get("target_fps", GFX_FPS)
                hop = "✓" if profile.get("server_hop_enabled") else "✗"
                print(f"  {C.LPUR}{i}.{C.R} {C.WHT}{game_name:20}{C.R} Delay:{delay}m Freeze:{freeze}s FPS:{fps} Hop:{hop}")
            print()

        print(f"{C.LPUR}[1]{C.R} {C.WHT}Tạo/Sửa hồ sơ game{C.R}")
        print(f"{C.LPUR}[2]{C.R} {C.WHT}Xóa hồ sơ game{C.R}")
        print(f"{C.LPUR}[3]{C.R} {C.WHT}Sao chép hồ sơ từ game khác{C.R}")
        print(f"\033[1;32m0. Quay lại menu chính{C.R}")
        sub = input("Chọn: ").strip()

        if sub == "1":
            game_name = input(f"Nhập tên game (để trống để xem danh sách): ").strip()
            if not game_name:
                print(f"\n {C.GRY}Danh sách game có sẵn:{C.R}")
                for i, (gn, gid) in enumerate(GAMES.items(), 1):
                    print(f"  {C.WHT}{gn:3}. {gid[0]}{C.R}")
                wait_enter()
                continue

            if game_name not in GAME_PROFILES:
                GAME_PROFILES[game_name] = {
                    "delay_rejoin_min": DELAY_REJOIN_MINUTES,
                    "freeze_timeout_sec": FREEZE_TIMEOUT_MIN * 60,
                    "target_fps": GFX_FPS,
                    "server_hop_enabled": SERVER_HOP,
                }
                msg_info(f"Đã tạo hồ sơ cho '{game_name}'")

            profile = GAME_PROFILES[game_name]
            announce_choice("1", f"Sửa hồ sơ: {game_name}")

            print(f"\n {C.WHT}Cài đặt cho: {game_name}{C.R}")
            print(f"  Delay rejoin (phút): {profile.get('delay_rejoin_min')} [để trống = giữ nguyên]")
            val = input("  → Nhập giá trị mới (1-30): ").strip()
            if val.isdigit() and 1 <= int(val) <= 30:
                profile["delay_rejoin_min"] = int(val)
                msg_done(f"Delay rejoin: {val} phút")

            print(f"  Freeze timeout (giây): {profile.get('freeze_timeout_sec')} [để trống = giữ nguyên]")
            val = input("  → Nhập giá trị mới (60-600): ").strip()
            if val.isdigit() and 60 <= int(val) <= 600:
                profile["freeze_timeout_sec"] = int(val)
                msg_done(f"Freeze timeout: {val} giây")

            print(f"  Target FPS: {profile.get('target_fps')} [để trống = giữ nguyên]")
            print(f"    (0=auto, 15/20/30=fixed)")
            val = input("  → Nhập giá trị mới: ").strip()
            if val and val.isdigit() and int(val) in (0, 15, 20, 30):
                profile["target_fps"] = int(val)
                msg_done(f"Target FPS: {val}")

            hop_str = "Y/n" if profile.get("server_hop_enabled") else "y/N"
            val = input(f"  Server Hop ({hop_str}): ").strip().lower()
            if val in ("y", "yes"):
                profile["server_hop_enabled"] = True
                msg_done("Server Hop: Bật")
            elif val in ("n", "no"):
                profile["server_hop_enabled"] = False
                msg_done("Server Hop: Tắt")

            save_config_file()
            wait_enter()

        elif sub == "2":
            if not GAME_PROFILES:
                msg_warn("Chưa có hồ sơ game nào để xóa.")
                wait_enter()
                continue
            game_name = input("Nhập tên game để xóa hồ sơ: ").strip()
            if game_name in GAME_PROFILES:
                del GAME_PROFILES[game_name]
                msg_done(f"Đã xóa hồ sơ '{game_name}'")
                save_config_file()
            else:
                msg_warn(f"Không tìm thấy hồ sơ '{game_name}'")
            wait_enter()

        elif sub == "3":
            if not GAME_PROFILES:
                msg_warn("Chưa có hồ sơ nào để sao chép.")
                wait_enter()
                continue
            source = input("Sao chép từ game: ").strip()
            if source not in GAME_PROFILES:
                msg_warn(f"Không tìm thấy hồ sơ '{source}'")
                wait_enter()
                continue
            dest = input("Sao chép tới game: ").strip()
            if not dest:
                msg_cancel("Hủy sao chép")
                wait_enter()
                continue
            GAME_PROFILES[dest] = GAME_PROFILES[source].copy()
            msg_done(f"Đã sao chép hồ sơ từ '{source}' tới '{dest}'")
            save_config_file()
            wait_enter()

        elif sub == "0":
            msg_info("Quay lại menu chính...")
            time.sleep(0.6)
            return
        else:
            invalid_choice(sub)

# ==================== EXECUTOR BINDING (GÁN EXECUTOR CHO TAB) ====================
def menu_executor_binding():
    while True:
        clear_screen()
        section_title("GÁN EXECUTOR CHO TAB")
        print(f" {C.GRY}Chọn executor nào sẽ chạy cho từng tab clone.{C.R}\n")

        packages = sorted(get_all_packages())
        if not packages:
            msg_warn("Chưa cài tab clone nào. Dùng mục 'Mở tab clone' trước.")
            wait_enter()
            return

        print(f" {C.WHT}Danh sách executor có sẵn:{C.R}")
        for i, exe in enumerate(EXECUTOR_NAMES, 1):
            print(f"  {i:2}. {exe}")
        print()

        print(f" {C.WHT}Tab hiện tại và executor được gán:{C.R}")
        for i, pkg in enumerate(packages, 1):
            short = ALIASES.get(pkg) or pkg[len(PACKAGE_PREFIX):].lstrip(".") if pkg.startswith(PACKAGE_PREFIX) else pkg
            exe = EXECUTOR_BINDING.get(pkg, "—")
            exe_display = exe if exe in EXECUTOR_NAMES else "—"
            print(f"  {C.LPUR}{i:>2}.{C.R} {C.WHT}{short:20}{C.R} → {C.YEL}{exe_display}{C.R}")
        print()

        print(f"\033[1;37m[Nhập số tab] [Nhập số executor] để gán (vd: 1 2 = Tab 1 dùng Codex){C.R}")
        print(f"{C.RED}[0] Quay lại{C.R}")
        sub = input("Chọn: ").strip()

        if sub == "0":
            msg_info("Quay lại menu chính...")
            time.sleep(0.6)
            return

        parts = sub.split()
        if len(parts) != 2:
            invalid_choice(sub)
            wait_enter()
            continue

        if not (parts[0].isdigit() and parts[1].isdigit()):
            invalid_choice(sub)
            wait_enter()
            continue

        tab_idx = int(parts[0]) - 1
        exe_idx = int(parts[1]) - 1

        if not (0 <= tab_idx < len(packages)) or not (0 <= exe_idx < len(EXECUTOR_NAMES)):
            msg_err("Chỉ số tab hoặc executor không hợp lệ.")
            wait_enter()
            continue

        pkg = packages[tab_idx]
        exe = EXECUTOR_NAMES[exe_idx]
        EXECUTOR_BINDING[pkg] = exe

        short = ALIASES.get(pkg) or pkg[len(PACKAGE_PREFIX):].lstrip(".") if pkg.startswith(PACKAGE_PREFIX) else pkg
        msg_done(f"Đã gán {exe} cho tab: {short}")
        save_config_file()
        wait_enter()

MENU_NAMES = {
    "1": "Bắt đầu", 
    "2": "Thiết lập cơ bản", 
    "3": "Thiết lập prefix package", 
    "4": "Thay đổi ID", 
    "5": "Thiết lập Webhook URL",
    "6": "Xóa cache", 
    "7": "Import Auto Execute", 
    "8": "Mở tab clone", 
    "9": "Gửi tin nhắn",
    "10": "Sao lưu / Khôi phục dữ liệu", 
    "11": "Cookie Roblox", 
    "12": "Xem log",
    "13": "Thống kê độ ổn định", 
    "14": "Hồ sơ theo game", 
    "15": "Gán executor cho tab",
    "16": "Ban Tracking Stats", 
    "17": "Autoexec Manager",
    "0": "Thoát",
}

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

def announce_choice(key, label):
    print(f"\n {C.PUR}›{C.R} {C.WHT}Đã chọn [{key}] {label}{C.R}")
    time.sleep(0.6)

def invalid_choice(text):
    msg_err(f"Lựa chọn '{text or '(trống)'}' không hợp lệ, vui lòng chọn lại.")
    time.sleep(1.2)

def search_packages_by_keyword():
    """
    Tìm package khớp từ khóa - kết quả hiện ra lập tức
    Flow: nhập từ khóa → hiển thị package khớp → xong
    """
    clear_screen()
    section_title("TÌM PACKAGE NAME")

    packages = sorted(list_installed_packages())
    if not packages:
        msg_warn("Chưa tìm thấy package nào khớp prefix.")
        wait_enter()
        return

    print(f"{C.GRY}Danh sách tất cả package ({len(packages)}):{C.R}\n")
    for i, pkg in enumerate(packages, 1):
        short = pkg[len(PACKAGE_PREFIX):].lstrip(".") if pkg.startswith(PACKAGE_PREFIX) else pkg
        alias = ALIASES.get(pkg, "")
        alias_str = f" ({alias})" if alias else ""
        print(f"  {C.WHT}{i:2}. {short}{alias_str}{C.R}")

    print(f"\n{C.WHT}Nhập từ khóa để lọc (vd: clone, game, 2):{C.R} ", end="", flush=True)
    search_term = input().strip().lower()

    if not search_term:
        msg_cancel("Hủy tìm kiếm.")
        wait_enter()
        return

    matched = [p for p in packages if search_term in p.lower()]

    clear_screen()
    section_title(f"KẾT QUẢ TÌM KIẾM: '{search_term}'")

    if not matched:
        msg_warn(f"Không tìm thấy package nào chứa '{search_term}'")
        wait_enter()
        return

    print(f"\n{C.GRN}✓ Tìm thấy {len(matched)}/{len(packages)} package khớp:{C.R}\n")
    for i, pkg in enumerate(matched, 1):
        short = pkg[len(PACKAGE_PREFIX):].lstrip(".") if pkg.startswith(PACKAGE_PREFIX) else pkg
        alias = ALIASES.get(pkg, "")
        alias_str = f" ({alias})" if alias else ""
        print(f"  {C.WHT}{i}. {short}{alias_str}{C.R}")
        print(f"     {C.GRY}→ {pkg}{C.R}")

    wait_enter()

def check_game_target(value):
    """Kiểm tra ID game hoặc link server VIP. Trả về (ok, thông báo, tên game hoặc None)."""
    value = value.strip()
    if value.isdigit():
        url = "https://games.roblox.com/v1/games/multiget-place-details?placeIds=" + value
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Linux; Android 13)"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
        except Exception as e:
            return None, f"Không kiểm tra được Game ID (mạng lỗi: {e})", None
        if isinstance(data, list):
            if not data:
                return False, f"Game ID {value} không tồn tại hoặc đã bị gỡ.", None
            name = data[0].get("name") or f"Game ID: {value}"
            return True, f"Game hợp lệ: {name}", name
        return None, "Không kiểm tra được Game ID (phản hồi lạ từ Roblox).", None

    if value.lower().startswith(("https://", "http://")) and "roblox" in value.lower():
        try:
            req = urllib.request.Request(value, headers={"User-Agent": "Mozilla/5.0 (Linux; Android 13)"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                code = resp.status
                body = resp.read(300000).decode("utf-8", "replace").lower()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False, "Link server VIP không tồn tại.", None
            return None, f"Không kiểm tra được link VIP (HTTP {e.code}).", None
        except Exception as e:
            return None, f"Không kiểm tra được link VIP (mạng lỗi: {e}).", None
        if any(p in body for p in VIP_EXPIRED_PHRASES):
            return False, "Link server VIP đã hết hạn hoặc không còn dùng được.", None
        if code == 404:
            return False, "Link server VIP không tồn tại.", None
        return True, "Link VIP hợp lệ (chưa xác nhận được server còn mở).", "Server VIP Custom"

    return False, "Định dạng không hợp lệ. Nhập ID game (chỉ số) hoặc link server VIP Roblox.", None

def menu_choose_game_with_package():
    """
    Consolidated menu [2]: Select game, then bind to package(s)
    Flow: game selection -> package selection -> save binding
    """
    global TARGET_LINK, SELECTED_GAME_NAME, PACKAGE_GAMES

    clear_screen()
    section_title("CHỌN GAME & LIÊN KẾT PACKAGE")

    # Step 1: Game selection
    print(f"\n{C.WHT}Set Up{C.R}\n")
    for k, (name, _gid) in GAMES.items():
        print(f"\033[1;37m{k}. {name}\033[0m")
    print(f"{C.LPUR}[12]{C.R} {C.WHT}Custom ID / Private Link{C.R}")

    game_choice = input(f"\n{C.WHT}Chọn game [1-12]:{C.R} ").strip()

    # Parse game selection
    game_name = None
    game_id = None

    if game_choice in GAMES:
        game_name, game_id = GAMES[game_choice]
        msg_done(f"Đã chọn game: {game_name}")
        print(f" {C.GRY}ID: {game_id}{C.R}")
    elif game_choice == "12":
        game_id = input(f"\n{C.WHT}Nhập ID game hoặc Link Server VIP:{C.R} ").strip()
        if game_id:
            ok_g, info_g, name_g = check_game_target(game_id)
            if ok_g is False:
                msg_err(info_g)
                wait_enter()
                return
            if ok_g is None:
                msg_warn(info_g)
            else:
                msg_done(info_g)
            game_name = name_g or (f"Game ID: {game_id}" if game_id.isdigit() else "Server VIP Custom")
        else:
            msg_cancel("Chưa nhập ID/link, hủy.")
            wait_enter()
            return
    else:
        msg_cancel("Lựa chọn không hợp lệ, hủy.")
        wait_enter()
        return

    # Save global selection
    SELECTED_GAME_NAME = game_name
    TARGET_LINK = game_id

    # Step 2: Package binding
    print(f"\n{C.WHT}Nhập Package Name{C.R}\n")

    packages = sorted(list_installed_packages())
    if not packages:
        msg_warn("Chưa tìm thấy package nào. Hãy kiểm tra lại Package Prefix ở mục [3].")
        save_config_file()
        wait_enter()
        return

    print(f"{C.WHT}Danh sách package:{C.R}")
    for i, pkg in enumerate(packages, 1):
        short = pkg[len(PACKAGE_PREFIX):].lstrip(".") if pkg.startswith(PACKAGE_PREFIX) else pkg
        alias = ALIASES.get(pkg, "")
        alias_str = f" ({alias})" if alias else ""
        print(f"  {C.WHT}{i:2}. {short}{alias_str}{C.R}")

    print(f"\n{C.GRY}Nhập số package hoặc 'all' để liên kết với game này:{C.R}")
    pkg_choice = input(f"{C.WHT}Chọn:{C.R} ").strip()

    # Save package binding
    if pkg_choice.lower() == "all":
        for pkg in packages:
            PACKAGE_GAMES[pkg] = {
                "game_name": game_name,
                "game_id": game_id,
            }
        msg_done(f"✓ Đã liên kết '{game_name}' với tất cả {len(packages)} package")
    elif pkg_choice.isdigit() and 1 <= int(pkg_choice) <= len(packages):
        pkg = packages[int(pkg_choice) - 1]
        PACKAGE_GAMES[pkg] = {
            "game_name": game_name,
            "game_id": game_id,
        }
        short = pkg[len(PACKAGE_PREFIX):].lstrip(".") if pkg.startswith(PACKAGE_PREFIX) else pkg
        msg_done(f"✓ Đã liên kết '{game_name}' với {C.WHT}{short}{C.R}")
    else:
        msg_err("Lựa chọn không hợp lệ.")
        wait_enter()
        return

    save_config_file()
    print(f"\n{C.GRN}✓ Cấu hình đã lưu thành công{C.R}")
    wait_enter()

def set_game_for_package():
    """Legacy function - kept for backward compatibility, now calls consolidated flow"""
    menu_choose_game_with_package()

def menu_choose_game():
    global TARGET_LINK, SELECTED_GAME_NAME
    clear_screen()
    section_title("CHỌN GAME")
    for k, (name, _gid) in GAMES.items():
        print(f"\033[1;37m{k}. {name}\033[0m")
    print(f"{C.LPUR}[12]{C.R} {C.WHT}Custom ID / Private Link{C.R}")
    game_choice = input("Chọn game [1-12]: ").strip()
    if game_choice in GAMES:
        SELECTED_GAME_NAME, TARGET_LINK = GAMES[game_choice]
        save_config_file()
        msg_done(f"Đã chọn và lưu game: {SELECTED_GAME_NAME}")
        print(f" {C.GRY}ID: {TARGET_LINK}{C.R}")
    elif game_choice == "12":
        link = input("Nhập ID game hoặc Link Server VIP: ").strip()
        if link:
            ok_g, info_g, name_g = check_game_target(link)
            if ok_g is False:
                msg_err(info_g)
                time.sleep(2)
                return
            if ok_g is None:
                msg_warn(info_g)
            else:
                msg_done(info_g)
            TARGET_LINK = link
            SELECTED_GAME_NAME = name_g or (f"Game ID: {link}" if link.isdigit() else "Server VIP Custom")
            save_config_file()
            msg_done(f"Đã nhận và lưu link/ID: {SELECTED_GAME_NAME}")
        else:
            msg_cancel(f"Chưa nhập ID/link, giữ nguyên game hiện tại: {SELECTED_GAME_NAME}")
    else:
        msg_cancel(f"Lựa chọn không hợp lệ, giữ nguyên game hiện tại: {SELECTED_GAME_NAME}")
    time.sleep(2)

def _pick_tab(packages, prompt):
    c = input(prompt).strip()
    if c.isdigit() and 1 <= int(c) <= len(packages):
        return packages[int(c) - 1]
    if c not in ("", "0"):
        msg_err("Lựa chọn không hợp lệ.")
    return None

def menu_key_injector():
    global KEY_AUTO
    while True:
        clear_screen()
        section_title("CLIENT KEY INJECTOR")
        packages = list_installed_packages()
        idx = _key_index_load()
        print(f" {C.GRY}Giữ bản sao file key/token do chính Client tạo ra, và tự chèn lại khi tab bị reset / xóa data{C.R}")
        print(f" {C.GRY}để khỏi nhập key tay. Tool không tạo, không sửa và không kiểm tra key: chỉ lưu / trả lại đúng file cũ.{C.R}")
        print(f" {C.GRY}Bản sao nằm ở {KEY_VAULT_DIR} (quyền riêng tư), không gửi lên Discord / log.{C.R}")
        print(f" {C.GRY}Tự động lưu & chèn: {'BẬT' if KEY_AUTO else 'TẮT'}{C.R}\n")
        if not packages:
            msg_err(f"Không thấy package nào khớp '{PACKAGE_PREFIX}' (đổi ở mục [3] nếu clone đặt tên khác).")
            wait_enter()
            return
        for i, p in enumerate(packages, 1):
            print(f" {C.LPUR}{i:>2}.{C.R} {C.WHT}{clip(tab_label(p), 30)}{C.R} {C.GRY}theo dõi {len(KEY_FILES.get(p, []))} file · vault {len(idx.get(p, {}))} file{C.R}")
        print(f"{C.LPUR}[1]{C.R} {C.WHT}Chọn file key cần giữ cho 1 tab (tự quét){C.R}")
        print(f"{C.LPUR}[2]{C.R} {C.WHT}Lưu key vào vault ngay (mọi tab đã chọn){C.R}")
        print(f"{C.LPUR}[3]{C.R} {C.WHT}Chèn key từ vault ngay (ghi đè, tab sẽ bị tắt){C.R}")
        print(f"{C.LPUR}[4]{C.R} {C.WHT}Bật / Tắt tự động lưu & chèn{C.R}")
        print(f"{C.LPUR}[5]{C.R} {C.WHT}Xóa vault của 1 tab{C.R}")
        print(f"{C.RED}[0] Quay lại menu Set up{C.R}")
        sub = input("Chọn: ").strip()
        if sub == "0":
            msg_info("Quay lại menu Set up...")
            time.sleep(0.6)
            return
        if not root_mode() and sub in ("1", "2", "3"):
            msg_err("Cần quyền root để đọc / ghi file key trong dữ liệu của app.")
            wait_enter()
            continue
        if sub == "1":
            p = _pick_tab(packages, "Nhập số tab: ")
            if not p:
                continue
            announce_choice("1", f"Quét file key của {tab_label(p)}")
            cands = with_spinner("Đang quét file key/token", key_candidates, p)
            cur = KEY_FILES.get(p, [])
            allc = sorted(set(cands) | set(cur))
            if allc:
                for i, c in enumerate(allc, 1):
                    mark = f"{C.GRN}✓{C.R}" if c in cur else " "
                    print(f" {C.LPUR}{i:>2}.{C.R} {mark} {C.WHT}{clip(c, 52)}{C.R} {C.GRY}{get_file_size(c)}B{C.R}")
            else:
                msg_warn("Không thấy file nào có tên chứa key / token / license (mở Client và nhập key 1 lần trước, hoặc nhập đường dẫn tay).")
            print(f" {C.GRY}Nhập số file cần giữ (cách nhau dấu cách) · p = nhập đường dẫn tay · Enter = hủy{C.R}")
            raw = input("Chọn: ").strip().lower()
            chosen = []
            if raw == "p":
                path = input("Đường dẫn file (bắt đầu bằng /): ").strip()
                if path.startswith("/") and get_file_size(path) > 0:
                    chosen = [path]
                else:
                    msg_err("Không thấy file đó (hoặc file rỗng).")
            elif raw:
                nums = [x for x in re.split(r"[,\s]+", raw) if x]
                if all(x.isdigit() and 1 <= int(x) <= len(allc) for x in nums):
                    chosen = [allc[int(x) - 1] for x in nums]
                else:
                    msg_err("Số không hợp lệ.")
            if not chosen:
                msg_cancel("Không thay đổi.")
                wait_enter()
                continue
            KEY_FILES[p] = sorted(set(cur) | set(chosen))
            save_config_file()
            changed, skipped = key_save(p)
            msg_done(f"{tab_label(p)}: theo dõi {len(KEY_FILES[p])} file, đã lưu vào vault {changed} file (bỏ qua {skipped}).")
            others = [o for o in packages if o != p]
            if others and input("Áp dụng đường dẫn tương tự cho các tab còn lại? (y/n): ").strip().lower() == "y":
                for o in others:
                    tr = [x.replace(p, o) for x in KEY_FILES[p]]
                    keep = [x for x in tr if get_file_size(x) > 0]
                    if keep:
                        KEY_FILES[o] = sorted(set(KEY_FILES.get(o, [])) | set(keep))
                        ch, _sk = key_save(o)
                        msg_ok(f"{tab_label(o)}: theo dõi {len(KEY_FILES[o])} file, lưu {ch} file.")
                    else:
                        msg_info(f"{tab_label(o)}: chưa có file tương ứng (nhập key ở tab đó rồi chạy lại mục này).")
                save_config_file()
            wait_enter()
        elif sub == "2":
            announce_choice("2", "Lưu key vào vault")
            tot = 0
            for p in packages:
                if KEY_FILES.get(p):
                    ch, sk = key_save(p)
                    tot += ch
                    (msg_ok if ch or not sk else msg_warn)(f"{tab_label(p)}: lưu {ch} file mới/đổi, bỏ qua {sk}.")
            if not KEY_FILES:
                msg_warn("Chưa chọn file key nào (dùng mục 1 trước).")
            else:
                msg_done(f"Hoàn tất lưu vault ({tot} file mới/đổi).")
            wait_enter()
        elif sub == "3":
            announce_choice("3", "Chèn key từ vault")
            targets = [p for p in packages if idx.get(p)]
            if not targets:
                msg_warn("Vault đang trống (dùng mục 1 / 2 để lưu key trước).")
            elif input(f"Các tab đang chạy sẽ bị tắt, ghi đè file key của {len(targets)} tab. Tiếp tục? (y/n): ").strip().lower() == "y":
                for p in targets:
                    close_game(p)
                    n = key_ensure(p, force=True)
                    if not n:
                        msg_err(f"{tab_label(p)}: không chèn được (kiểm tra root / thư mục dữ liệu của app).")
                msg_done("Đã chèn key từ vault. Mở lại tab bằng Start hoặc mục [8].")
            else:
                msg_cancel("Đã hủy.")
            wait_enter()
        elif sub == "4":
            KEY_AUTO = not KEY_AUTO
            save_config_file()
            msg_done(f"Đã {'BẬT' if KEY_AUTO else 'TẮT'} tự động lưu & chèn key và lưu cấu hình.")
            wait_enter()
        elif sub == "5":
            p = _pick_tab(packages, "Nhập số tab cần xóa vault: ")
            if not p:
                continue
            announce_choice("5", f"Xóa vault {tab_label(p)}")
            if input(f"Xóa bản sao key của {tab_label(p)}? (y/n): ").strip().lower() == "y":
                shutil.rmtree(_key_dir(p), ignore_errors=True)
                i2 = _key_index_load()
                i2.pop(p, None)
                _key_index_save(i2)
                KEY_FILES.pop(p, None)
                save_config_file()
                msg_done("Đã xóa vault và bỏ theo dõi key của tab này.")
            else:
                msg_cancel("Đã hủy.")
            wait_enter()
        else:
            invalid_choice(sub)

def screen_diagnose():
    if not root_mode():
        msg_err("Cần quyền root để chụp màn hình / đọc cửa sổ.")
        return
    packages = [p for p in list_installed_packages() if is_app_running(p)]
    if not packages:
        msg_warn("Không có tab nào đang chạy. Hãy Start hoặc mở tab clone trước.")
        return
    msg_info("Đang đọc cửa sổ và chụp màn hình...")
    snap = window_snapshot(packages)
    frame = capture_frame()
    if frame is None:
        msg_err("Không chụp được màn hình bằng screencap (máy / ROM không hỗ trợ?).")
    else:
        msg_ok(f"Chụp được khung {frame[0]}x{frame[1]}.")
    for p in packages:
        if p in snap["anr"]:
            msg_warn(f"{tab_label(p)}: đang hiện hộp thoại Not Responding.")
        rect = snap["rects"].get(p)
        if not rect and snap["focus"] != p:
            msg_info(f"{tab_label(p)}: không xác định được cửa sổ (tab không có focus) nên bỏ qua.")
            continue
        if frame is None:
            continue
        res = analyze_frame(frame, rect)
        if not res:
            msg_info(f"{tab_label(p)}: vùng cửa sổ quá nhỏ.")
            continue
        verdict = {"white": "TRẮNG kẹt", "black": "ĐEN kẹt", "ok": "bình thường"}[res["kind"]]
        print(f" {dot(res['kind'] == 'ok')} {C.WHT}{tab_label(p)}{C.R}: {verdict} {C.GRY}(độ sáng {res['median']}, đồng màu {res['uniform']}){C.R}")

def menu_screen_guard():
    global WB_DETECT, OVERLAY_DETECT
    while True:
        clear_screen()
        section_title("PHÁT HIỆN MÀN HÌNH TRẮNG/ĐEN & GUI ĐỨNG")
        print(f" {C.GRY}Quét màn hình mỗi {SCREEN_CHECK_SEC}s khi đang Start (tự động rejoin ở chế độ 1):{C.R}")
        print(f" {C.GRY}• Trắng/đen kẹt {WB_CONFIRM_COUNT} lần liên tiếp -> kill-process rồi vào lại ngay, không chờ timeout.{C.R}")
        print(f" {C.GRY}• Not Responding (ANR) hoặc khung hình đứng im {OVERLAY_FREEZE_SEC}s + không có log -> kill-process rồi chạy lại.{C.R}")
        print(f" {C.GRY}Hiện tại: {screen_guard_label()}{C.R}\n")
        print(f"{C.LPUR}[1]{C.R} {C.WHT}Bật / Tắt phát hiện màn hình trắng/đen [{'Bật' if WB_DETECT else 'Tắt'}]{C.R}")
        print(f"{C.LPUR}[2]{C.R} {C.WHT}Bật / Tắt phát hiện Not Responding / GUI đứng [{'Bật' if OVERLAY_DETECT else 'Tắt'}]{C.R}")
        print(f"{C.LPUR}[3]{C.R} {C.WHT}Thử quét ngay (xem tool đọc màn hình từng tab){C.R}")
        print(f"{C.RED}[0] Quay lại menu Set up{C.R}")
        sub = input("Chọn: ").strip()
        if sub == "0":
            msg_info("Quay lại menu Set up...")
            time.sleep(0.6)
            return
        if sub == "1":
            WB_DETECT = not WB_DETECT
            save_config_file()
            msg_done(f"Đã {'BẬT' if WB_DETECT else 'TẮT'} phát hiện màn hình trắng/đen và lưu cấu hình.")
            wait_enter()
        elif sub == "2":
            OVERLAY_DETECT = not OVERLAY_DETECT
            save_config_file()
            msg_done(f"Đã {'BẬT' if OVERLAY_DETECT else 'TẮT'} phát hiện Not Responding / GUI đứng và lưu cấu hình.")
            wait_enter()
        elif sub == "3":
            announce_choice("3", "Thử quét màn hình")
            screen_diagnose()
            wait_enter()
        else:
            invalid_choice(sub)

def menu_update_tool():
    """Set up > Update Tool: kiểm tra và cập nhật tool thủ công từ server"""
    import shutil
    import urllib.request
    clear_screen()
    section_title("UPDATE TOOL")
    print(f" {C.GRY}Phiên bản đang dùng: {VERSION}{C.R}")
    print(f" {C.YEL}Đang kiểm tra phiên bản...{C.R}")
    latest = fetch_latest_version()
    if not latest:
        msg_warn("Không kiểm tra được phiên bản (mất kết nối).")
        wait_enter()
        return
    UPDATE_INFO["latest"] = latest
    if not update_available():
        msg_done(f"Bạn đang dùng bản mới nhất ({VERSION}).")
        wait_enter()
        return
    print(f"\n{C.GRN}Phiên bản mới: {latest} (đang dùng {VERSION}){C.R}\n")
    print(f"{C.YEL}[1] Cập nhật ngay{C.R}")
    print(f"{C.RED}[0] Bỏ qua{C.R}\n")
    if ask("Chọn:").strip() != "1":
        return
    download_url = "https://paintool-bot.onrender.com/api/download/latest"
    current_file = os.path.abspath(__file__)
    backup_file = current_file + ".backup"
    print(f"\n{C.YEL}[*] Đang tải bản cập nhật...{C.R}")
    try:
        if os.path.exists(current_file):
            shutil.copy(current_file, backup_file)
        with urllib.request.urlopen(download_url, timeout=30) as response:
            new_content = response.read()
        with open(current_file, "wb") as f:
            f.write(new_content)
        msg_done("Cập nhật thành công! Đang khởi động lại...")
        print(f"{C.GRY}(File backup: {backup_file}){C.R}")
        time.sleep(2)
        os.execl(sys.executable, sys.executable, current_file)
    except Exception as e:
        msg_err(f"Lỗi tải bản cập nhật: {str(e)}")
        print(f"{C.GRY}Khôi phục từ backup...{C.R}")
        if os.path.exists(backup_file):
            shutil.copy(backup_file, current_file)
        wait_enter()

def menu_quiet_hours():
    while True:
        clear_screen()
        section_title("GIỜ IM LẶNG CẢNH BÁO")
        st = f"{C.GRN}Bật{C.R}" if QUIET_HOURS.get("enabled") else f"{C.GRY}Tắt{C.R}"
        print(f" Trạng thái: {st}")
        print(f" Khung giờ: {QUIET_HOURS.get('start')} → {QUIET_HOURS.get('end')}\n")
        print(f"{C.GRY}Trong khung giờ, cảnh báo vẫn gửi lên webhook nhưng không ping @everyone/ID.{C.R}\n")
        print(f"{C.LPUR}[1]{C.R} {C.WHT}Bật{C.R}")
        print(f"{C.LPUR}[2]{C.R} {C.WHT}Tắt{C.R}")
        print(f"{C.LPUR}[3]{C.R} {C.WHT}Đổi khung giờ{C.R}")
        print(f"{C.RED}[0] Quay lại{C.R}\n")
        sub = ask("Chọn:").strip()
        if sub == "1":
            QUIET_HOURS["enabled"] = True
            save_config_file()
            msg_done("Đã bật giờ im lặng.")
            time.sleep(1)
        elif sub == "2":
            QUIET_HOURS["enabled"] = False
            save_config_file()
            msg_done("Đã tắt giờ im lặng.")
            time.sleep(1)
        elif sub == "3":
            a = ask("Giờ bắt đầu (HH:MM, ví dụ 23:00):").strip()
            b = ask("Giờ kết thúc (HH:MM, ví dụ 07:00):").strip()
            valid = all(re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", t) for t in (a, b))
            if not valid:
                msg_err("Giờ không hợp lệ. Dùng dạng HH:MM, ví dụ 23:00.")
            else:
                QUIET_HOURS["start"] = a
                QUIET_HOURS["end"] = b
                save_config_file()
                msg_done(f"Đã đặt khung giờ {a} → {b}.")
            time.sleep(1)
        elif sub == "0":
            return
        else:
            invalid_choice(sub)

def menu_stop_timer():
    global RUN_LIMIT_HOURS
    while True:
        clear_screen()
        section_title("GIỚI HẠN THỜI GIAN CHẠY")
        st = f"{C.GRN}Bật{C.R}" if STOP_TIMER.get("enabled") else f"{C.GRY}Tắt{C.R}"
        close = f"{C.GRN}Bật{C.R}" if STOP_TIMER.get("close_apps") else f"{C.GRY}Tắt{C.R}"
        print(f" Trạng thái: {st}  ·  Thời gian: {STOP_TIMER.get('hours')} giờ")
        print(f" Tắt clone khi hết giờ: {close}\n")
        print(f"{C.GRY}Tính từ lúc bấm Start. Khi hết giờ tool dừng rejoin và gửi tin lên webhook.{C.R}\n")
        print(f"{C.LPUR}[1]{C.R} {C.WHT}Bật và đặt số giờ{C.R}")
        print(f"{C.LPUR}[2]{C.R} {C.WHT}Tắt{C.R}")
        print(f"{C.LPUR}[3]{C.R} {C.WHT}Bật/tắt tắt clone khi hết giờ{C.R}")
        print(f"{C.RED}[0] Quay lại{C.R}\n")
        sub = ask("Chọn:").strip()
        if sub == "1":
            raw = ask("Số giờ chạy (ví dụ 6 hoặc 2.5):").strip().replace(",", ".")
            try:
                v = float(raw)
                if v <= 0:
                    raise ValueError
                STOP_TIMER["enabled"] = True
                STOP_TIMER["hours"] = v
                save_config_file()
                msg_done(f"Đã bật giới hạn {v:g} giờ.")
            except ValueError:
                msg_err("Số giờ không hợp lệ.")
            time.sleep(1)
        elif sub == "2":
            STOP_TIMER["enabled"] = False
            save_config_file()
            msg_done("Đã tắt giới hạn thời gian chạy.")
            time.sleep(1)
        elif sub == "3":
            STOP_TIMER["close_apps"] = not STOP_TIMER.get("close_apps", False)
            save_config_file()
            msg_done("Tắt clone khi hết giờ: " + ("BẬT" if STOP_TIMER["close_apps"] else "TẮT"))
            time.sleep(1)
        elif sub == "0":
            return
        else:
            invalid_choice(sub)

def toggle_monitor_only():
    global MONITOR_ONLY
    MONITOR_ONLY = not MONITOR_ONLY
    save_config_file()
    msg_done("Chế độ chỉ theo dõi: " + ("BẬT (không rejoin, vẫn gửi cảnh báo)" if MONITOR_ONLY else "TẮT"))
    time.sleep(1.2)

def toggle_screen_archive():
    SCREEN_ARCHIVE["enabled"] = not SCREEN_ARCHIVE.get("enabled", False)
    save_config_file()
    msg_done("Lưu ảnh khi có lỗi nghiêm trọng: " + ("BẬT" if SCREEN_ARCHIVE["enabled"] else "TẮT"))
    if SCREEN_ARCHIVE["enabled"]:
        print(f" {C.GRY}Ảnh lưu tại {SHOT_DIR}, giữ tối đa {SHOT_KEEP} ảnh gần nhất.{C.R}")
    time.sleep(1.5)

def menu_setup():
    while True:
        clear_screen()
        section_title("SET UP")
        print(f"{C.LPUR}[1]{C.R} {C.WHT}Set up auto rejoin{C.R}")
        print(f"{C.LPUR}[2]{C.R} {C.WHT}Chọn game{C.R}")
        print(f"{C.LPUR}[3]{C.R} {C.WHT}Auto Clear Data / Khôi phục tab kẹt [{'Bật' if AUTO_CLEAR_DATA else 'Tắt'}]{C.R}")
        print(f"{C.LPUR}[4]{C.R} {C.WHT}Auto Backup data tab [{'Bật' if AUTO_BACKUP else 'Tắt'}]{C.R}")
        print(f"{C.LPUR}[5]{C.R} {C.WHT}Cảnh báo RAM thấp [{'Bật' if LOW_RAM_ALERT else 'Tắt'}]{C.R}")
        print(f"{C.LPUR}[6]{C.R} {C.WHT}Profile cấu hình [{len(PROFILES)} profile]{C.R}")
        print(f"{C.LPUR}[7]{C.R} {C.WHT}Tìm package name (khớp từ khóa){C.R}")
        print(f"{C.LPUR}[8]{C.R} {C.WHT}Hẹn giờ tự chạy / tự dừng [{'Bật' if (SCHEDULE.get('start') or SCHEDULE.get('stop')) else 'Tắt'}]{C.R}")
        print(f"{C.LPUR}[9]{C.R} {C.WHT}Graphics Optimizer (đồ họa thấp + giới hạn FPS) [{gfx_settings_label()}]{C.R}")
        print(f"{C.LPUR}[10]{C.R} {C.WHT}Biệt danh tab (Alias) [{len(ALIASES)} tab]{C.R}")
        print(f"{C.LPUR}[11]{C.R} {C.WHT}Kiểm tra mạng trước khi rejoin [{'Bật' if NET_CHECK else 'Tắt'}]{C.R}")
        print(f"{C.LPUR}[12]{C.R} {C.WHT}Lịch tự động restart [{auto_restart_label()}]{C.R}")
        print(f"{C.LPUR}[13]{C.R} {C.WHT}Client Key Injector [{key_label()}]{C.R}")
        print(f"{C.LPUR}[14]{C.R} {C.WHT}Phát hiện màn hình trắng/đen & GUI đứng [{screen_guard_label()}]{C.R}")
        # BLACK SCREEN REMOVED - Not compatible with UgPhone
        # print(f"{C.LPUR}[15]{C.R} {C.WHT}Chế độ màn hình đen (Black Screen) [{black_screen_label()}]{C.R}")
        print(f"{C.LPUR}[15]{C.R} {C.WHT}Auto Server Hop (đổi server khi lag) [{hop_label()}]{C.R}")
        print(f"{C.LPUR}[16]{C.R} {C.WHT}Groq AI Setup{C.R}")
        print(f"{C.LPUR}[17]{C.R} {C.WHT}Update Tool{C.R}")
        print(f"{C.LPUR}[18]{C.R} {C.WHT}Giờ im lặng cảnh báo [{'Bật' if QUIET_HOURS.get('enabled') else 'Tắt'}]{C.R}")
        print(f"{C.LPUR}[19]{C.R} {C.WHT}Giới hạn thời gian chạy [{'Bật' if STOP_TIMER.get('enabled') else 'Tắt'}]{C.R}")
        print(f"{C.LPUR}[20]{C.R} {C.WHT}Chế độ chỉ theo dõi [{'Bật' if MONITOR_ONLY else 'Tắt'}]{C.R}")
        print(f"{C.LPUR}[21]{C.R} {C.WHT}Lưu ảnh khi có lỗi nghiêm trọng [{'Bật' if SCREEN_ARCHIVE.get('enabled') else 'Tắt'}]{C.R}")
        print(f"{C.RED}[0] Quay lại menu chính{C.R}")
        sub = input("Chọn: ").strip()
        if sub == "1":
            announce_choice("1", "Set up auto rejoin")
            setup_auto_rejoin()
        elif sub == "2":
            announce_choice("2", "Chọn game & Liên kết package")
            menu_choose_game_with_package()
        elif sub == "3":
            announce_choice("3", "Auto Clear Data")
            setup_auto_clear()
        elif sub == "4":
            announce_choice("4", "Auto Backup")
            setup_auto_backup()
        elif sub == "5":
            announce_choice("5", "Cảnh báo RAM thấp")
            setup_low_ram()
        elif sub == "6":
            announce_choice("6", "Profile cấu hình")
            menu_profile()
        elif sub == "7":
            announce_choice("7", "Tìm package name")
            search_packages_by_keyword()
        elif sub == "8":
            announce_choice("8", "Hẹn giờ tự chạy / tự dừng")
            menu_schedule()
        elif sub == "9":
            announce_choice("9", "Graphics Optimizer")
            menu_low_graphics()
        elif sub == "10":
            announce_choice("10", "Biệt danh tab")
            menu_alias()
        elif sub == "11":
            announce_choice("11", "Kiểm tra mạng trước khi rejoin")
            setup_net_check()
        elif sub == "12":
            announce_choice("12", "Lịch tự động restart")
            menu_auto_restart()
        elif sub == "13":
            announce_choice("13", "Client Key Injector")
            menu_key_injector()
        elif sub == "14":
            announce_choice("14", "Phát hiện màn hình trắng/đen & GUI đứng")
            menu_screen_guard()
        # BLACK SCREEN REMOVED - Not compatible with UgPhone
        # elif sub == "15":
        #     announce_choice("15", "Chế độ màn hình đen")
        #     menu_black_screen()
        elif sub == "15":
            announce_choice("15", "Auto Server Hop")
            menu_server_hop()
        elif sub == "16":
            announce_choice("16", "Groq AI Setup")
            menu_groq_setup()
        elif sub == "17":
            announce_choice("17", "Update Tool")
            menu_update_tool()
        elif sub == "18":
            announce_choice("18", "Giờ im lặng cảnh báo")
            menu_quiet_hours()
        elif sub == "19":
            announce_choice("19", "Giới hạn thời gian chạy")
            menu_stop_timer()
        elif sub == "20":
            announce_choice("20", "Chế độ chỉ theo dõi")
            toggle_monitor_only()
        elif sub == "21":
            announce_choice("21", "Lưu ảnh khi có lỗi nghiêm trọng")
            toggle_screen_archive()
        elif sub == "0":
            msg_info("Quay lại menu chính...")
            time.sleep(0.6)
            break
        else:
            invalid_choice(sub)

def menu_package_prefix():
    """Menu 3: Nhập Package Prefix + Chọn Chế Độ Chạy Packages"""
    global PACKAGE_PREFIX, SELECTED_PACKAGES, SELECT_ALL_PACKAGES, PACKAGE_GAMES
    
    # Step 1: Input/Update Package Prefix
    clear_screen()
    section_title("PACKAGE PREFIX - NHẬP VÀ CHỌN CHẾ ĐỘ")
    
    print(f"{C.GRY}Prefix hiện tại:{C.R} {C.WHT}{PACKAGE_PREFIX}{C.R}\n")
    print(f"{C.YEL}Ví dụ: com.roblox → tìm com.roblox.clone1, clone2...{C.R}\n")
    
    pref = input("Nhập Package Prefix (Để trống để giữ mặc định): ").strip()
    
    if pref:
        PACKAGE_PREFIX = pref
        save_config_file()
        msg_done(f"Đã cập nhật Package Prefix: {PACKAGE_PREFIX}")
        time.sleep(1)
    else:
        print(f"{C.GRY}[*] Giữ nguyên: {PACKAGE_PREFIX}{C.R}")
        time.sleep(1)
    
    # Step 2: List packages & show mode selector
    packages_list = list(PACKAGE_GAMES.keys())
    
    if not packages_list:
        msg_err("Không tìm thấy package nào khớp prefix này.")
        wait_enter()
        return
    
    clear_screen()
    section_title("CHỌN PACKAGES - NHẬP PREFIX THÀNH CÔNG")
    
    print(f"{C.GRN}✓ Tìm thấy {len(packages_list)} packages:{C.R}\n")
    
    for i, pkg in enumerate(packages_list, 1):
        print(f" {C.LPUR}[{i:2}]{C.R} {pkg}")
    
    print(f"\n{C.YEL}Bây giờ chọn chế độ chạy packages:{C.R}\n")
    
    print(f"{C.LPUR}[1]{C.R} {C.WHT}Custom Count Mode{C.R}")
    print(f"    → Nhập số N để chạy N packages đầu tiên")
    print(f"    → Ví dụ: nhập 5 → chạy packages 1-5\n")
    
    print(f"{C.LPUR}[2]{C.R} {C.WHT}Selective Mode{C.R}")
    print(f"    → Chọn riêng packages muốn chạy")
    print(f"    → Ví dụ: chọn 1, 3, 5 → chỉ chạy packages này\n")
    
    print(f"{C.RED}[0] Quay lại menu chính{C.R}\n")
    
    mode_choice = ask("Chọn chế độ:").strip()
    
    if mode_choice == "0":
        return
    elif mode_choice == "1":
        menu_custom_count_mode(packages_list)
    elif mode_choice == "2":
        menu_selective_mode(packages_list)
    else:
        msg_err("Lựa chọn không hợp lệ.")
        time.sleep(1)

def menu_change_id():
    clear_screen()
    section_title("CHANGE ANDROID ID")
    new_id = input("Nhập ID mới (Để trống để tạo ngẫu nhiên): ").strip()
    if not new_id:
        new_id = "".join(random.choices(string.hexdigits.lower(), k=16))
        msg_info(f"Đã tạo ID ngẫu nhiên: {new_id}")
    msg_info("Đang áp dụng ID mới...")
    sh(f"settings put secure android_id {shlex.quote(new_id)}")
    current = sh("settings get secure android_id", timeout=5).strip()
    if current == new_id:
        msg_done(f"Đã đổi Android ID thành công: {new_id}")
    else:
        msg_warn(f"Đã gửi lệnh đổi ID: {new_id}")
    wait_enter()

def send_test_webhook(url, content, embed_title, embed_desc):
    """Gửi tin thử tới webhook. Trả về (ok, thông báo)."""
    payload = {
        "content": content,
        "allowed_mentions": {"parse": ["everyone", "users"]},
        "embeds": [{"title": embed_title, "description": embed_desc, "color": 0x57F287}],
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "PainTool/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            code = resp.status
        if code in (200, 204):
            return True, f"HTTP {code}"
        return False, f"HTTP {code}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)

def menu_webhook():
    global WEBHOOK_URL
    clear_screen()
    section_title("SET WEBHOOK URL")
    if WEBHOOK_URL:
        print(f"Webhook hiện tại: {WEBHOOK_URL[:35]}...")
    else:
        print(f" {C.GRY}Chưa cài Webhook. Tool sẽ không gửi được báo cáo / cảnh báo / Send Text cho tới khi bạn nhập ở đây.{C.R}")
    new_webhook = input("Nhập URL Discord Webhook (Để trống để xóa Webhook): ").strip()
    if new_webhook and not new_webhook.lower().startswith(("https://", "http://")):
        msg_err("URL webhook phải bắt đầu bằng https://  — giữ nguyên cấu hình cũ.")
        wait_enter()
        return
    WEBHOOK_URL = new_webhook
    save_config_file()
    if WEBHOOK_URL:
        global DISCORD_UID
        uid = input("Nhập Discord ID để ping (để trống để ping @everyone): ").strip()
        if uid and not (uid.isdigit() and 17 <= len(uid) <= 20):
            msg_err("Discord ID không hợp lệ (cần 17–20 chữ số). Sẽ ping @everyone.")
            uid = ""
        DISCORD_UID = uid
        save_config_file()
        mention = "@everyone" + (f" <@{DISCORD_UID}>" if DISCORD_UID else "")
        print(f" {C.YEL}[*] Đang gửi tin thử tới Discord...{C.R}")
        ok_test, info = send_test_webhook(
            WEBHOOK_URL, mention, "Webhook đã kết nối",
            "PAIN TOOL REJOIN VIP: tin thử từ menu Set Webhook URL.")
        if ok_test:
            msg_done(f"Gửi tin thử thành công ({info}).")
        else:
            msg_err(f"Gửi tin thử thất bại ({info}). Kiểm tra lại URL webhook.")
        msg_done("Đã cập nhật Webhook thành công!")
        print(f" {C.GRY}Webhook: {WEBHOOK_URL[:35]}...{C.R}")
        print(f" {C.GRY}Ping: {mention}{C.R}")
        print(f" {C.GRY}Báo cáo ảnh chụp màn hình mỗi 5 phút sẽ chạy khi bạn bấm Start.{C.R}")
    else:
        msg_done("Đã xóa Webhook thành công.")
        print(f" {C.GRY}Không có webhook thì tool không gửi báo cáo và không chụp ảnh màn hình.{C.R}")
    wait_enter()

def menu_clear_cache():
    clear_screen()
    section_title("XÓA CACHE")
    packages = get_all_packages()
    msg_info(f"Đang xóa cache của {len(packages)} tab và dọn RAM...")
    for pkg in packages:
        sh(f"rm -rf /data/data/{pkg}/cache/* /data/data/{pkg}/code_cache/*")
    sh("sync && echo 3 > /proc/sys/vm/drop_caches")
    msg_done(f"Đã xóa cache {len(packages)} tab và dọn RAM (không xóa dữ liệu đăng nhập)!")
    wait_enter()

def import_autoexec_script():
    clear_screen()
    section_title("IMPORT AUTO EXECUTE")
    script_data = input("Nhập script hack (Để trống để thoát): ").strip()
    if not script_data:
        msg_cancel("Chưa nhập script, đã hủy import.")
        time.sleep(1.2)
        return
    msg_info("Đang ghi script vào các thư mục Autoexec...")
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
    written = sum(1 for t in target_dirs if os.path.exists(f"{t}/script.lua"))
    try:
        os.remove(temp_path)
    except Exception:
        pass
    if written:
        msg_done(f"Đã lưu script Autoexec thành công vào {written}/{len(target_dirs)} thư mục!")
    else:
        msg_err("Không ghi được script vào thư mục nào (kiểm tra quyền truy cập bộ nhớ của Termux).")
    wait_enter()

def menu_open_clones():
    clear_screen()
    section_title("MỞ TAB CLONE")
    found_pkgs = get_all_packages()
    stats = {"ok": 0, "fail": 0}
    print(f"\033[1;32m[*] Đang mở hàng loạt tab (chỉ mở tab, KHÔNG vào Map)...\033[0m")

    def open_tab_only(pkg, label):
        if open_game(pkg, enter_map=False):
            stats["ok"] += 1
            print(f"\033[1;32m[+] Đã mở package {label}: {tab_label(pkg)}\033[0m")
        else:
            stats["fail"] += 1
            print(f"\033[1;31m[!] Không mở được package {label}: {tab_label(pkg)}\033[0m")

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
    msg_done(f"Hoàn tất mở tab clone: {stats['ok']}/{len(found_pkgs)} tab đã gửi lệnh mở thành công.")
    if stats["fail"]:
        msg_warn(f"{stats['fail']} tab không mở được (xem thông báo phía trên).")
    wait_enter()

def menu_groq_setup():
    clear_screen()
    section_title("COHERE AI STATUS (Environment Variable)")

    if not _HAS_GROQ:
        msg_warn("Cohere SDK chưa cài đặt. Cài bằng: pip install cohere")
        print(f"\n{C.GRY}$ pip install cohere{C.R}\n")
        wait_enter()
        return

    print(f"""
{C.LPUR}┌─ COHERE AI SETUP ──────────────────────┐{C.R}
{C.LPUR}│{C.R} • 10,000 API calls/tháng miễn phí
{C.LPUR}│{C.R} • Error analysis chuyên nghiệp
{C.LPUR}│{C.R} • Model: command-r-v1
{C.LPUR}│{C.R} • Đăng ký: dashboard.cohere.com
{C.LPUR}└────────────────────────────────────────┘{C.R}
    """)

    status = "✓ ENABLED" if GROQ_ENABLED else "✗ DISABLED"
    status_color = C.GRN if GROQ_ENABLED else C.RED
    key_status = f"{'*' * 10}{GROQ_API_KEY[-10:]}" if GROQ_API_KEY and len(GROQ_API_KEY) > 10 else "Not set"
    
    print(f"Current Status: {status_color}{status}{C.R}")
    print(f"API Key (from env): {C.WHT}{key_status}{C.R}")
    print(f"Requests Today: {GROQ_REQUEST_COUNT}/{GROQ_QUOTA_LIMIT}")
    
    wait_enter()

def apply_game_profile(game_name):
    """
    Load game profile settings và áp dụng vào global vars.
    Nếu game_name không có profile, không làm gì.
    """
    global DELAY_REJOIN_MINUTES, FREEZE_TIMEOUT_MIN, GFX_FPS, SERVER_HOP
    
    if not game_name or game_name not in GAME_PROFILES:
        return
    
    profile = GAME_PROFILES[game_name]
    try:
        # Load từ profile, giữ nguyên nếu key không tồn tại
        delay = profile.get("delay_rejoin_min")
        if isinstance(delay, int) and delay > 0:
            DELAY_REJOIN_MINUTES = delay
        
        freeze_sec = profile.get("freeze_timeout_sec")
        if isinstance(freeze_sec, int) and freeze_sec > 0:
            FREEZE_TIMEOUT_MIN = freeze_sec // 60
        
        fps = profile.get("target_fps")
        if isinstance(fps, int) and (fps == 0 or fps in (15, 20, 30)):
            GFX_FPS = fps
        
        server_hop = profile.get("server_hop_enabled")
        if isinstance(server_hop, bool):
            SERVER_HOP = server_hop
        
        log_event("PROFILE_APPLY", detail=f"Loaded profile for '{game_name}': delay={DELAY_REJOIN_MINUTES}m, freeze={FREEZE_TIMEOUT_MIN}m, fps={GFX_FPS}, hop={SERVER_HOP}")
    except Exception as e:
        log_event("PROFILE_ERR", detail=f"Error loading profile '{game_name}': {e}")

def get_game_for_package(pkg):
    """Lấy game được gán cho package, hoặc fallback đến SELECTED_GAME_NAME."""
    if pkg in PACKAGE_GAMES:
        game_name = PACKAGE_GAMES[pkg].get("game_name")
        if game_name:
            return game_name
    return SELECTED_GAME_NAME

def apply_profiles_on_startup():
    """
    Xác định game nào đang active và load profile tương ứng.
    - Per-package mode: mỗi package có game riêng (từ PACKAGE_GAMES)
    - Global mode: dùng SELECTED_GAME_NAME cho toàn bộ
    
    Lúc startup, áp dụng profile của game đầu tiên để set global defaults.
    Khi run Start, apply per-package profiles sẽ xảy ra trong start_tool loop.
    """
    packages = get_all_packages()
    
    # Kiểm tra nếu dùng per-package game assignment
    has_per_package = any(PACKAGE_GAMES.get(pkg) for pkg in packages)
    
    applied_game = None
    
    if has_per_package:
        # Per-package mode: tìm game profile đầu tiên để apply global defaults
        for pkg in packages:
            game_name = get_game_for_package(pkg)
            if game_name and game_name in GAME_PROFILES:
                apply_game_profile(game_name)
                applied_game = game_name
                log_event("STARTUP_PROFILE", pkg, detail=f"Per-package mode: loaded profile for '{game_name}'")
                break
    else:
        # Global mode: dùng SELECTED_GAME_NAME cho toàn bộ
        if SELECTED_GAME_NAME and SELECTED_GAME_NAME in GAME_PROFILES:
            apply_game_profile(SELECTED_GAME_NAME)
            applied_game = SELECTED_GAME_NAME
            log_event("STARTUP_PROFILE", detail=f"Global mode: loaded profile for '{SELECTED_GAME_NAME}'")
    
    if applied_game:
        print(f" {C.GRN}✓{C.R} Profile '{applied_game}' đã tải. (Để xem/chỉnh sửa: Menu 2 > Hồ sơ theo game)")

def verify_and_start():
    load_saved_config()
    apply_profiles_on_startup()  # <-- Auto-load game profiles sau khi load config
    restore_screen_if_needed()
    authenticate()   # <-- Kiểm tra key chạy TRƯỚC, không qua được thì authenticate() không return

    # Auto-init Cohere AI from environment variable
    if GROQ_API_KEY:
        init_groq()

    time.sleep(0.5)  # Small delay to stabilize terminal state after auth
    
    while True:
        show_banner()
        choice = ask_main("Chọn chức năng [0-17]:").strip()
        if choice not in MENU_NAMES:
            invalid_choice(choice)
            continue
        if choice == "0":
            exit_tool()
        announce_choice(choice, MENU_NAMES[choice])
        if choice == "1":
            start_tool()
        elif choice == "2":
            menu_setup()
        elif choice == "3":
            menu_package_prefix()
        elif choice == "4":
            menu_change_id()
        elif choice == "5":
            menu_webhook()
        elif choice == "6":
            menu_clear_cache()
        elif choice == "7":
            import_autoexec_script()
        elif choice == "8":
            menu_open_clones()
        elif choice == "9":
            handle_send_text()
        elif choice == "10":
            backup_menu()
        elif choice == "11":
            menu_cookie_roblox()
        elif choice == "12":
            menu_view_log()
        elif choice == "13":
            menu_stability_stats()
        elif choice == "14":
            menu_game_profiles()
        elif choice == "15":
            menu_executor_binding()
        elif choice == "16":
            display_ban_stats()
            wait_enter()
        elif choice == "17":
            menu_autoexec_manager()


if __name__ == "__main__":
    verify_and_start()
