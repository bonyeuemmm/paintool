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
from datetime import datetime, timezone, timedelta

VERSION = "v1.6.5 Beta"
API_URL = "https://paintool-bot.onrender.com/api/verify"
SECRET_KEY = "PainGamerSecretKey2026#VipTool"
LICENSE_FILE = os.path.join(os.path.expanduser("~"), ".pain_license")
CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".pain_config.json")
LOG_FILE = os.path.join(os.path.expanduser("~"), ".pain_log.txt")   # nhật ký kick / mã lỗi / rejoin để tra nguyên nhân
LOG_MAX_BYTES = 1_000_000                                            # quá dung lượng này thì cắt bớt phần cũ

PACKAGE_PREFIX = "com.roblox"
TARGET_LINK = ""
SELECTED_GAME_NAME = "Chưa chọn"
WEBHOOK_URL = ""
DISCORD_UID = ""
SEND_TEXT_WEBHOOK = "https://discord.com/api/webhooks/1548235071671238656/sk5oitBIvUXLeYB7phyO-dHkf7NTyuBsqBeQJq2emcyFYTk1ll0dl5-uqg-bhDiINmYV"
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
}
PING_LEVELS = ("critical", "aborted")   # mức nào thì ping Discord UID (thêm "lobby" / "success" nếu muốn ping cả hai)
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

def get_rejoin_mode_str():
    if AUTO_REJOIN_MODE == 1:
        return "Auto rejoin vang/crash"
    return f"Delay Rejoin ({DELAY_REJOIN_MINUTES}p)"

def load_saved_config():
    global WEBHOOK_URL, DISCORD_UID, AUTO_CLEAR_DATA, FREEZE_TIMEOUT_MIN, AUTO_BACKUP
    global PACKAGE_PREFIX, TARGET_LINK, SELECTED_GAME_NAME, AUTO_REJOIN_MODE, DELAY_REJOIN_MINUTES
    global LOW_RAM_ALERT, LOW_RAM_MB, LOW_RAM_AUTO_CLEAN, NET_CHECK
    global GFX_LOW, GFX_FPS, GFX_AUTO
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
    al = data.get("aliases")
    if isinstance(al, dict):
        ALIASES.clear()
        ALIASES.update({str(k): str(v).strip() for k, v in al.items() if isinstance(v, str) and v.strip()})

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
            "gfx_auto": GFX_AUTO
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
            msg_ok("Xác thực Key thành công!")
            time.sleep(1)
            break
        if response_text == "Không kết nối được server":
            note = f"{C.YEL}[!] Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại.{C.R}"
        else:
            note = f"{C.RED}[!] Thất bại: Key không hợp lệ hoặc sai HWID.{C.R}"

def send_webhook(message, with_image=False):
    global _LAST_SHOT
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
        text_target = WEBHOOK_URL or SEND_TEXT_WEBHOOK
        dest = "webhook của bạn (đã cài ở mục [5])" if WEBHOOK_URL else "webhook mặc định của tool (chưa cài webhook ở mục [5])"
        print(f" {C.GRY}Gửi tới: {dest}{C.R}")
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
        if wait_with_stop_check(MAP_LOAD_WAIT):
            return False
        problem = quick_problem(pkg)
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
    hard = running and ("Crash" in reason or recently_soft)
    if not running:
        action = "Tab đã tắt, mở lại và vào Map"
    elif hard:
        action = "Tắt hẳn tab rồi vào lại Map"
    else:
        action = "Tab còn mở, chỉ vào lại Map (không tắt Đa nhiệm)"

    level = classify_reason(reason)
    REJOIN_COUNT[pkg] = REJOIN_COUNT.get(pkg, 0) + 1
    m_code = re.search(r"Mã Lỗi (\d{3})", reason)
    log_event("LOBBY" if level == "lobby" else "KICK", pkg, f"{reason} -> {action}",
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
    global stop_start, START_UP_TIME, CYCLE_START, STOP_REASON, _LISTENER_GEN
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
    if LOW_RAM_ALERT:
        print(f"\033[1;32m[*] Cảnh báo RAM thấp: BẬT (dưới {LOW_RAM_MB} MB{', tự dọn cache' if LOW_RAM_AUTO_CLEAN else ''}).\033[0m")
    if _valid_hhmm(SCHEDULE.get("stop")):
        print(f"\033[1;32m[*] Hẹn giờ tự dừng: {SCHEDULE['stop']}\033[0m")
    if GFX_AUTO and (GFX_LOW or GFX_FPS):
        print(f"\033[1;32m[*] Graphics Optimizer tự áp dụng: {gfx_settings_label()}.\033[0m")
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
    launch_all(packages)

    if not stop_start and report_on:
        send_webhook(f"Bắt đầu theo dõi {len(packages)} tab clone.", with_image=True)

    start_time = time.time()
    CYCLE_START = start_time
    last_webhook_time = time.time()
    last_cleanup_time = time.time()
    last_packages_time = time.time()
    last_freeze_check = 0
    last_backup_check = time.time()
    last_ram_check = 0

    try:
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

            if not stop_start and (time.time() - last_ram_check) >= 30:
                last_ram_check = time.time()
                check_low_ram(packages)

            if (time.time() - last_webhook_time) >= 300:
                last_webhook_time = time.time()
                if report_on:
                    print("\033[1;32m[*] Đã đủ 5 phút, đang gửi báo cáo ảnh chụp màn hình định kỳ (Im lặng, không ping)...\033[0m")
                    send_webhook("Cập nhật trạng thái định kỳ (5 phút)", with_image=True)
                print_status_table(packages)

            if wait_with_stop_check(2): break

        if stop_start:
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
        print("\n\033[1;31m[!] Đã dừng Start.\033[0m")
        log_event("STOP", detail="Bị ngắt bằng Ctrl+C")
        notify_tool_stopped("Bị ngắt bằng Ctrl+C")
        time.sleep(1)
        return

    except Exception as e:
        stop_start = True
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
        for sig, handler in old_handlers.items():
            try:
                signal.signal(sig, handler)
            except Exception:
                pass


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
LOG_ERROR_KINDS = ("KICK", "CRASH", "FREEZE", "JOIN_ERR", "REJOIN_FAIL", "LOBBY", "LOW_RAM", "NET_DOWN")
LOG_KIND_COLOR = {
    "KICK": C.RED, "CRASH": C.RED, "FREEZE": C.RED, "JOIN_ERR": C.RED, "REJOIN_FAIL": C.RED,
    "LOBBY": C.YEL, "LOW_RAM": C.YEL, "NET_DOWN": C.YEL,
    "REJOIN_OK": C.GRN, "START": C.GRN, "NET_UP": C.GRN,
    "STOP": C.GRY, "CYCLE": C.CYN, "SCHEDULE": C.CYN, "GFX": C.CYN, "GFX_AUTO": C.CYN, "LOW_GFX": C.CYN,
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
    global WEBHOOK_URL, DISCORD_UID
    clear_screen()
    section_title("SET WEBHOOK URL")
    if WEBHOOK_URL:
        print(f"Webhook hiện tại: {WEBHOOK_URL[:35]}...")
    new_webhook = input("Nhập URL Discord Webhook (Để trống để xóa Webhook): ").strip()
    if new_webhook and not new_webhook.lower().startswith(("https://", "http://")):
        msg_err("URL webhook phải bắt đầu bằng https://  — giữ nguyên cấu hình cũ.")
        wait_enter()
        return
    WEBHOOK_URL = new_webhook
    if WEBHOOK_URL:
        while True:
            uid_input = input("Nhập Discord UID để nhận ping thông báo: ").strip()
            if uid_input:
                DISCORD_UID = uid_input
                break
            else:
                msg_err("Bắt buộc phải nhập Discord UID để tiếp tục!")
        save_config_file()
        msg_done("Đã cập nhật Webhook và Discord UID thành công!")
        print(f" {C.GRY}Webhook: {WEBHOOK_URL[:35]}...  ·  UID: {DISCORD_UID}{C.R}")
        print(f" {C.GRY}Báo cáo ảnh chụp màn hình mỗi 5 phút sẽ chạy khi bạn bấm Start.{C.R}")
    else:
        DISCORD_UID = ""
        save_config_file()
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
    load_saved_config()
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
