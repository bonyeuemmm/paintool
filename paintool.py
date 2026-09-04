import os
import sys
import time
import subprocess
import requests
import json

API_URL = "https://discord-license-bot-production.up.railway.app/api/verify"
LICENSE_FILE = os.path.join(os.path.expanduser("~"), ".pain_license")

PACKAGE_NAME = "com.roblox.client"
TARGET_LINK = ""
WEBHOOK_URL = ""
ROBLOX_CREDENTIALS = ""
AUTO_REJOIN = 1
DELAY_MINUTES = 1
WEBHOOK_INTERVAL = 1
SCREENSHOT_PATH = "/sdcard/pain_screenshot.png"

def get_hwid():
    hwid = ""
    try:
        hwid = subprocess.check_output(["settings", "get", "secure", "android_id"]).decode().strip()
    except Exception:
        pass

    if not hwid or hwid == "null":
        try:
            hwid = subprocess.check_output(["getprop", "ro.serialno"]).decode().strip()
        except Exception:
            pass

    if not hwid or hwid == "null":
        hwid = "android_default_hwid"
        
    return hwid

def authenticate():
    global LICENSE_FILE
    input_key = ""
    hwid = get_hwid()

    if os.path.exists(LICENSE_FILE):
        with open(LICENSE_FILE, "r") as f:
            input_key = f.read().strip()
        
        if input_key:
            print("\033[1;35m[*] Checking saved license...\033[0m")
            try:
                payload = {"key": input_key, "hwid": hwid}
                res = requests.post(API_URL, json=payload, timeout=10)
                
                try:
                    data = res.json()
                    is_valid = data.get("valid") is True or data.get("status") == "success"
                except Exception:
                    is_valid = '"valid":true' in res.text.replace(" ", "")

                if is_valid:
                    print("\033[1;37m[+] Automatic license verification successful!\033[0m")
                    time.sleep(1)
                    return
                else:
                    print("\033[1;33m[!] Saved key is invalid, expired, or HWID mismatched.\033[0m")
                    if os.path.exists(LICENSE_FILE):
                        os.remove(LICENSE_FILE)
            except Exception:
                pass

    while True:
        os.system('clear')
        print("\033[1;35m==================================================\033[0m")
        print("\033[1;37m          PAIN TOOL REJOIN VIP - AUTH             \033[0m")
        print("\033[1;35m==================================================\033[0m")
        print(f"\033[1;36m Current HWID: {hwid}\033[0m")
        print("\033[1;37m[!] Please enter Tool Key (pain_key_...) to continue.\033[0m")
        print("\033[1;35m(Type 'exit' or '0' to quit)\033[0m")
        print("\033[1;35m==================================================\033[0m")
        input_key = input("Enter Key: ").strip()
        
        if input_key == "exit" or input_key == "0":
            print("\033[1;31mExited program. Goodbye!\033[0m")
            sys.exit(0)

        if not input_key:
            continue

        print("\033[1;35m[*] Connecting to server to verify key...\033[0m")
        try:
            payload = {"key": input_key, "hwid": hwid}
            res = requests.post(API_URL, json=payload, timeout=10)
            
            try:
                data = res.json()
                is_valid = data.get("valid") is True or data.get("status") == "success"
            except Exception:
                is_valid = '"valid":true' in res.text.replace(" ", "")

            if is_valid:
                try:
                    with open(LICENSE_FILE, "w") as f:
                        f.write(input_key)
                except Exception as write_err:
                    print(f"\033[1;33m[!] Warning: Could not save license locally ({write_err})\033[0m")

                print("\033[1;37m[+] License verification successful! Device locked.\033[0m")
                time.sleep(1.5)
                break
            else:
                print(f"\033[1;31m[!] Failed: Invalid key or HWID mismatch.\033[0m")
                print(f"\033[1;33m[*] Server response: {res.text.strip()}\033[0m")
                time.sleep(3)
        except Exception as e:
            print(f"\033[1;31m[!] Connection error: {e}\033[0m")
            time.sleep(2)

def show_banner():
    os.system('clear')
    target_display = TARGET_LINK if TARGET_LINK else "Not Set (Normal Rejoin/Blox Fruit Lobby)"
    webhook_display = WEBHOOK_URL if WEBHOOK_URL else "Not Set"
    creds_display = "Not Set" if not ROBLOX_CREDENTIALS else "Configured (*)"
    auto_rejoin_display = "Enabled" if AUTO_REJOIN == 1 else "Disabled"
    
    print("\033[1;35m==================================================\033[0m")
    print("\033[1;37m             PAIN TOOL REJOIN VIP                 \033[0m")
    print("\033[1;35m==================================================\033[0m")
    print(f"\033[1;35m Package Name    :\033[0m \033[1;37m{PACKAGE_NAME}\033[0m")
    print(f"\033[1;35m Target ID/Link  :\033[0m \033[1;37m{target_display}\033[0m")
    print(f"\033[1;35m Webhook URL     :\033[0m \033[1;37m{webhook_display}\033[0m")
    print(f"\033[1;35m Webhook Interval:\033[0m \033[1;37mEvery {WEBHOOK_INTERVAL} minute(s)\033[0m")
    print(f"\033[1;35m Roblox Creds    :\033[0m \033[1;37m{creds_display}\033[0m")
    print(f"\033[1;35m Auto Rejoin     :\033[0m \033[1;37m{auto_rejoin_display}\033[0m")
    print(f"\033[1;35m Delay Time      :\033[0m \033[1;37m{DELAY_MINUTES} minute(s)\033[0m")
    print("\033[1;35m==================================================\033[0m")
    print("\033[1;35m[1]\033[0m \033[1;37mStart\033[0m")
    print("\033[1;35m[2]\033[0m \033[1;37mSet up\033[0m")
    print("\033[1;35m[3]\033[0m \033[1;37mPackage name\033[0m")
    print("\033[1;35m[4]\033[0m \033[1;37mID/Link private\033[0m")
    print("\033[1;35m[5]\033[0m \033[1;37mUrl webhook\033[0m")
    print("\033[1;35m[6]\033[0m \033[1;37mLogin cookie roblox\033[0m")
    print("\033[1;31m[7] Exit\033[0m")
    print("\033[1;35m==================================================\033[0m")

def send_webhook_with_image(message):
    if WEBHOOK_URL:
        try:
            subprocess.run(["screencap", "-p", SCREENSHOT_PATH], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(SCREENSHOT_PATH):
                with open(SCREENSHOT_PATH, "rb") as f:
                    files = {"file": f}
                    payload = {"payload_json": json.dumps({"content": message})}
                    requests.post(WEBHOOK_URL, data=payload, files=files)
            else:
                requests.post(WEBHOOK_URL, json={"content": message})
        except Exception:
            pass

def start_tool():
    if not PACKAGE_NAME:
        print("\033[1;31m[!] Error: Package name is not set!\033[0m")
        time.sleep(2)
        return

    if AUTO_REJOIN == 0:
        print("\033[1;31m[!] Auto Rejoin is currently disabled in [2] Set up!\033[0m")
        time.sleep(2)
        return

    os.system('clear')
    print("\033[1;37m[+] PAIN TOOL REJOIN VIP is running...\033[0m")
    print("\033[1;35m[*] Press Ctrl+C to stop and return to menu.\033[0m")
    
    if ROBLOX_CREDENTIALS:
        print("\033[1;37m[+] Roblox credentials loaded for session context.\033[0m")

    send_webhook_with_image(f"[PAIN TOOL] Tool started monitoring Roblox. Periodic screenshot interval: {WEBHOOK_INTERVAL} minute(s).")

    sleep_seconds = DELAY_MINUTES * 60
    interval_seconds = WEBHOOK_INTERVAL * 60
    elapsed_time = 0

    try:
        while True:
            pid_res = subprocess.run(["pidof", PACKAGE_NAME], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            pid = pid_res.stdout.decode().strip()
            
            if not pid:
                print("\033[1;31m[-] Roblox closed or kicked. Reopening...\033[0m")
                send_webhook_with_image("[PAIN TOOL] Roblox was closed or kicked! Reopening game and capturing screen:")
                if TARGET_LINK:
                    subprocess.run(["am", "start", "-a", "android.intent.action.VIEW", "-d", TARGET_LINK, PACKAGE_NAME])
                else:
                    subprocess.run(["am", "start", "-n", f"{PACKAGE_NAME}/.MainActivity"])
                time.sleep(10)
                elapsed_time = 0
            else:
                logcat_res = subprocess.run(["logcat", "-d", "-s", "Unity:V", "AndroidRuntime:E"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                log_output = logcat_res.stdout.decode()
                
                if any(keyword in log_output.lower() for keyword in ['disconnect', 'kicked', 'lost connection']):
                    print("\033[1;33m[-] Connection lost detected. Rejoining...\033[0m")
                    send_webhook_with_image("[PAIN TOOL] Connection lost detected! Rejoining game and capturing screen:")
                    subprocess.run(["am", "force-stop", PACKAGE_NAME])
                    time.sleep(2)
                    
                    if TARGET_LINK:
                        subprocess.run(["am", "start", "-a", "android.intent.action.VIEW", "-d", TARGET_LINK, PACKAGE_NAME])
                    else:
                        subprocess.run(["am", "start", "-n", f"{PACKAGE_NAME}/.MainActivity"])
                    time.sleep(10)
                    elapsed_time = 0
            
            subprocess.run(["logcat", "-c"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            elapsed_time += sleep_seconds
            if elapsed_time >= interval_seconds:
                send_webhook_with_image(f"[PAIN TOOL] Periodic status update ({WEBHOOK_INTERVAL} min interval):")
                elapsed_time = 0

            time.sleep(sleep_seconds)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    authenticate()

    while True:
        show_banner()
        choice = input("Select an option [1-7]: ").strip()
        
        if choice == "1":
            start_tool()
        elif choice == "2":
            while True:
                os.system('clear')
                auto_status = "Enabled" if AUTO_REJOIN == 1 else "Disabled"
                print("\033[1;35m=== SET UP CONFIGURATION ===\033[0m")
                print(f"\033[1;37m1. Auto Rejoin (Current: {auto_status})\033[0m")
                print(f"\033[1;37m2. Delay check time (Current: {DELAY_MINUTES} minute(s))\033[0m")
                print(f"\033[1;37m3. Webhook interval (Current: {WEBHOOK_INTERVAL} minute(s))\033[0m")
                print("\033[1;35m4. Back to main menu\033[0m")
                print("\033[1;35m==================================================\033[0m")
                sub_choice = input("Select sub-option [1-4]: ").strip()
                
                if sub_choice == "1":
                    os.system('clear')
                    print("\033[1;35m=== AUTO REJOIN SETTING ===\033[0m")
                    print("\033[1;37m1. Enable Auto Rejoin\033[0m")
                    print("\033[1;37m0. Disable Auto Rejoin\033[0m")
                    toggle_val = input("Choose option [1/0]: ").strip()
                    if toggle_val in ["1", "0"]:
                        AUTO_REJOIN = int(toggle_val)
                        print("\033[1;37m[+] Auto Rejoin updated successfully!\033[0m")
                    else:
                        print("\033[1;31m[!] Invalid selection.\033[0m")
                    time.sleep(2)
                elif sub_choice == "2":
                    os.system('clear')
                    print("\033[1;35m=== DELAY CHECK TIME SETTING (MINUTES) ===\033[0m")
                    input_min = input("Enter check delay time in minutes: ").strip()
                    if input_min.isdigit() and int(input_min) > 0:
                        DELAY_MINUTES = int(input_min)
                        print(f"\033[1;37m[+] Check delay updated to {DELAY_MINUTES} minute(s)!\033[0m")
                    else:
                        print("\033[1;31m[!] Invalid number.\033[0m")
                    time.sleep(2)
                elif sub_choice == "3":
                    os.system('clear')
                    print("\033[1;35m=== WEBHOOK INTERVAL SETTING (MINUTES) ===\033[0m")
                    input_interval = input("Enter interval time in minutes for sending screenshot: ").strip()
                    if input_interval.isdigit() and int(input_interval) > 0:
                        WEBHOOK_INTERVAL = int(input_interval)
                        print(f"\033[1;37m[+] Webhook interval updated to every {WEBHOOK_INTERVAL} minute(s)!\033[0m")
                    else:
                        print("\033[1;31m[!] Invalid number.\033[0m")
                    time.sleep(2)
                elif sub_choice == "4":
                    break
                else:
                    print("\033[1;31m[!] Invalid option.\033[0m")
                    time.sleep(2)
        elif choice == "3":
            while True:
                os.system('clear')
                print("\033[1;35m=== PACKAGE NAME SETTING ===\033[0m")
                print(f"\033[1;37mCurrent package: {PACKAGE_NAME}\033[0m")
                print("\033[1;35m[1]\033[0m \033[1;37mChange package name\033[0m")
                print("\033[1;35m[2]\033[0m \033[1;37mBack to main menu\033[0m")
                print("\033[1;35m==================================================\033[0m")
                pkg_choice = input("Select option [1-2]: ").strip()
                
                if pkg_choice == "1":
                    os.system('clear')
                    print("\033[1;35m=== ENTER NEW PACKAGE NAME ===\033[0m")
                    input_pkg = input("Enter package name (e.g. com.roblox.client): ").strip()
                    if input_pkg:
                        PACKAGE_NAME = input_pkg
                        print(f"\033[1;37m[+] Package name updated to: {PACKAGE_NAME}\033[0m")
                    else:
                        print("\033[1;31m[!] Package name cannot be empty.\033[0m")
                    time.sleep(2)
                elif pkg_choice == "2":
                    break
                else:
                    print("\033[1;31m[!] Invalid option.\033[0m")
                    time.sleep(2)
        elif choice == "4":
            os.system('clear')
            print("\033[1;35m=== ID / LINK PRIVATE SETTING ===\033[0m")
            print("\033[1;37mDefault preset available: Type 'blox' for Blox Fruit\033[0m")
            print(f"\033[1;37mCurrent Target: {TARGET_LINK if TARGET_LINK else 'None'}\033[0m\n")
            input_link = input("Enter Game ID / Private Server Link (leave blank to clear): ").strip()
            
            if input_link.lower() == "blox" or input_link.lower() == "blox fruit":
                TARGET_LINK = "https://www.roblox.com/games/9968396843/Blox-Fruits"
                print("\033[1;37m[+] Preset Blox Fruit loaded successfully!\033[0m")
            else:
                TARGET_LINK = input_link
                if TARGET_LINK:
                    print("\033[1;37m[+] Custom Private ID/Link updated successfully!\033[0m")
                else:
                    print("\033[1;33m[-] Target link cleared.\033[0m")
            time.sleep(2)
        elif choice == "5":
            os.system('clear')
            print("\033[1;35m=== WEBHOOK URL SETTING ===\033[0m")
            print(f"\033[1;37mCurrent Webhook: {WEBHOOK_URL if WEBHOOK_URL else 'None'}\033[0m\n")
            input_webhook = input("Enter Discord Webhook URL (leave blank to clear): ").strip()
            WEBHOOK_URL = input_webhook
            if WEBHOOK_URL:
                print("\033[1;37m[+] Webhook URL updated successfully!\033[0m")
            else:
                print("\033[1;33m[-] Webhook cleared.\033[0m")
            time.sleep(2)
        elif choice == "6":
            os.system('clear')
            print("\033[1;35m=== LOGIN COOKIE ROBLOX ===\033[0m")
            input_creds = input("Enter info (username|password|cookie): ").strip()
            if input_creds:
                input_custom_pkg = input("Enter roblox package name: ").strip()
                if not input_custom_pkg:
                    input_custom_pkg = "com.roblox.client"
                ROBLOX_CREDENTIALS = input_creds
                PACKAGE_NAME = input_custom_pkg
                print(f"\033[1;37m[+] Logging into Roblox with package {PACKAGE_NAME}...\033[0m")
                subprocess.run(["am", "start", "-n", f"{PACKAGE_NAME}/.MainActivity"])
                time.sleep(3)
                print("\033[1;37m[+] Configured and started application successfully!\033[0m")
            else:
                ROBLOX_CREDENTIALS = ""
                print("\033[1;33m[-] Login configuration cancelled.\033[0m")
            time.sleep(2)
        elif choice == "7":
            print("\033[1;31mExiting tool. Goodbye!\033[0m")
            sys.exit(0)
        else:
            print("\033[1;31m[!] Invalid option, please choose from 1 to 7.\033[0m")
            time.sleep(2)