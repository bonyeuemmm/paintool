import http.server
import socketserver
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
from datetime import datetime, timezone, timedelta

VERSION = "v1.6.5 Beta"
API_URL = "https://paintool-bot.onrender.com/api/keys/verify"   # endpoint xác thực key (web service Render)

# --- SECRET_KEY: tách riêng khỏi file chính, không hardcode ở đây ---
# Thứ tự ưu tiên: biến môi trường PAINTOOL_SECRET_KEY > file ~/.pain_secret.key > tạo file mới.
# Lợi ích: nếu file tool.py này (file chính) bị dán/chia sẻ ở đâu đó, secret KHÔNG đi kèm theo,
# vì nó nằm trong file riêng trên máy người dùng, không nằm trong mã nguồn được chia sẻ.
# Lưu ý thật: đây chỉ ngăn secret bị lộ khi chia sẻ FILE NÀY; nếu máy/thiết bị của chính bạn bị
# người khác truy cập được, họ vẫn đọc được file secret đó như đọc bất kỳ file nào khác.
_SECRET_KEY_FILE = os.path.join(os.path.expanduser("~"), ".pain_secret.key")
_DEFAULT_SECRET_KEY = "9gt8AU2jITFNRJdLMFoejFdXyXE4Rk-IufaF3AUi344"   # dùng để tạo file lần đầu nếu chưa có


def _load_secret_key():
    env_val = os.environ.get("PAINTOOL_SECRET_KEY", "").strip()
    if env_val:
        return env_val
    try:
        if os.path.isfile(_SECRET_KEY_FILE):
            with open(_SECRET_KEY_FILE, "r", encoding="utf-8") as f:
                val = f.read().strip()
            if val:
                return val
    except Exception:
        pass
    # Chưa có file -> tạo mới với giá trị mặc định (giữ tương thích với key đã cấp trước đó)
    try:
        with open(_SECRET_KEY_FILE, "w", encoding="utf-8") as f:
            f.write(_DEFAULT_SECRET_KEY)
        try:
            os.chmod(_SECRET_KEY_FILE, 0o600)   # chỉ chủ file đọc/ghi được
        except Exception:
            pass
    except Exception:
        pass
    return _DEFAULT_SECRET_KEY


SECRET_KEY = _load_secret_key()
try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False   # Termux chưa cài 'pip install requests' -> tự rơi về curl bên dưới
LAST_LICENSE_EXPIRES = ""   # hạn dùng key, lấy từ phản hồi server (hiển thị cho người dùng)
LICENSE_FILE = os.path.join(os.path.expanduser("~"), ".pain_license")
CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".pain_config.json")
LOG_FILE = os.path.join(os.path.expanduser("~"), ".pain_log.txt")   # nhật ký kick / mã lỗi / rejoin để tra nguyên nhân
LOG_MAX_BYTES = 1_000_000                                            # quá dung lượng này thì cắt bớt phần cũ

PACKAGE_PREFIX = "com.roblox"
TARGET_LINK = ""
SELECTED_GAME_NAME = "Chưa chọn"
WEBHOOK_URL = ""    # chỉ do người dùng tự nhập ở Mục [5]; không còn webhook mặc định gắn sẵn trong code
DISCORD_UID = ""
SCREENSHOT_PATH = "/sdcard/pain_screenshot.png"

DISCORD_LINK = "https://discord.gg/z7RUNArBuJ"

AUTO_REJOIN_MODE = 1          # 1 = Auto rejoin vang/crash, 2 = Delay rejoin (hết chu kỳ tắt tab rồi vào lại map)
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
RETRY_COUNTDOWN_SECONDS = 5  # tab không vào lại được game: đếm ngược bấy nhiêu giây rồi tắt Đa nhiệm và vào lại
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
    "stopped":  {"color": 0x95A5A6, "icon": "⚪", "label": "TOOL DỪNG"},         # xám: người dùng chủ động dừng Start
    "aborted":  {"color": 0xE67E22, "icon": "⛔", "label": "TOOL DỪNG BẤT THƯỜNG"},  # cam: tool dừng do lỗi / bị kill
    "warn":     {"color": 0xFEE75C, "icon": "🟡", "label": "CẢNH BÁO"},          # vàng: RAM thấp
    "restart":  {"color": 0x3498DB, "icon": "🔄", "label": "TỰ ĐỘNG RESTART"},   # xanh dương: lịch tự dọn / reset tab
    "hop":      {"color": 0x9B59B6, "icon": "🔀", "label": "ĐỔI SERVER"},         # tím: Auto Server Hop
}
PING_LEVELS = ("critical", "aborted")   # mức nào thì ping @everyone (thêm "lobby" / "success" nếu muốn ping cả hai)
ALERT_COOLDOWN_SEC = 20       # cùng 1 cảnh báo của cùng 1 tab trong khoảng này chỉ gửi 1 lần (chống spam)
_ALERT_LAST = {}
REJOIN_COUNT = {}             # pkg -> số lần đã phải rejoin trong phiên chạy này
ACCOUNTS = {}                 # pkg -> tên tài khoản Roblox đã login bằng mục Login Cookie (chỉ lưu tên, KHÔNG lưu cookie)
CYCLE_START = None            # chế độ 2: mốc bắt đầu chu kỳ hiện tại (để tính "còn bao lâu tới lần rejoin kế")
_LOG_LOCK = threading.Lock()

# ==================== NHẬT KÝ FILE ====================
def log_event(kind, pkg=None, detail="", code=None, rejoin=None):
    """Ghi 1 dòng vào LOG_FILE: giờ | loại | package | mã lỗi | lần rejoin | chi tiết. Lỗi ghi file không làm tool dừng."""
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
    """(chữ trạng thái, màu dot) của 1 tab."""
    if not is_app_running(pkg):
        return "Đã tắt", False
    if not is_app_in_foreground(pkg):
        return "Lobby", None
    if pkg in JOINED_AT:
        return "Trong map", True
    return "Đang vào", None

def print_status_table(packages=None):
    """Bảng trạng thái nhỏ: tab nào đang chạy, số lần rejoin, thời gian trong map, tổng thời gian chạy, còn bao lâu tới chu kỳ rejoin kế."""
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
        sw, rw, mw = 11, 3, 7
        nw = max(8, inner - sw - rw - mw - 3)
        states = [(pkg,) + tab_state(pkg) for pkg in packages]
        running = sum(1 for _p, _t, st in states if st is not False)
        print(box_top(w))
        print(box_row(f"{C.WHT}TRẠNG THÁI TAB{C.R}", w, "center"))
        print(box_sep(w))
        print(box_kv("Chạy tổng", f"{C.WHT}{total}{C.R}", w))
        print(box_kv("Cơ chế", f"{C.WHT}{get_rejoin_mode_str()}{C.R}", w))
        print(box_kv("Rejoin kế", f"{C.WHT}{nxt}{C.R}", w))
        if NEXT_AUTO_RESTART and AUTO_RESTART_HOURS:
            rl = NEXT_AUTO_RESTART - now
            print(box_kv("Restart kế", f"{C.WHT}{fmt_duration(rl) if rl > 0 else 'sắp tới'} ({auto_restart_label()}){C.R}", w))
        print(box_kv("Tab chạy", f"{C.WHT}{running}/{len(packages)}{C.R}", w))
        print(box_sep(w))
        print(box_row(f"{C.GRY}{pad('Tab', nw)} {pad('Trạng thái', sw)} {pad('RJ', rw)} {pad('Map', mw)}{C.R}", w))
        for pkg, text, st in states:
            short = pkg[len(PACKAGE_PREFIX):].lstrip(".") if pkg.startswith(PACKAGE_PREFIX) and pkg != PACKAGE_PREFIX else pkg
            if ALIASES.get(pkg):
                short = ALIASES[pkg]
            if ACCOUNTS.get(pkg):
                short = f"{short} ({ACCOUNTS[pkg]})"
            in_map = fmt_duration(now - JOINED_AT[pkg]) if pkg in JOINED_AT and st else "—"
            row = (f"{pad(clip(short, nw), nw)} {pad(dot(st) + ' ' + clip(text, sw - 2), sw)} "
                   f"{pad(str(REJOIN_COUNT.get(pkg, 0)), rw)} {pad(in_map, mw)}")
            print(box_row(row, w))
        print(box_bot(w))
    except Exception as e:
        print(f"\033[1;31m[!] Không hiển thị được bảng trạng thái: {e}\033[0m")

def notify_tool_stopped(reason, unexpected=False):
    """Gửi cảnh báo Discord khi tool dừng. Gửi ĐỒNG BỘ (không dùng luồng nền) để kịp gửi trước khi tool thoát."""
    if not WEBHOOK_URL:
        return
    up = fmt_duration(time.time() - START_UP_TIME.timestamp()) if START_UP_TIME else "?"
    total = sum(REJOIN_COUNT.values())
    print("\033[1;33m[*] Đang gửi cảnh báo dừng tool lên Discord...\033[0m")
    send_detailed_alert("aborted" if unexpected else "stopped", "Tool đã dừng",
                        f"Tool đã dừng sau **{up}** chạy, tổng cộng **{total}** lần rejoin.",
                        reason=reason,
                        action="Cần mở lại tool để tiếp tục treo máy" if unexpected else "Người dùng chủ động dừng, không cần xử lý")

# ---- Cảnh báo RAM thấp (tool chạy trên Cloud Phone nên không cảnh báo pin) ----
LOW_RAM_ALERT = True
LOW_RAM_MB = 500              # RAM trống (MemAvailable) dưới ngưỡng này -> cảnh báo + tự dọn cache
LOW_RAM_AUTO_CLEAN = True
LOW_RAM_COOLDOWN_SEC = 300    # sau mỗi lần cảnh báo, 5 phút sau mới cảnh báo lại (chống spam Discord)
_LOW_RAM_LAST = 0

# ---- Kiểm tra cập nhật khi mở tool ----
UPDATE_URL = "https://paintool-bot.onrender.com/api/version"   # cần trả về JSON {"version": "v1.5.6"} hoặc text trơn "v1.5.6"
UPDATE_INFO = {"latest": None}

# ---- Profile & hẹn giờ ----
PROFILES = {}                 # tên -> {target_link, selected_game_name, auto_rejoin_mode, delay_rejoin_minutes, package_prefix}
SCHEDULE = {"start": "", "stop": ""}   # "HH:MM" (giờ máy), rỗng = tắt
SCHED_FIRED = {}
STOP_REASON = ""              # "" | "schedule": lý do dừng Start
_LISTENER_GEN = 0

def _valid_hhmm(v):
    return isinstance(v, str) and bool(re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v))

# ==================== CẢNH BÁO RAM THẤP ====================
def get_free_ram_mb():
    """RAM còn trống (MB, theo MemAvailable) hoặc None nếu không đọc được."""
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except Exception:
        pass
    return None

def check_low_ram(packages):
    """RAM trống < LOW_RAM_MB: cảnh báo trên màn hình + Discord, và tự dọn cache nếu bật (cần root)."""
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
    """Hỏi server bản mới nhất. Trả về chuỗi phiên bản hoặc None nếu không lấy được."""
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

def startup_update_check():
    try:
        latest = with_spinner("Đang kiểm tra cập nhật", fetch_latest_version)
    except Exception:
        latest = None
    UPDATE_INFO["latest"] = latest
    if not latest:
        msg_info("Không kiểm tra được bản cập nhật (bỏ qua).")
        time.sleep(0.8)
    elif update_available():
        msg_warn(f"Có bản mới: {latest} (đang dùng {VERSION}).")
        print(f" {C.GRY}Lấy bản mới tại:{C.R} {C.CYN}{DISCORD_LINK}{C.R}")
        wait_enter()
    else:
        msg_done(f"Bạn đang dùng bản mới nhất ({VERSION}).")
        time.sleep(1)

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
    """Đến giờ tự chạy (trong 10 phút đầu, mỗi ngày 1 lần)."""
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
    """Đến giờ tự dừng và lần Start hiện tại bắt đầu TRƯỚC giờ dừng đó (hỗ trợ chạy qua đêm)."""
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
    """Như ask() nhưng ở menu chính vẫn theo dõi giờ hẹn: đến giờ tự chạy thì trả về '1' (Start)."""
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
ALIASES = {}                  # pkg -> biệt danh ngắn (vd: com.roblox.client -> Acc Main)
NET_CHECK = True              # ping 8.8.8.8 trước khi rejoin; mất mạng thì tạm dừng, không mở app liên tục
GFX_FILE = "GlobalBasicSettings_13.xml"
GFX_LOW = True                # Graphics Optimizer: hạ đồ họa xuống mức thấp nhất khi áp dụng
GFX_FPS = 30                  # Graphics Optimizer: giới hạn FPS (15 / 20 / 30, 0 = không giới hạn)
GFX_AUTO = False              # tự áp dụng cài đặt trên cho mọi tab mỗi lần bấm Start
AUTO_RESTART_HOURS = 0        # Lịch tự restart: 0 = tắt, 2 / 3 / 4 = số giờ treo liên tục giữa 2 lần
AUTO_RESTART_ACTION = "reset" # "clean" = chỉ dọn RAM + cache, "reset" = dọn + tắt Đa nhiệm + vào lại Map toàn bộ tab
NEXT_AUTO_RESTART = None      # mốc (epoch) restart kế tiếp, để hiện trong bảng trạng thái
SCREENSHOT_MIN_GAP_SEC = 60   # chống spam: tối thiểu bấy nhiêu giây giữa 2 lần chụp màn hình gửi Discord
_LAST_SHOT = 0
EXECUTOR_NAMES = ["Delta", "Codex", "ArceusX", "Fluxus", "Hydrogen", "Valyse", "VegaX", "Krampus", "Evon"]

def tab_name(pkg):
    """Tên ngắn để hiển thị: biệt danh nếu có, không thì package."""
    return ALIASES.get(pkg) or pkg

def tab_label(pkg):
    """Biệt danh (package) nếu có biệt danh, không thì chỉ package."""
    return f"{ALIASES[pkg]} ({pkg})" if ALIASES.get(pkg) else pkg

# ==================== KIỂM TRA MẠNG TRƯỚC KHI REJOIN ====================
def _rc(cmd, timeout=6):
    try:
        return subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL, timeout=timeout).returncode
    except Exception:
        return -1

def is_online():
    """Ping 8.8.8.8. Máy không có lệnh ping hoặc chặn ICMP thì thử thêm 1 request HTTP nhẹ để khỏi báo mất mạng nhầm."""
    if _rc(["ping", "-c", "1", "-W", "3", "8.8.8.8"], timeout=6) == 0:
        return True
    out = run_cmd(["curl", "-s", "-m", "5", "-o", "/dev/null", "-w", "%{http_code}",
                   "http://connectivitycheck.gstatic.com/generate_204"], timeout=8)
    return out.strip() in ("204", "200")

def wait_for_network(label=""):
    """Mất mạng: tạm dừng (không mở app, không đếm ngược) tới khi có mạng lại.
    Trả về (bị_dừng_giữa_chừng, số_giây_mất_mạng)."""
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

# ==================== CLIENT KEY INJECTOR (giữ & chèn lại key/token của Client) ====================
KEY_AUTO = True                    # tự lưu key vào vault khi tab chạy ổn, tự chèn lại khi file key bị mất (reset / xóa data)
KEY_FILES = {}                     # pkg -> [đường dẫn tuyệt đối của file key/token cần giữ] (chỉ lưu ĐƯỜNG DẪN trong config, không lưu nội dung)
KEY_VAULT_DIR = os.path.join(os.path.expanduser("~"), ".pain_keyvault")   # nơi lưu bản sao file key (quyền 700 / 600, không gửi đi đâu)
KEY_SAVE_INTERVAL_SEC = 600
KEY_MAX_BYTES = 64 * 1024

# ==================== PHÁT HIỆN MÀN HÌNH TRẮNG/ĐEN, GUI ĐỨNG, NOT RESPONDING ====================
WB_DETECT = True                   # màn hình trắng/đen kẹt (không tải được tài nguyên game) -> rejoin ngay
OVERLAY_DETECT = True              # ANR "Not Responding" + khung hình đứng im (GUI / overlay của Client treo) -> kill-process rồi chạy lại
SCREEN_CHECK_SEC = 15              # chu kỳ quét màn hình khi đang Start
SCREEN_GRACE_SEC = 60              # tab vừa mở: bỏ qua từng này giây đầu (đang tải là bình thường)
WB_CONFIRM_COUNT = 3               # số lần quét liên tiếp thấy trắng/đen mới kết luận là kẹt
WB_UNIFORM_RATIO = 0.995           # >= tỉ lệ này điểm ảnh cùng 1 màu mới coi là "trắng/đen kẹt" (logo / chữ loading làm tỉ lệ thấp hơn)
OVERLAY_FREEZE_SEC = 150           # khung hình không đổi + không có log mới quá từng này giây = GUI đứng
SCREEN_COOLDOWN_SEC = 120          # 1 tab vừa bị xử lý thì từng này giây sau mới được xử lý lại
MAP_POLL_SEC = 3                   # lúc vào map: quét xem đã vào map chưa mỗi từng này giây
WB_JOIN_CONFIRM = 3                # lúc vào map: số lần quét liên tiếp thấy trắng/đen
JOIN_MARKERS = ("joining game", "connection accepted", "replicator created", "game join succeeded")   # dấu hiệu trong log là đã vào map (chỉ để thoát chờ sớm, không bắt buộc)
SCREEN_STATE = {}                  # pkg -> {"wb": số lần trắng/đen liên tiếp, "fp": dấu vân tay khung hình, "since": từ lúc nào}
SCREEN_COOLDOWN = {}
LAUNCHED_AT = {}                   # pkg -> lúc gửi lệnh mở tab gần nhất
ANR_SEEN = {}
_SCREEN_LAST_SWEEP = 0
_FRAME_WARNED = False
SCREEN_REASON_KEYS = ("màn hình trắng", "màn hình đen", "not responding", "overlay")
_FRAME_RX = re.compile(r"(?:mFrame|frame)=\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")

def is_screen_reason(reason):
    low = (reason or "").lower()
    return any(k in low for k in SCREEN_REASON_KEYS)

def sh_bytes(cmd, timeout=15):
    """Chạy lệnh shell (qua su nếu có root) và trả về stdout NGUYÊN BẢN dạng bytes (không cắt khoảng trắng, không giải mã)."""
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
    """Quét các file nhỏ có tên chứa key / token / license trong dữ liệu của tab và thư mục các client phổ biến."""
    q = shlex.quote
    roots = [_app_dir(pkg), f"/sdcard/Android/data/{pkg}"] + [f"/sdcard/{n}" for n in EXECUTOR_NAMES]
    cmd = ("find " + " ".join(q(r) for r in roots) +
           " -maxdepth 5 -type f \\( -iname '*key*' -o -iname '*token*' -o -iname '*license*' \\) -size -64k"
           " ! -iname '*keyboard*' ! -iname '*.log' ! -path '*/cache/*' ! -path '*/code_cache/*'"
           " ! -path '*/app_webview/*' ! -path '*/app_textures/*' 2>/dev/null | head -n 40")
    out = sh(cmd, timeout=25)
    return [x.strip() for x in out.splitlines() if x.strip().startswith("/")]

def key_save(pkg):
    """Chép file key/token đang có của tab vào vault (chỉ khi nội dung thay đổi). Trả về (số file mới/đổi, số file bỏ qua)."""
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
            os.replace(fp, fp + ".prev")   # giữ thêm 1 bản cũ
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
            return False   # app chưa được cài / chưa có thư mục dữ liệu
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
    """Chèn lại file key/token từ vault nếu file đang thiếu hoặc rỗng (sau reset / xóa data).
    force=True: ghi đè kể cả khi file còn. Trả về số file đã chèn."""
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
    """Tab đã vào map ổn định (nghĩa là key đang dùng được) thì lưu / cập nhật bản sao key vào vault."""
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
    """Đầu ra của `screencap` (không -p): header w,h,format (+ colorspace trên Android 9+) rồi điểm ảnh RGBA."""
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
    """Lấy mẫu lưới điểm ảnh (trong rect của tab nếu có). Trả về {"kind": white|black|ok, "median", "uniform", "fp"}."""
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
    """1 lần dumpsys: tab nào đang có focus, vùng cửa sổ của từng tab, và tab nào đang hiện hộp thoại 'Not Responding'."""
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
    """Quét các tab đang chạy. Trả về [(pkg, lý do)] cần kill-process rồi vào lại:
    - ANR / hộp thoại 'Not Responding' (GUI, nút bấm không phản hồi)
    - màn hình trắng/đen kẹt liên tiếp WB_CONFIRM_COUNT lần quét
    - khung hình đứng im >= OVERLAY_FREEZE_SEC mà không có log mới (overlay / GUI Client treo)"""
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
    """Quét 1 tab ngay (dùng lúc vào map). Trả về ('anr' | 'white' | 'black' | 'ok' | None nếu không xác định được)."""
    snap = window_snapshot([pkg])
    if pkg in snap["anr"]:
        return "anr"
    if pkg not in snap["rects"] and snap["focus"] != pkg:
        return None
    if BLACK_SCREEN_ACTIVE:      # đang chủ động tắt màn hình: ảnh chụp đen là bình thường, không dò trắng/đen
        return None
    frame = capture_frame()
    if frame is None:
        return None
    res = analyze_frame(frame, snap["rects"].get(pkg))
    return res["kind"] if res else None

def wait_map_load(pkg):
    """Chờ map load tối đa MAP_LOAD_WAIT giây và quét liên tục xem tab đã vào map chưa.
    Phát hiện lỗi / trắng-đen / ANR là trả về ngay (không chờ hết thời gian). Trả về lý do nếu chưa ổn, None nếu ổn.
    (Người dùng bấm dừng: trả về None, caller kiểm tra stop_start.)"""
    t0 = time.time()
    bad = 0
    joined_hint = False
    while time.time() - t0 < MAP_LOAD_WAIT:
        if wait_with_stop_check(MAP_POLL_SEC):
            return None
        if not is_app_running(pkg):
            return "Game bị tắt / crash (không còn tiến trình)"
        text = read_new_log_text(pkg)
        found, reason = scan_text_for_problem(text)
        if found:
            return f"{reason} (Log File)"
        text2 = read_new_logcat_text(pkg)
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

def save_config_file():
    try:
        data = {
            "webhook_url": WEBHOOK_URL,
            "discord_uid": DISCORD_UID,
            "auto_clear_data": AUTO_CLEAR_DATA,
            "freeze_timeout_min": FREEZE_TIMEOUT_MIN,
            "auto_backup": AUTO_BACKUP,
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
            "black_screen": BLACK_SCREEN
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

def msg_done(text):
    """Thông báo hoàn thành thao tác (xanh lá, có dấu ✓)."""
    print(f"\n {C.GRN}[✓] {text}{C.R}")

def msg_warn(text):
    print(f" {C.YEL}[!] {text}{C.R}")

def msg_cancel(text):
    print(f"\n {C.YEL}[-] {text}{C.R}")

def wait_enter(text="Ấn Enter để tiếp tục..."):
    """Dừng để người dùng kịp đọc thông báo trước khi màn hình bị xóa."""
    try:
        input(f"\n {C.GRY}{text}{C.R} ")
    except EOFError:
        pass

def exit_tool():
    print(f"\n {C.GRN}[✓] Đã thoát tool thành công. Good bye!{C.R}")
    time.sleep(1)
    sys.exit(0)

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
    """Xác thực key qua Web Service Render (/api/keys/verify), có ký HMAC-SHA256 kèm timestamp
    (giống server routes/verifySignature.js) để chặn script spam gọi thẳng API không qua tool.
    Dùng thư viện 'requests' nếu Termux đã cài; nếu chưa thì tự dùng curl (đỡ phải cài thêm gói)."""
    global LAST_LICENSE_EXPIRES
    timestamp = int(time.time())
    raw_data = f"{key}:{hwid}:{timestamp}"
    signature = hmac.new(SECRET_KEY.encode("utf-8"), raw_data.encode("utf-8"), hashlib.sha256).hexdigest()
    payload = {"key": key, "hwid": hwid, "timestamp": timestamp, "signature": signature}
    data = None

    if _HAS_REQUESTS:
        try:
            res = requests.post(API_URL, json=payload, timeout=10)
            data = res.json()
        except Exception:
            return False, "Không kết nối được server"
    else:
        try:
            res_text = run_cmd([
                "curl", "-s", "-X", "POST", API_URL,
                "-H", "Content-Type: application/json",
                "-d", json.dumps(payload),
                "--connect-timeout", "10"
            ], timeout=15)
            if not res_text:
                return False, "Không kết nối được server"
            data = json.loads(res_text)
        except Exception:
            return False, "Không kết nối được server"

    if not isinstance(data, dict):
        return False, "Phản hồi không hợp lệ từ server"

    LAST_LICENSE_EXPIRES = str(data.get("expiresAt") or "")
    if data.get("valid") is True:
        return True, data.get("message", "ok")
    return False, data.get("message", "Key không hợp lệ hoặc sai HWID")

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
                extra = f" Hạn dùng đến: {LAST_LICENSE_EXPIRES}" if LAST_LICENSE_EXPIRES else ""
                msg_ok(f"Tự động xác thực bản quyền thành công!{extra}")
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
            exit_tool()
        if not input_key:
            continue
        is_valid, response_text = with_spinner("Đang kết nối máy chủ", check_license_curl, input_key, hwid)
        if is_valid:
            try:
                with open(LICENSE_FILE, "w") as f:
                    f.write(input_key)
            except Exception:
                pass
            extra = f" Hạn dùng đến: {LAST_LICENSE_EXPIRES}" if LAST_LICENSE_EXPIRES else ""
            msg_ok(f"Xác thực Key thành công!{extra}")
            time.sleep(1)
            break
        if response_text == "Không kết nối được server":
            note = f"{C.YEL}[!] Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại.{C.R}"
        else:
            note = f"{C.RED}[!] Thất bại: Key không hợp lệ hoặc sai HWID.{C.R}"

def send_webhook(message, with_image=False):
    global _LAST_SHOT
    if BLACK_SCREEN_ACTIVE:
        with_image = False   # màn hình đen thì ảnh chụp vô nghĩa
    if not webhook_active():
        return   # chưa set URL webhook: không gửi và cũng không chụp màn hình
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
            with_image = False   # vừa chụp gần đây: chỉ gửi chữ, không chụp thêm
        if with_image:
            _LAST_SHOT = time.time()
            try:
                os.remove(SCREENSHOT_PATH)   # bỏ ảnh cũ còn sót để không gửi nhầm ảnh cũ
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
    if "màn hình trắng" in low or "màn hình đen" in low:
        return "Màn hình trắng/đen kẹt"
    if "not responding" in low:
        return "Client Not Responding"
    if "overlay" in low:
        return "Overlay / GUI client bị đứng"
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
        add("🏷️ Biệt danh", ALIASES.get(pkg) if pkg else None)
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
        if level in PING_LEVELS:
            mention = "@everyone" + (f" <@{DISCORD_UID}>" if DISCORD_UID else "")
            payload_dict["content"] = mention
            payload_dict["allowed_mentions"] = {"parse": ["everyone", "users"]}

        payload_json = json.dumps(payload_dict)
        run_cmd([
            "curl", "-s", "-X", "POST", WEBHOOK_URL,
            "-H", "Content-Type: application/json",
            "-d", payload_json
        ], timeout=10)
    except Exception:
        pass

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

def build_deep_link(pkg=None):
    """Link vào game. Đang đổi server cho tab (HOP_OVERRIDE) hoặc tab đã chuyển sang VIP server khác (HOP_CURRENT) thì dùng link đó."""
    link = (HOP_OVERRIDE.get(pkg) or HOP_CURRENT.get(pkg) or TARGET_LINK) if pkg else TARGET_LINK
    if not link:
        return None
    if link.startswith("roblox://") or link.startswith("http"):
        return link
    return f"roblox://placeId={link}"

def launch_commands(pkg, enter_map=True, soft=False):
    """Các cách mở game, ưu tiên cách đầu; lỗi thì dùng cách dự phòng.
    enter_map=False: chỉ mở app, không vào map.
    soft=True: tab đang chạy -> giữ nguyên task (không tắt Đa nhiệm), chỉ đưa lên và gửi lệnh vào map.
    soft=False: --activity-clear-task để tab mới thay thế hẳn tab cũ trong Đa nhiệm."""
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
    """Mốc mới cho tab: log/logcat cũ trước thời điểm này bị bỏ qua, và thời gian 'treo' được tính lại từ đầu."""
    path = get_latest_log_file(pkg)
    LOG_STATE[pkg] = (path, get_file_size(path) if path else 0)
    LOGCAT_BASELINE[pkg] = time.time()
    LAST_ACTIVITY[pkg] = time.time()
    LAUNCHED_AT[pkg] = time.time()
    SCREEN_STATE.pop(pkg, None)
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
    if not running:
        key_ensure(pkg)   # tab đang tắt (vừa reset / xóa data): chèn lại key/token từ vault trước khi mở
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

def retry_countdown(pkg, why):
    """Tab không vào lại được game: đếm ngược RETRY_COUNTDOWN_SECONDS giây. Hết giờ thì caller tắt Đa nhiệm (force-stop) và vào lại.
    Mất mạng thì tạm dừng, chờ có mạng rồi mới đếm ngược.
    Trả về True nếu bị ngắt giữa chừng (bấm dừng Start)."""
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
    """Vào Map tối đa LAUNCH_MAX_RETRY lần (dùng chung cho chế độ 1 và 2).
    Mỗi lần: mở / gửi lệnh vào map -> chờ app lên -> chờ map load -> kiểm tra lại.
    Tab không vào được game: đếm ngược 5s -> tắt hẳn tab (tắt Đa nhiệm) -> mở lại vào map.
    Lần 1: tab đã mở sẵn thì chỉ vào map, không tắt Đa nhiệm (trừ khi hard=True). Từ lần 2 trở đi luôn tắt hẳn rồi mở lại."""
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
        problem = wait_map_load(pkg)   # quét liên tục xem đã vào map chưa, lỗi / trắng-đen / ANR thì thử lại ngay
        if stop_start:
            return False
        if not problem:
            JOINED_AT[pkg] = time.time()
            print(f"\033[1;32m[+] {tab_label(pkg)} đã vào Map.\033[0m")
            return True
        print(f"\033[1;31m[!] {tab_label(pkg)} chưa vào được Map [{problem}].\033[0m")
        log_event("JOIN_ERR", pkg, f"lần {attempt}/{LAUNCH_MAX_RETRY}: {problem}")
        if attempt < LAUNCH_MAX_RETRY and retry_countdown(pkg, "Tab không vào lại được game"):
            return False

    print(f"\033[1;31m[!] Không vào được Map {tab_label(pkg)} sau {LAUNCH_MAX_RETRY} lần.\033[0m")
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
        print(f"\033[1;33m[-] {tab_label(pkg)} bị thoát ra Màn hình chính/Lobby. Đang đếm ngược 5s...\033[0m")
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
    log_event("REJOIN_OK" if ok else "REJOIN_FAIL", pkg,
              f"{action}; mất {took}s" if ok else f"không vào được Map sau {LAUNCH_MAX_RETRY} lần thử ({action}); mất {took}s",
              rejoin=REJOIN_COUNT.get(pkg))
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
                ready = [sys.stdin]   # máy không hỗ trợ select: đọc chặn như cũ
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

def launch_all(packages, hard=False):
    """Vào Map lần lượt các tab (>=4 tab: nhóm 3 tab, cách nhau 15s).
    hard=False: tab đã mở sẵn thì chỉ vào Map, không tắt Đa nhiệm (lúc bấm Start).
    hard=True : tắt hẳn từng tab (tắt Đa nhiệm) rồi mở lại vào Map (chế độ 2 hết chu kỳ).
    Mỗi tab thử vào Map tối đa LAUNCH_MAX_RETRY lần."""
    total = len(packages)
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

def start_tool():
    global stop_start, START_UP_TIME, CYCLE_START, STOP_REASON, _LISTENER_GEN, NEXT_AUTO_RESTART, _HOP_LAG, _HOP_PAUSE_UNTIL
    stop_start = False
    CYCLE_START = None
    STOP_REASON = ""
    _LISTENER_GEN += 1
    gen = _LISTENER_GEN
    if _valid_hhmm(SCHEDULE.get("start")) and datetime.now() >= _today_at(SCHEDULE["start"]):
        SCHED_FIRED["start"] = datetime.now().date()   # đã Start tay sau giờ hẹn: hôm nay không tự Start lại
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
    report_on = webhook_active()   # báo cáo Discord 5 phút chỉ bật khi đã set URL webhook rồi bấm Start
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
                # Quét màn hình trắng/đen kẹt, ANR "Not Responding", GUI / overlay của Client đứng -> kill-process rồi vào lại ngay
                if not stop_start:
                    for pkg, why_screen in screen_guard(packages):
                        if stop_start: break
                        recover_tab(pkg, why_screen)

            elif AUTO_REJOIN_MODE == 2:
                # Chế độ 2: hết chu kỳ -> tự thoát app game + tắt Đa nhiệm từng tab rồi mở lại vào Map (thử tối đa 3 lần/tab).
                # (Vào lại Map mà không tắt tab thì Roblox bỏ qua vì đang ở đúng map đó, nên phải tắt hẳn mới rejoin thật.)
                # Không có tự động rejoin khi crash ở chế độ này.
                if elapsed_minutes >= DELAY_REJOIN_MINUTES:
                    print(f"\033[1;33m[*] Chu kỳ {DELAY_REJOIN_MINUTES}p hoàn tất. Tắt Đa nhiệm và vào lại Map toàn bộ tab...\033[0m")
                    for _p in packages:
                        REJOIN_COUNT[_p] = REJOIN_COUNT.get(_p, 0) + 1
                    log_event("CYCLE", detail=f"Hết chu kỳ {DELAY_REJOIN_MINUTES}p, tắt Đa nhiệm và vào lại {len(packages)} tab")
                    launch_all(packages, hard=True)
                    start_time = time.time()
                    CYCLE_START = start_time

            # Lịch tự động restart: treo liên tục đủ 2-4 giờ thì dọn RAM / reset toàn bộ tab
            if not stop_start and auto_restart_due(last_auto_restart):
                do_auto_restart(packages)
                last_auto_restart = time.time()
                NEXT_AUTO_RESTART = last_auto_restart + AUTO_RESTART_HOURS * 3600
                if AUTO_RESTART_ACTION == "reset":
                    start_time = last_auto_restart   # vừa reset toàn bộ tab: tính lại chu kỳ chế độ 2
                    CYCLE_START = start_time
                if stop_start:
                    break

            # Auto Clear Data / khôi phục tab kẹt (chạy ở cả 2 chế độ), kiểm tra mỗi 10 giây
            if AUTO_CLEAR_DATA and not stop_start and (time.time() - last_freeze_check) >= 10:
                last_freeze_check = time.time()
                net_down = NET_CHECK and not is_online()
                for pkg in packages:
                    if stop_start: break
                    if AUTO_REJOIN_MODE == 2:
                        collect_new_logs(pkg)   # chế độ 1 đã đọc log trong detect_problem
                    if net_down:
                        LAST_ACTIVITY[pkg] = time.time()   # mất mạng: không có log là bình thường, không coi là treo
                    elif is_tab_frozen(pkg):
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
                    print("\033[1;32m[*] Đã đủ 5 phút, đang gửi báo cáo ảnh chụp màn hình định kỳ (Im lặng, không ping)...\033[0m")
                    send_webhook("Cập nhật trạng thái định kỳ (5 phút)", with_image=True)
                print_status_table(packages)

            if wait_with_stop_check(2): break

        if stop_start:
            restore_screen_after_run()
            if STOP_REASON == "schedule":
                why = f"Đến giờ hẹn dừng {SCHEDULE['stop']}"
                print(f"\n\033[1;32m[✓] Đã dừng Start theo hẹn giờ ({SCHEDULE['stop']}). Quay lại menu...\033[0m")
            else:
                why = "Người dùng bấm 0 để dừng Start"
                print("\n\033[1;31m[!] Đã dừng Start. Quay lại menu...\033[0m")
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
        restore_screen_after_run()      # chốt chặn cuối (bị kill / SystemExit): luôn trả lại độ sáng gốc
        NEXT_AUTO_RESTART = None
        for sig, handler in old_handlers.items():
            try:
                signal.signal(sig, handler)
            except Exception:
                pass

# ==================== CHẾ ĐỘ MÀN HÌNH ĐEN (BLACK SCREEN) ====================
BLACK_SCREEN = False              # bật: khi Start, hạ độ sáng về 0 (và tắt hiển thị nếu máy hỗ trợ) để đỡ tốn GPU
BLACK_SCREEN_ACTIVE = False       # đang ở trạng thái màn hình đen (chạy thật) -> tạm tắt các phép dò dựa trên ảnh chụp màn hình
SCREEN_RESTORE_FILE = os.path.join(os.path.expanduser("~"), ".pain_screen_restore.json")

def _settings_get(key):
    out = sh(f"settings get system {key}", timeout=6).strip()
    return out if re.fullmatch(r"-?\d{1,5}", out) else None

def _settings_put(key, value):
    """Ghi 1 giá trị settings system rồi đọc lại để xác nhận. True nếu đã ghi được."""
    sh(f"settings put system {key} {int(value)}", timeout=6)
    return _settings_get(key) == str(int(value))

def _screen_state_load():
    """Đọc file khôi phục (độ sáng gốc). Chỉ nhận số nguyên hợp lệ vì giá trị này sẽ được đưa vào lệnh shell."""
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
    """Hạ độ sáng màn hình về 0, thử thêm lệnh tắt hiển thị. Độ sáng gốc được lưu ra file để luôn khôi phục lại được.
    Trả về (ok, thông báo)."""
    global BLACK_SCREEN_ACTIVE
    if BLACK_SCREEN_ACTIVE:
        return True, "đã ở chế độ màn hình đen"
    st = _screen_state_load()                      # có file cũ (lần trước chưa khôi phục) thì giữ nguyên giá trị gốc đó
    if st is None:
        level = _settings_get("screen_brightness")
        if level is None:
            return False, "không đọc được độ sáng màn hình (cần root, hoặc cấp quyền 'Sửa đổi cài đặt hệ thống' cho Termux)"
        st = {"level": level, "mode": _settings_get("screen_brightness_mode"), "poweroff": False}
        if not _screen_state_save(st):
            return False, "không ghi được file khôi phục độ sáng nên không dám đổi (tránh kẹt màn hình đen)"
    if st["mode"] is not None:
        _settings_put("screen_brightness_mode", 0)     # tắt tự động chỉnh sáng, nếu không hệ thống sẽ tự tăng lại
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
    """Khôi phục độ sáng gốc (và bật lại hiển thị). Trả về (ok, thông báo)."""
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
    """Gọi lúc mở tool: lần chạy trước bị tắt giữa chừng khi đang màn hình đen thì tự khôi phục."""
    if os.path.exists(SCREEN_RESTORE_FILE):
        ok, msg = black_screen_off()
        print(f" {C.GRN if ok else C.YEL}[{'✓' if ok else '!'}] Lần chạy trước chưa khôi phục màn hình: {msg}.{C.R}")
        time.sleep(1.2)

def menu_black_screen():
    global BLACK_SCREEN
    clear_screen()
    section_title("CHẾ ĐỘ MÀN HÌNH ĐEN (BLACK SCREEN)")
    print(f" {C.GRY}Trạng thái:{C.R} {C.WHT}{'BẬT' if BLACK_SCREEN else 'TẮT'}{C.R}")
    print(" Khi bấm Start, tool hạ độ sáng về 0 (và tắt hiển thị nếu máy hỗ trợ) để máy bớt vẽ hình;")
    print(" Roblox vẫn chạy ngầm. Bấm 0 để dừng Start thì độ sáng được trả lại như cũ.")
    print(f" {C.GRY}Lưu ý: mức giảm tải GPU/CPU tùy máy (tool không đo được). Khi đang bật, các phép dò")
    print(f" màn hình trắng/đen & GUI đứng (dựa trên ảnh chụp) tự tạm tắt để không báo nhầm.{C.R}")
    if not root_mode():
        msg_warn("Máy chưa root: đổi độ sáng có thể bị từ chối. Dùng mục 3 để thử trước.")
    print("\033[1;37m1. Bật\033[0m")
    print("\033[1;37m2. Tắt\033[0m")
    print("\033[1;37m3. Thử ngay 8 giây (tự khôi phục)\033[0m")
    print("\033[1;37m4. Khôi phục màn hình ngay (nếu đang bị kẹt đen)\033[0m")
    print("\033[1;32m0. Quay lại\033[0m")
    sub = input("Chọn: ").strip()
    if sub == "1":
        BLACK_SCREEN = True
    elif sub == "2":
        BLACK_SCREEN = False
    elif sub == "3":
        msg_info("Đang thử chế độ màn hình đen 8 giây...")
        ok, msg = black_screen_on()
        if ok:
            msg_done(msg)
            for left in range(8, 0, -1):
                print(f"\r {C.GRY}Tự khôi phục sau {left}s... {C.R}", end="", flush=True)
                time.sleep(1)
            print()
            ok2, msg2 = black_screen_off()
            (msg_done if ok2 else msg_err)(msg2)
        else:
            msg_err(msg)
        wait_enter()
        return
    elif sub == "4":
        ok, msg = black_screen_off()
        (msg_done if ok else msg_warn)(msg + ("" if ok else "."))
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
    msg_done(f"Đã {'BẬT' if BLACK_SCREEN else 'TẮT'} chế độ màn hình đen và lưu cấu hình.")
    time.sleep(2)

def black_screen_label():
    return "Bật" if BLACK_SCREEN else "Tắt"

# ==================== AUTO SERVER HOP (ĐỔI SERVER KHI LAG) ====================
SERVER_HOP = False               # bật: độ trễ tới Roblox cao liên tục thì đổi sang server khác
HOP_PING_MS = 500                # ngưỡng độ trễ (ms)
HOP_CHECKS = 3                   # số lần đo liên tiếp vượt ngưỡng mới đổi
HOP_INTERVAL_SEC = 30            # chu kỳ đo độ trễ
HOP_COOLDOWN_SEC = 600           # 1 tab vừa đổi server thì từng này giây sau mới được đổi lại
HOP_MAX_PER_HOUR = 6
VIP_SERVERS = []                 # danh sách link VIP server để xoay vòng (tối đa MAX_VIP_SERVERS)
MAX_VIP_SERVERS = 10
HOP_OVERRIDE = {}                # pkg -> link dùng cho lần mở tiếp theo (đổi server public)
HOP_CURRENT = {}                 # pkg -> link VIP đang dùng (các lần rejoin sau vào đúng server này)
HOP_LAST = {}
HOP_LOG = []                     # mốc thời gian các lần đổi (để nhận ra "đổi mãi vẫn lag" = lỗi mạng của máy)
_HOP_LAG = 0
_HOP_PAUSE_UNTIL = 0
_HOP_RX_LINK = re.compile(r"(?:https://(?:www\.|web\.)?roblox\.com/|roblox://)[^\s'\"`;|<>$\\]{1,280}")   # cho phép & (link chia sẻ có nhiều tham số); link chỉ đi qua argv, không qua shell
_HOP_RX_ID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

def valid_vip_link(s):
    return bool(s) and len(s) <= 300 and bool(_HOP_RX_LINK.fullmatch(s))

def place_id_of(link):
    """Lấy Place ID từ ID thuần / link roblox:// / link roblox.com/games/<id>."""
    link = (link or "").strip()
    if re.fullmatch(r"\d{4,}", link):
        return link
    m = re.search(r"placeId=(\d{4,})", link) or re.search(r"/games/(\d{4,})", link)
    return m.group(1) if m else None

def measure_latency_ms(samples=3):
    """Độ trễ TCP từ máy tới Roblox (trung vị, ms). None = không đo được (máy không có curl). Kết nối hỏng/timeout tính là 5000ms."""
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
    """Server public còn chỗ, ít người, ping (nếu Roblox cho biết) không vượt ngưỡng. Chọn ngẫu nhiên trong 5 server tốt nhất để các tab không dồn vào 1 server."""
    ok = [s for s in servers if s["id"] != avoid and s["playing"] < s["max"]]
    if not ok:
        return None
    good = [s for s in ok if s["ping"] is None or s["ping"] <= HOP_PING_MS] or ok
    good.sort(key=lambda s: (s["playing"], s["ping"] or 0))
    pool = [s for s in good if s["playing"] >= 1][:5] or good[:5]
    return random.choice(pool)

def pick_hop_target(pkg):
    """(link, loại, mô tả). Ưu tiên VIP server trong danh sách (xoay vòng sang server khác server đang dùng), không có thì Public ít người."""
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
    """Đổi server cho 1 tab: tắt hẳn tab rồi vào server mới. Vào không được thì quay lại game gốc."""
    now = time.time()
    HOP_LAST[pkg] = now            # đặt cooldown ngay cả khi thất bại để khỏi thử dồn dập
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
    """Gọi định kỳ khi Start: đo độ trễ, vượt ngưỡng HOP_CHECKS lần liên tiếp thì đổi server cho 1 tab (mỗi lượt đo tối đa 1 tab)."""
    global _HOP_LAG, _HOP_PAUSE_UNTIL
    now = time.time()
    if now < _HOP_PAUSE_UNTIL:
        return
    if NET_CHECK and not is_online():          # mất mạng không phải lỗi của server, để cơ chế chờ mạng xử lý
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
        # đổi server nhiều lần mà vẫn lag = nhiều khả năng do mạng của máy, đổi tiếp vô ích
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
                print(f" {C.CYN}{i}.{C.R} {clip(v, ui_width() - 8)}")
        else:
            print(f" {C.GRY}(chưa có VIP server nào, khi cần đổi tool sẽ chọn Public server ít người){C.R}")
        print(f" {C.GRY}Đã có {len(VIP_SERVERS)}/{MAX_VIP_SERVERS}. Dán link VIP server của game (https://www.roblox.com/... hoặc roblox://...).{C.R}")
        print("\033[1;37m1. Thêm link VIP server\033[0m")
        print("\033[1;37m2. Xóa link (theo số thứ tự)\033[0m")
        print("\033[1;32m0. Quay lại\033[0m")
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
    print("\033[1;37m1. Bật\033[0m")
    print("\033[1;37m2. Tắt\033[0m")
    print("\033[1;37m3. Đổi ngưỡng độ trễ (200-2000 ms)\033[0m")
    print("\033[1;37m4. Quản lý danh sách VIP server\033[0m")
    print("\033[1;37m5. Đo độ trễ tới Roblox ngay\033[0m")
    print("\033[1;32m0. Quay lại\033[0m")
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
    """Dừng Start / có lỗi: trả độ sáng gốc NGAY (trước khi in thông báo / chờ Enter) để người dùng đọc được màn hình."""
    if BLACK_SCREEN_ACTIVE:
        ok, msg = black_screen_off()
        print(f"{C.GRN if ok else C.YEL}[{'✓' if ok else '!'}] Black Screen: {msg}.{C.R}")
        log_event("BLACKSCREEN", detail=f"tắt: {msg}")

# ==================== UPTIME WEB SERVER (DAEMON THREAD) ====================
_UPTIME_SERVER_STARTED = False

def start_uptime_server():
    """Mở Web Server ẩn chạy nền (daemon thread) để UptimeRobot / health-check ping giữ tool luôn thức.
    Port: biến môi trường PORT (nếu có) hoặc mặc định 8080.
    Trả về True nếu đã start, False nếu port bị chiếm / lỗi."""
    global _UPTIME_SERVER_STARTED
    if _UPTIME_SERVER_STARTED:
        return True

    try:
        port = int(os.environ.get("PORT", "8080"))
    except (TypeError, ValueError):
        port = 8080
    print(f"\033[1;36m[*] Web Server ẩn (UptimeRobot ping): http://0.0.0.0:{port}/\033[0m")

    class _HealthHandler(http.server.BaseHTTPRequestHandler):
        server_version = "PainToolHealth/1.0"

        _tabs_cache = {"t": 0.0, "n": 0}   # nhớ số tab 30 giây để ping dồn dập không chạy `pm list packages` liên tục

        def _payload(self):
            free = get_free_ram_mb()
            now = time.time()
            cache = self._tabs_cache
            if now - cache["t"] > 30:
                cache["n"] = len(list_installed_packages())
                cache["t"] = now
            uptime = int(time.time() - START_UP_TIME.timestamp()) if START_UP_TIME else 0
            return json.dumps({
                "status": "ok",
                "tool": "PAIN TOOL REJOIN VIP",
                "version": VERSION,
                "port": port,
                "uptime_sec": uptime,
                "uptime_human": fmt_duration(uptime),
                "tabs_running": cache["n"],
                "free_ram_mb": free,
                "rejoin_mode": get_rejoin_mode_str(),
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }, ensure_ascii=False).encode("utf-8")

        def do_GET(self):
            body = self._payload()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(body)
            except Exception:
                pass

        def do_HEAD(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()

        def log_message(self, *args):
            pass  # tắt log rác ra stdout để không phá UI Termux

    class _ReusableServer(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    def _serve():
        try:
            with _ReusableServer(("0.0.0.0", port), _HealthHandler) as httpd:
                httpd.serve_forever(poll_interval=1.0)
        except OSError as e:
            # Port bị chiếm hoặc không bind được -> im lặng bỏ qua, KHÔNG làm chết tool
            try:
                log_event("WEB", detail=f"Không mở được web server port {port}: {e}")
            except Exception:
                pass
        except Exception:
            pass

    t = threading.Thread(target=_serve, name="paintool-uptime", daemon=True)
    t.start()

    # Chờ 1 nhịp rất ngắn để chắc chắn bind thành công (không bắt buộc)
    time.sleep(0.2)
    _UPTIME_SERVER_STARTED = True

    try:
        log_event("WEB", detail=f"Web server ẩn đang chạy tại http://0.0.0.0:{port}")
    except Exception:
        pass
    return True

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
        ("1", "Start", "Start"),
        ("2", "Set up", "Set up"),
        ("3", "Package prefix", "Package prefix"),
        ("4", "Change ID", "Change id"),
        ("5", "Set Webhook URL", "Set Webhook URL"),
        ("6", "Xóa cache", "Xóa cache"),
        ("7", "Import auto execute", "Import auto execute"),
        ("8", "Mở tab clone", "Mở tab clone "),
        ("9", "Send Text", "SEND TEXT"),
        ("10", "Backup / Restore", "Backup / Restore data tab"),
        ("11", "Login Cookie Roblox", "Login Cookie Roblox"),
        ("12", "Xem log", "Xem log"),
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
        half = (len(entries) + 1) // 2
        for i in range(half):
            right = cell(entries[i + half], inner - colw, True) if i + half < len(entries) else ""
            print(box_row(pad(cell(entries[i], colw, True), colw) + right, w))
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
    print("\033[1;37m2. Delay rejoin (Hết chu kỳ tự tắt Đa nhiệm rồi vào lại Map)\033[0m")
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
    print("Tự backup dữ liệu (đăng nhập, cài đặt) của các tab đang chạy ổn định. Cần root.")
    print("\033[1;37m1. Bật\033[0m")
    print("\033[1;37m2. Tắt\033[0m")
    print("\033[1;32m0. Quay lại\033[0m")
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
        print("\033[1;37m1. Backup tất cả tab\033[0m")
        print("\033[1;37m2. Restore tất cả tab\033[0m")
        print("\033[1;37m3. Backup 1 tab\033[0m")
        print("\033[1;37m4. Restore 1 tab\033[0m")
        print("\033[1;37m5. Xem danh sách backup\033[0m")
        print("\033[1;32m0. Quay lại menu chính\033[0m")
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

def setup_low_ram():
    global LOW_RAM_ALERT, LOW_RAM_MB, LOW_RAM_AUTO_CLEAN
    clear_screen()
    section_title("CẢNH BÁO RAM THẤP")
    free = get_free_ram_mb()
    print(f"Trạng thái: {'BẬT' if LOW_RAM_ALERT else 'TẮT'} | Ngưỡng: {LOW_RAM_MB} MB | Tự dọn cache: {'BẬT' if LOW_RAM_AUTO_CLEAN else 'TẮT'}")
    print(f"RAM trống hiện tại: {str(free) + ' MB' if free is not None else 'không đọc được'}")
    print("Khi đang Start mà RAM trống dưới ngưỡng: cảnh báo trên màn hình + Discord và tự dọn cache (cần root).")
    print("\033[1;37m1. Bật cảnh báo\033[0m")
    print("\033[1;37m2. Tắt cảnh báo\033[0m")
    print("\033[1;37m3. Đổi ngưỡng RAM (MB)\033[0m")
    print("\033[1;37m4. Bật / Tắt tự dọn cache khi RAM thấp\033[0m")
    print("\033[1;32m0. Quay lại\033[0m")
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
        print("\033[1;37m1. Lưu cấu hình hiện tại thành profile\033[0m")
        print("\033[1;37m2. Nạp profile (đổi nhanh)\033[0m")
        print("\033[1;37m3. Xóa profile\033[0m")
        print("\033[1;32m0. Quay lại\033[0m")
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
        print("\033[1;37m1. Đặt giờ tự chạy (HH:MM)\033[0m")
        print("\033[1;37m2. Đặt giờ tự dừng (HH:MM)\033[0m")
        print("\033[1;37m3. Tắt hẹn giờ\033[0m")
        print("\033[1;32m0. Quay lại\033[0m")
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
    print("\033[1;37m1. Bật\033[0m")
    print("\033[1;37m2. Tắt\033[0m")
    print("\033[1;37m3. Thử kiểm tra mạng ngay\033[0m")
    print("\033[1;32m0. Quay lại\033[0m")
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
    """'low' | 'normal' | None (chưa có file cài đặt)."""
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
        sh(f"cat {shlex.quote(work)} > {shlex.quote(path)}", timeout=15)   # ghi đè tại chỗ, giữ nguyên chủ sở hữu / SELinux
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
    """Báo cáo Discord (kể cả chụp ảnh màn hình 5 phút/lần) chỉ hoạt động khi người dùng đã set URL webhook hợp lệ."""
    url = (WEBHOOK_URL or "").strip()
    return url.lower().startswith(("https://", "http://"))

# ==================== LỊCH TỰ ĐỘNG RESTART ====================
AUTO_RESTART_CHOICES = (2, 3, 4)   # số giờ treo liên tục giữa 2 lần restart
AUTO_RESTART_ACTIONS = {"clean": "Dọn RAM + cache", "reset": "Reset toàn bộ tab (tắt Đa nhiệm + vào lại Map)"}

def auto_restart_label():
    if AUTO_RESTART_HOURS not in AUTO_RESTART_CHOICES:
        return "Tắt"
    return f"Mỗi {AUTO_RESTART_HOURS}h · {'Reset tab' if AUTO_RESTART_ACTION == 'reset' else 'Dọn RAM'}"

def auto_restart_due(last_ts, now=None):
    """Đã treo liên tục đủ AUTO_RESTART_HOURS kể từ lần restart (hoặc Start) gần nhất chưa."""
    if AUTO_RESTART_HOURS not in AUTO_RESTART_CHOICES:
        return False
    now = time.time() if now is None else now
    return (now - last_ts) >= AUTO_RESTART_HOURS * 3600

def clean_cache_all(packages):
    """Xóa cache các tab + dọn RAM (KHÔNG xóa dữ liệu đăng nhập)."""
    for pkg in packages:
        sh(f"rm -rf /data/data/{pkg}/cache/* /data/data/{pkg}/code_cache/*")
    sh("sync && echo 3 > /proc/sys/vm/drop_caches")

def do_auto_restart(packages):
    """Đến hạn: dọn RAM/cache, và nếu chọn 'reset' thì tắt Đa nhiệm toàn bộ tab rồi vào lại Map."""
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
        print("\033[1;37m1. Tắt\033[0m")
        print("\033[1;37m2. Mỗi 2 giờ\033[0m")
        print("\033[1;37m3. Mỗi 3 giờ\033[0m")
        print("\033[1;37m4. Mỗi 4 giờ\033[0m")
        print("\033[1;37m5. Hành động: chỉ dọn RAM + cache\033[0m")
        print("\033[1;37m6. Hành động: reset toàn bộ tab (tắt Đa nhiệm + vào lại Map)\033[0m")
        print("\033[1;32m0. Quay lại\033[0m")
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
    """{'path','low','fps'} hoặc None nếu chưa có file cài đặt."""
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
    """Ghi cài đặt tối ưu vào GlobalBasicSettings_13.xml: low=True -> đồ họa thấp nhất, fps>0 -> FramerateCap.
    Đã đúng cài đặt thì bỏ qua (không tắt tab). Trả về (ok, thông báo)."""
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
    close_game(pkg)   # Roblox ghi đè file cài đặt khi thoát nên phải tắt tab trước
    xml = sh(f"cat {q(path)}", timeout=10)
    if "<Properties" not in xml:
        return False, "file cài đặt không đúng định dạng"
    if "1" not in sh(f"[ -f {q(bak)} ] && echo 1", timeout=5):
        sh(f"cat {q(path)} > {q(bak)}", timeout=10)   # giữ bản gốc để khôi phục
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
    """Khôi phục file cài đặt gốc từ bản sao lưu của tool. Trả về (ok, thông báo)."""
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
    """Bật 'tự áp dụng khi Start': đưa mọi tab về cài đặt tối ưu trước khi mở game (tab đã đúng thì bỏ qua)."""
    if not GFX_AUTO or not (GFX_LOW or GFX_FPS):
        return
    if not root_mode():
        print("\033[1;31m[!] Graphics Optimizer cần root, bỏ qua.\033[0m")
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
    """Graphics Optimizer: đồ họa thấp nhất + giới hạn FPS 15/20/30 cho từng tab clone."""
    global GFX_LOW, GFX_FPS, GFX_AUTO
    while True:
        clear_screen()
        section_title("GRAPHICS OPTIMIZER")
        print(f"Cài đặt: {C.WHT}{gfx_settings_label()}{C.R}   Tự áp dụng khi Start: {C.WHT}{'Bật' if GFX_AUTO else 'Tắt'}{C.R}")
        print(f" {C.GRY}Sửa file {GFX_FILE} của từng tab (cần root). Tab đang chạy sẽ bị tắt để áp dụng.{C.R}")
        print("\033[1;37m1. Áp dụng ngay cho tất cả tab\033[0m")
        print(f"\033[1;37m2. Đồ họa thấp nhất [{'Bật' if GFX_LOW else 'Tắt'}]\033[0m")
        print(f"\033[1;37m3. Giới hạn FPS [{GFX_FPS if GFX_FPS else 'Không giới hạn'}]\033[0m")
        print("\033[1;37m4. Khôi phục cài đặt gốc (tất cả tab)\033[0m")
        print("\033[1;37m5. Xem trạng thái các tab\033[0m")
        print(f"\033[1;37m6. Tự áp dụng khi Start [{'Bật' if GFX_AUTO else 'Tắt'}]\033[0m")
        print("\033[1;32m0. Quay lại\033[0m")
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
LOG_ERROR_KINDS = ("KICK", "CRASH", "FREEZE", "SCREEN", "JOIN_ERR", "REJOIN_FAIL", "LOBBY", "LOW_RAM", "NET_DOWN")
LOG_KIND_COLOR = {
    "KICK": C.RED, "CRASH": C.RED, "FREEZE": C.RED, "JOIN_ERR": C.RED, "REJOIN_FAIL": C.RED,
    "LOBBY": C.YEL, "LOW_RAM": C.YEL, "NET_DOWN": C.YEL, "SCREEN": C.RED, "KEY": C.CYN,
    "REJOIN_OK": C.GRN, "START": C.GRN, "NET_UP": C.GRN,
    "STOP": C.GRY, "HOP": C.CYN, "HOP_FAIL": C.YEL, "HOP_PAUSE": C.YEL, "BLACKSCREEN": C.CYN, "CYCLE": C.CYN, "SCHEDULE": C.CYN, "AUTO_RESTART": C.CYN, "GFX": C.CYN, "GFX_AUTO": C.CYN, "LOW_GFX": C.CYN,
}

def parse_log_line(line):
    """'giờ | LOẠI | package | [code=..] | [rejoin#..] | chi tiết' -> dict."""
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
    """mode: all | errors | pkg | search | session."""
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
    """Ngắt dòng theo độ rộng hiển thị thật (chữ có dấu / emoji)."""
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
    """Danh sách dòng đã tô màu cho 1 mục log (dòng 1: giờ + loại + tab, các dòng sau: chi tiết)."""
    color = LOG_KIND_COLOR.get(e["kind"], C.WHT)
    stamp = e["time"][5:] if len(e["time"]) >= 19 else e["time"]           # MM-DD HH:MM:SS
    head = f"{C.GRY}{stamp}{C.R} {color}{e['kind'] or 'LOG'}{C.R}"
    pkg_line = None
    if e["pkg"]:
        room = width - vlen(stamp) - len(e["kind"] or "LOG") - 2
        if room >= 8:
            head += f" {C.WHT}{clip(tab_label(e['pkg']), room)}{C.R}"
        else:
            pkg_line = f"  {C.WHT}{clip(tab_label(e['pkg']), width - 2)}{C.R}"   # màn hình hẹp: tên tab xuống dòng riêng
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
    """Trang 0 = mới nhất. Trả về (mục trong trang theo thứ tự cũ→mới, tổng số trang, trang đã chỉnh)."""
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
        print("\033[1;37m1. Xem log mới nhất\033[0m")
        print("\033[1;37m2. Chỉ xem lỗi (Kick / Crash / Treo / Lobby / Rejoin thất bại...)\033[0m")
        print("\033[1;37m3. Phiên chạy gần nhất (từ lần Start cuối)\033[0m")
        print("\033[1;37m4. Lọc theo tab\033[0m")
        print("\033[1;37m5. Tìm theo từ khóa / mã lỗi\033[0m")
        print("\033[1;37m6. Xóa toàn bộ log\033[0m")
        print("\033[1;32m0. Quay lại menu chính\033[0m")
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
    """Danh sách (thư mục, tên file, đang bật?). Script bật = *.lua, tắt = *.lua.disabled (executor bỏ qua file này)."""
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
        print("\033[1;37m1. Import script mới\033[0m")
        print("\033[1;37m2. Quản lý script (bật / tắt từng script)\033[0m")
        print("\033[1;32m0. Quay lại menu chính\033[0m")
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

MENU_NAMES = {
    "1": "Start", "2": "Set up", "3": "Package prefix", "4": "Change ID", "5": "Set Webhook URL",
    "6": "Xóa cache", "7": "Import auto execute", "8": "Mở tab clone", "9": "Send Text",
    "10": "Backup / Restore data tab", "11": "Login Cookie Roblox", "12": "Xem log", "0": "Exit",
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
    """Báo ngay cho người dùng biết mục vừa bấm đã được nhận."""
    print(f"\n {C.PUR}›{C.R} {C.WHT}Đã chọn [{key}] {label}{C.R}")
    time.sleep(0.6)

def invalid_choice(text):
    msg_err(f"Lựa chọn '{text or '(trống)'}' không hợp lệ, vui lòng chọn lại.")
    time.sleep(1.2)

def menu_choose_game():
    global TARGET_LINK, SELECTED_GAME_NAME
    clear_screen()
    section_title("CHỌN GAME")
    for k, (name, _gid) in GAMES.items():
        print(f"\033[1;37m{k}. {name}\033[0m")
    print("\033[1;37m12. Custom ID / Private Link\033[0m")
    game_choice = input("Chọn game [1-12]: ").strip()
    if game_choice in GAMES:
        SELECTED_GAME_NAME, TARGET_LINK = GAMES[game_choice]
        save_config_file()
        msg_done(f"Đã chọn và lưu game: {SELECTED_GAME_NAME}")
        print(f" {C.GRY}ID: {TARGET_LINK}{C.R}")
    elif game_choice == "12":
        link = input("Nhập ID game hoặc Link Server VIP: ").strip()
        if link:
            TARGET_LINK = link
            SELECTED_GAME_NAME = f"Game ID: {link}" if link.isdigit() else "Server VIP Custom"
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
        print(f" {C.GRY}Bản sao nằm ở {KEY_VAULT_DIR} (quyền riêng tư), không gửi lên Discord / log. Cần root.{C.R}")
        print(f" {C.GRY}Tự động lưu & chèn: {'BẬT' if KEY_AUTO else 'TẮT'}{C.R}\n")
        if not packages:
            msg_err(f"Không thấy package nào khớp '{PACKAGE_PREFIX}' (đổi ở mục [3] nếu clone đặt tên khác).")
            wait_enter()
            return
        for i, p in enumerate(packages, 1):
            print(f" {C.LPUR}{i:>2}.{C.R} {C.WHT}{clip(tab_label(p), 30)}{C.R} {C.GRY}theo dõi {len(KEY_FILES.get(p, []))} file · vault {len(idx.get(p, {}))} file{C.R}")
        print("\033[1;37m1. Chọn file key cần giữ cho 1 tab (tự quét)\033[0m")
        print("\033[1;37m2. Lưu key vào vault ngay (mọi tab đã chọn)\033[0m")
        print("\033[1;37m3. Chèn key từ vault ngay (ghi đè, tab sẽ bị tắt)\033[0m")
        print("\033[1;37m4. Bật / Tắt tự động lưu & chèn\033[0m")
        print("\033[1;37m5. Xóa vault của 1 tab\033[0m")
        print("\033[1;32m0. Quay lại menu Set up\033[0m")
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
    """Cho người dùng xem tool đọc màn hình từng tab ra sao (để chỉnh ngưỡng nếu cần)."""
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
        print(f" {C.GRY}Quét màn hình mỗi {SCREEN_CHECK_SEC}s khi đang Start (cần root, tự động rejoin ở chế độ 1):{C.R}")
        print(f" {C.GRY}• Trắng/đen kẹt {WB_CONFIRM_COUNT} lần liên tiếp -> kill-process rồi vào lại ngay, không chờ timeout.{C.R}")
        print(f" {C.GRY}• Not Responding (ANR) hoặc khung hình đứng im {OVERLAY_FREEZE_SEC}s + không có log -> kill-process rồi chạy lại.{C.R}")
        print(f" {C.GRY}Hiện tại: {screen_guard_label()}{C.R}\n")
        print(f"\033[1;37m1. Bật / Tắt phát hiện màn hình trắng/đen [{'Bật' if WB_DETECT else 'Tắt'}]\033[0m")
        print(f"\033[1;37m2. Bật / Tắt phát hiện Not Responding / GUI đứng [{'Bật' if OVERLAY_DETECT else 'Tắt'}]\033[0m")
        print("\033[1;37m3. Thử quét ngay (xem tool đọc màn hình từng tab)\033[0m")
        print("\033[1;32m0. Quay lại menu Set up\033[0m")
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

def menu_setup():
    while True:
        clear_screen()
        section_title("SET UP")
        print("\033[1;37m1. Set up auto rejoin\033[0m")
        print("\033[1;37m2. Chọn game\033[0m")
        print(f"\033[1;37m3. Auto Clear Data / Khôi phục tab kẹt [{'Bật' if AUTO_CLEAR_DATA else 'Tắt'}]\033[0m")
        print(f"\033[1;37m4. Auto Backup data tab [{'Bật' if AUTO_BACKUP else 'Tắt'}]\033[0m")
        print(f"\033[1;37m5. Cảnh báo RAM thấp [{'Bật' if LOW_RAM_ALERT else 'Tắt'}]\033[0m")
        print(f"\033[1;37m6. Profile cấu hình [{len(PROFILES)} profile]\033[0m")
        print(f"\033[1;37m7. Hẹn giờ tự chạy / tự dừng [{'Bật' if (SCHEDULE.get('start') or SCHEDULE.get('stop')) else 'Tắt'}]\033[0m")
        print(f"\033[1;37m8. Graphics Optimizer (đồ họa thấp + giới hạn FPS) [{gfx_settings_label()}]\033[0m")
        print(f"\033[1;37m9. Biệt danh tab (Alias) [{len(ALIASES)} tab]\033[0m")
        print(f"\033[1;37m10. Kiểm tra mạng trước khi rejoin [{'Bật' if NET_CHECK else 'Tắt'}]\033[0m")
        print(f"\033[1;37m11. Lịch tự động restart [{auto_restart_label()}]\033[0m")
        print(f"\033[1;37m12. Client Key Injector [{key_label()}]\033[0m")
        print(f"\033[1;37m13. Phát hiện màn hình trắng/đen & GUI đứng [{screen_guard_label()}]\033[0m")
        print(f"\033[1;37m14. Chế độ màn hình đen (Black Screen) [{black_screen_label()}]\033[0m")
        print(f"\033[1;37m15. Auto Server Hop (đổi server khi lag) [{hop_label()}]\033[0m")
        print("\033[1;32m0. Quay lại menu chính\033[0m")
        sub = input("Chọn: ").strip()
        if sub == "1":
            announce_choice("1", "Set up auto rejoin")
            setup_auto_rejoin()
        elif sub == "2":
            announce_choice("2", "Chọn game")
            menu_choose_game()
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
            announce_choice("7", "Hẹn giờ tự chạy / tự dừng")
            menu_schedule()
        elif sub == "8":
            announce_choice("8", "Graphics Optimizer")
            menu_low_graphics()
        elif sub == "9":
            announce_choice("9", "Biệt danh tab")
            menu_alias()
        elif sub == "10":
            announce_choice("10", "Kiểm tra mạng trước khi rejoin")
            setup_net_check()
        elif sub == "11":
            announce_choice("11", "Lịch tự động restart")
            menu_auto_restart()
        elif sub == "12":
            announce_choice("12", "Client Key Injector")
            menu_key_injector()
        elif sub == "13":
            announce_choice("13", "Phát hiện màn hình trắng/đen & GUI đứng")
            menu_screen_guard()
        elif sub == "14":
            announce_choice("14", "Chế độ màn hình đen")
            menu_black_screen()
        elif sub == "15":
            announce_choice("15", "Auto Server Hop")
            menu_server_hop()
        elif sub == "0":
            msg_info("Quay lại menu chính...")
            time.sleep(0.6)
            break
        else:
            invalid_choice(sub)

def menu_package_prefix():
    global PACKAGE_PREFIX
    clear_screen()
    section_title("PACKAGE PREFIX")
    print(f" {C.GRY}Prefix hiện tại:{C.R} {C.WHT}{PACKAGE_PREFIX}{C.R}")
    pref = input("Nhập Package Prefix (Để trống để giữ mặc định): ").strip()
    if pref:
        PACKAGE_PREFIX = pref
        n = len(list_installed_packages())
        save_config_file()
        msg_done(f"Đã cập nhật và lưu Package Prefix: {PACKAGE_PREFIX}")
        if n:
            print(f" {C.GRY}Tìm thấy {n} package khớp prefix này.{C.R}")
        else:
            msg_warn("Chưa tìm thấy package nào khớp prefix này, hãy kiểm tra lại tên.")
    else:
        msg_cancel(f"Giữ nguyên Package Prefix: {PACKAGE_PREFIX}")
    wait_enter()

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
        msg_warn(f"Nhưng máy chưa xác nhận (có thể cần root). ID hiện tại: {current or 'không đọc được'}")
    wait_enter()

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
        msg_done("Đã cập nhật Webhook thành công!")
        print(f" {C.GRY}Webhook: {WEBHOOK_URL[:35]}...{C.R}")
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
    # Chỉ xóa cache (không pm clear) nên không mất đăng nhập. Xóa hẳn data: dùng Backup/Restore hoặc Auto Clear Data.
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
    except:
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

if __name__ == "__main__":
    # Bật Web Server ẩn trước tiên để UptimeRobot ping được ngay
    try:
        start_uptime_server()
    except Exception:
        pass

    load_saved_config()
    restore_screen_if_needed()
    authenticate()
    startup_update_check()
    while True:
        show_banner()
        choice = ask_main("Chọn chức năng [0-12]:").strip()
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
            menu_import_autoexec()
        elif choice == "8":
            menu_open_clones()
        elif choice == "9":
            handle_send_text()
        elif choice == "10":
            backup_menu()
        elif choice == "11":
            cookie_login_menu()
        elif choice == "12":
            menu_view_log()
