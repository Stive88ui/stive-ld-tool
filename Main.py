print("### RUNNING NEW MAIN (MULTI LD PARALLEL) ###")

import uiautomator2 as u2
import time
import random
import requests
import subprocess
import sys
import threading
import msvcrt
import os
import __main__
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import API_KEY, BASE_URL, SERVICE_CODE
from rich.progress import Progress, SpinnerColumn, TextColumn

# ====== Rich UI ======
from rich.console import Console
from rich.panel import Panel
from rich.align import Align
from rich.text import Text
from rich.table import Table
from rich.live import Live

console = Console()

# ====== ตั้งค่า path adb ของ LDPlayer ======
ADB_PATH = r"C:\LDPlayer\LDPlayer9\adb.exe"   # แก้ให้ตรงเครื่องคุณ

GLOBAL_TIMEOUT = 40
RETRY_INTERVAL = 0.5
CANCEL_EVENT = threading.Event()

# ---------- REAL-TIME STATUS ----------
STATUS_LOCK = threading.Lock()
DEVICE_STATUS = {}  # serial -> {"state": str, "detail": str, "last": float}


# ---------- ฟังก์ชันรีสตาร์ท ----------
def fancy_restart():
    import os, sys, subprocess, time

    clear_screen()
    console.print("[bold yellow]Restarting program...[/bold yellow]")
    time.sleep(0.8)

    # path python + script จริง
    python = sys.executable
    script = os.path.abspath(__file__)

    # เปิดตัวใหม่ก่อน
    subprocess.Popen([python, script], close_fds=True)

    # ปิดโปรแกรมปัจจุบันทันที (ฆ่าทุก thread)
    os._exit(0)
 

    # Loading Animation
    with Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("[bold green]{task.description}"),
        console=console
    ) as progress:

        task = progress.add_task("Saving state...", total=None)
        time.sleep(1.2)

        progress.update(task, description="Clearing cache...")
        time.sleep(1.2)

        progress.update(task, description="Reloading core modules...")
        time.sleep(1.2)

        progress.update(task, description="Reinitializing engine...")
        time.sleep(1.2)

    console.print("\n[bold bright_green]✔ Restarting now...[/bold bright_green]")
    time.sleep(1)

    os.execl(sys.executable, sys.executable, *sys.argv)

def clear_screen():
    os.system("cls")

def set_status(serial, state, detail=""):
    with STATUS_LOCK:
        DEVICE_STATUS.setdefault(serial, {})
        DEVICE_STATUS[serial]["state"] = state
        DEVICE_STATUS[serial]["detail"] = detail
        DEVICE_STATUS[serial]["last"] = time.time()

def build_status_table():
    table = Table(title="📊 LD Real-time Status", show_lines=True)
    table.add_column("Device", style="cyan", no_wrap=True)
    table.add_column("State", style="green")
    table.add_column("Detail", style="yellow")
    table.add_column("Last Update", style="magenta")

    with STATUS_LOCK:
        for serial, info in DEVICE_STATUS.items():
            last = time.strftime("%H:%M:%S", time.localtime(info.get("last", time.time())))
            state = info.get("state", "-")

            # กำหนดสีตามสถานะ
            state_style = "green"
            if state in ["ERROR", "ผิดพลาด"]:
                state_style = "red"
            elif state in ["ยกเลิก"]:
                state_style = "bright_red"
            elif state in ["DONE", "เสร็จสิ้น"]:
                state_style = "bright_green"
            elif state in ["WAIT OTP", "รอระบบ", "สแกน", "กำลังลบ", "ตรวจสอบ"]:
                state_style = "yellow"

            table.add_row(
                serial,
                f"[{state_style}]{state}[/{state_style}]",
                info.get("detail", ""),
                last
            )
    return table


def status_ui_loop(stop_event):
    with Live(build_status_table(), refresh_per_second=2, console=console) as live:
        while not stop_event.is_set():
            live.update(build_status_table())
            time.sleep(0.5)

# ---------- LOG ----------
def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

# ---------- BANNER ----------
def show_banner(title, subtitle):
    ascii_logo = r"""
███████╗████████╗██╗██╗   ██╗███████╗ █████╗  █████╗ 
██╔════╝╚══██╔══╝██║██║   ██║██╔════╝██╔══██╗██╔══██╗
███████╗   ██║   ██║██║   ██║█████╗  ╚█████╔╝╚█████╔╝
╚════██║   ██║   ██║╚██╗ ██╔╝██╔══╝  ██╔══██╗██╔══██╗
███████║   ██║   ██║ ╚████╔╝ ███████╗╚█████╔╝╚█████╔╝
╚══════╝   ╚═╝   ╚═╝  ╚═══╝  ╚══════╝ ╚════╝  ╚════╝
"""
    text = Text()
    text.append(ascii_logo, style="bold cyan")
    text.append(f"\n{title}\n", style="bold green")
    text.append(f"{subtitle}\n", style="yellow")
    text.append("\nDeveloped with ❤️  by Stive88", style="bold magenta")
    console.print(Panel(Align.center(text), border_style="cyan", padding=(1,4)))

# ---------- Utils ----------
def get_devices():
    try:
        result = subprocess.check_output([ADB_PATH, "devices"]).decode("utf-8", errors="ignore")
    except Exception as e:
        log(f"ADB error: {e}")
        return []

    lines = result.strip().split("\n")[1:]
    devices = []
    for line in lines:
        if "device" in line and "offline" not in line:
            serial = line.split()[0]
            devices.append(serial)
    return devices

def open_app(serial, pkg, act):
    cmd = [ADB_PATH, "-s", serial, "shell", "am", "start", "-W", "-n", f"{pkg}/{act}"]
    subprocess.run(cmd, capture_output=True, text=True)
    time.sleep(5)

def open_line(serial):
    set_status(serial, "OPEN", "Opening LINE")
    open_app(serial, "jp.naver.line.android", ".activity.SplashActivity")

def open_contacts(d, serial):
    set_status(serial, "เปิดแอป", "พยายามเปิด Contacts ระบบ (ไอคอนฟ้า-ขาว)")

    # candidates ของ Contacts ระบบจริง
    candidates = [
        "com.google.android.contacts/com.android.contacts.activities.PeopleActivity",
        "com.android.contacts/com.android.contacts.activities.PeopleActivity",
        "com.google.android.contacts/.activities.PeopleActivity",
        "com.android.contacts/.activities.PeopleActivity",
    ]

    opened = False

    for comp in candidates:
        set_status(serial, "เปิดแอป", f"ลองเปิด {comp}")
        cmd = [ADB_PATH, "-s", serial, "shell", "am", "start", "-W", "-n", comp]
        subprocess.run(cmd, capture_output=True, text=True)
        time.sleep(3)

        try:
            # เช็กว่าหน้าจอเป็น Contacts จริงไหม
            # โดยดูว่ามี list รายชื่อ หรือปุ่ม + เพิ่มรายชื่อ
            if d(resourceIdMatches=".*contacts.*").exists(timeout=3) or \
               d(descriptionContains="เพิ่ม").exists(timeout=3) or \
               d(textContains="รายชื่อ").exists(timeout=3):

                opened = True
                break
        except:
            pass

    if not opened:
        set_status(serial, "ผิดพลาด", "ยังเข้า Contacts ระบบไม่ได้ (อาจโดน LD hijack)")
    else:
        set_status(serial, "สำเร็จ", "เข้า Contacts ระบบ (ไอคอนฟ้า-ขาว) แล้ว")



# ---------- FLOW CONTROL ----------
class RestartFlow(Exception):
    pass

def is_back_to_register(d):
    keywords = ["สมัครใช้งาน", "Welcome", "เข้าสู่ระบบ"]
    try:
        for k in keywords:
            if d(textContains=k).exists(timeout=0.2):
                return True
    except:
        pass
    return False

def guard_check(d, serial):
    if is_back_to_register(d):
        set_status(serial, "RESTART", "Back to register detected")
        raise RestartFlow()

# ---------- ADVANCED NAME GENERATOR ----------
USED_NAMES = set()
USED_PROFILE_INDEX = {}   # serial -> set(index)

THAI_NAMES = [
    "มีนา","มินนี่","มินท์","มายด์","เมย์","โมจิ","มิ้ว","มิว","มิ้น",
    "นานา","นุ่น","น้ำ","เนย","นิดา","นิว","ใบเฟิร์น","ฟ้า","ฝน",
    "แพรว","แพร","พลอย","พิม","พริม","ปัน","แป้ง","ปิ่น","เบล","บีม",
    "โบว์","บัว","โบนัส","เฟิร์น","ฟาง","ลิน","ลิลลี่","ลูกแก้ว","ลูกน้ำ",
    "แยม","ยิ้ม","ออย","อิง","ออม","อาย","ไอซ์","ไอด้า","ไอริน","เอม","เอมมี่","อันนา"
]

JP_PREFIX = ["Mi","Me","Na","No","Sa","Shi","Yu","Ya","Ka","Ki","Ko","A","E","I","O","U","Ri","Ra","Re","Ru","Hana","Momo","Yuki","Sora","Ami","Emi"]
JP_SUFFIX = ["mi","na","ko","ka","ra","ri","ru","ne","no","yo","ya","chi","rin","chan"]

KR_PREFIX = ["Ji","Min","Seo","Su","Ha","Na","Ye","Yu","Da","Ara","Bo","Chae","Eun","Hye","Jae","So","Yeon","Yoon","Rin","Ri"]
KR_SUFFIX = ["ah","a","i","in","na","ye","ri","rin","soo","mi","eun","yeon","ra","ha"]

EN_PREFIX = ["Mi","Me","May","Na","Ne","Ni","Li","Lu","La","Ka","Ke","Ki","Sa","Se","Si","Ta","Te","Ti","El","Em","An","Al","Be","Bi","Bo","Cha","Chi","Ri","Ra"]
EN_MIDDLE = ["la","li","lu","ra","ri","na","ni","ma","mi","ka","ki","sa","si","ta","ti","ya","yo","yu","lyn","rin","mel","mir"]
EN_SUFFIX = ["a","i","y","ie","ee","e","lyn","lee","ly","rin","rose","mint","mii"]

SYMBOLS = ["<", ">", "/", "!", "@", "#", "'", "\"", "_", "-", ".", "~", "*"]
EMOJIS = ["✨","🌸","🌷","🌼","💖","💕","💫","⭐","🌈","🍓","🍒","🐰","🐱","🦄","🎀","🫶","💐","☁️","🌙"]

def gen_jp_name():
    return random.choice(JP_PREFIX) + random.choice(JP_SUFFIX)

def gen_kr_name():
    return random.choice(KR_PREFIX) + random.choice(KR_SUFFIX)

def gen_en_name():
    parts = [random.choice(EN_PREFIX), random.choice(EN_MIDDLE), random.choice(EN_SUFFIX)]
    return "".join(parts).capitalize()

def gen_th_name():
    return random.choice(THAI_NAMES)

def get_unique_mixed_name():
    global USED_NAMES
    for _ in range(3000):
        style = random.choice(["TH", "JP", "KR", "EN"])
        if style == "TH":
            base = gen_th_name()
        elif style == "JP":
            base = gen_jp_name()
        elif style == "KR":
            base = gen_kr_name()
        else:
            base = gen_en_name()

        sym_count = random.choice([0,1,2])
        syms = "".join(random.sample(SYMBOLS, sym_count))
        emoji = random.choice(EMOJIS + [""])

        styles = [
            f"{base}{syms}{emoji}",
            f"{emoji}{base}{syms}",
            f"{base}{emoji}{syms}",
            f"{syms}{base}{emoji}",
            f"{base}_{emoji}",
            f"{base}.{syms}{emoji}",
        ]

        final_name = random.choice(styles)
        if final_name not in USED_NAMES:
            USED_NAMES.add(final_name)
            return final_name

    fallback = f"{gen_en_name()}{random.randint(1000,9999)}"
    USED_NAMES.add(fallback)
    return fallback

# ---------- API ----------
# ================= FAST INPUT =================
def fast_set_text(d, text, **kwargs):
    try:
        obj = d(**kwargs)
        if obj.exists(timeout=5):
            obj.click()
            obj.clear_text()
            obj.set_text(text)
            return True
    except:
        pass
    return False


# ================= RESTRICT CHECK =================
def check_restricted_and_restart(d, serial):
    try:
        if d(textContains="ถูกจำกัด").exists(timeout=1) or \
           d(textContains="รอ 7 วัน").exists(timeout=1):

            set_status(serial, "BLOCKED", "Restricted 7 days")

            if d(text="ตกลง").exists(timeout=1):
                d(text="ตกลง").click()
                time.sleep(1)

            d.app_stop("com.linecorp.linelite")
            time.sleep(1)

            raise RestartFlow()
    except:
        pass


# ================= API =================
def get_number(serial):
    set_status(serial, "API", "Buying number")
    url = f"{BASE_URL}/getNumber.php"

    r = requests.get(url, params={
        "api_key": API_KEY,
        "service": SERVICE_CODE
    }, timeout=20)

    data = r.json()
    if not data.get("success"):
        raise Exception(f"Buy number failed: {data}")

    return data["order_id"], data["phone"]


def get_otp_with_retry(d, order_id, timeout=60, serial=None):
    url = f"{BASE_URL}/getStatus.php"

    set_status(serial, "WAIT OTP", "Max 60s")
    start = time.time()

    while time.time() - start < timeout:
        guard_check(d, serial)
        check_restricted_and_restart(d, serial)

        try:
            r = requests.get(url, params={
                "api_key": API_KEY,
                "order_id": order_id
            }, timeout=15)

            data = r.json()

            if data.get("success") and data.get("status") == "received":
                set_status(serial, "OTP", "Received")
                return data["otp_code"], order_id

            if data.get("status") in ["cancelled", "banned", "blocked"]:
                set_status(serial, "OTP", "Number blocked")
                raise RestartFlow()

        except:
            pass

        time.sleep(2)

    set_status(serial, "OTP", "Timeout -> Restart")
    raise RestartFlow()


# ================= SMART UI =================
def wait_for(d, timeout=25, interval=0.5, **kwargs):
    start = time.time()
    while time.time() - start < timeout:
        try:
            if d(**kwargs).exists:
                return True
        except:
            pass
        time.sleep(interval)
    return False


def auto_handle_dialogs(d, rounds=3):
    selectors = [
        {"text": "ตกลง"},
        {"textMatches": "(?i)ok|confirm|yes"},
        {"text": "ยอมรับ"},
        {"text": "อนุญาต"},
        {"text": "ดำเนินการต่อ"},
        {"text": "ถัดไป"},
        {"text": "สมัครใช้งาน"},
        {"text": "ทำต่อ"},
    ]

    for _ in range(rounds):
        for sel in selectors:
            try:
                if d(**sel).exists:
                    d(**sel).click()
                    time.sleep(0.2)
            except:
                pass
        time.sleep(0.2)


def sweep_forward_only(d):
    texts = [
        "สมัครใช้งาน","ทำต่อ","ตกลง",
        "ดำเนินการต่อ","ถัดไป",
        "ยอมรับ","อนุญาต","ยืนยัน","สร้างบัญชีใหม่"
    ]

    for t in texts:
        try:
            if d(text=t).exists(timeout=0.2):
                d(text=t).click()
                time.sleep(0.2)
                return
        except:
            pass

    d.click(0.92, 0.92)
    time.sleep(0.2)


def spam_forward(d, rounds=5):
    for _ in range(rounds):
        auto_handle_dialogs(d, rounds=1)
        sweep_forward_only(d)
        time.sleep(0.3)


def confirm_age_and_send_sms(d, serial, timeout=20):
    set_status(serial, "SMS", "Confirm age & send")
    start = time.time()

    while time.time() - start < timeout:
        try:
            if d(textContains="11").exists(timeout=0.2):
                d(textContains="11").click()
                time.sleep(0.2)

            d.click(0.92, 0.92)
            time.sleep(0.8)

            if d(text="ตกลง").exists(timeout=0.5):
                d(text="ตกลง").click()
                return True

        except:
            pass

        time.sleep(0.5)

    return False


# ================= MAIN FLOW =================
def flow_register_line(d, serial):
    while True:
        try:
            set_status(serial, "START", "Register flow")

            open_line(serial)
            spam_forward(d, rounds=6)

            guard_check(d, serial)
            check_restricted_and_restart(d, serial)

            # ---------- PHONE ----------
            set_status(serial, "INPUT", "Waiting phone input")

            if not wait_for(d, timeout=25, className="android.widget.EditText"):
                continue

            order_id, phone = get_number(serial)
            set_status(serial, "INPUT", f"Phone {phone}")

            fast_set_text(d, phone, className="android.widget.EditText")
            time.sleep(0.2)

            confirm_age_and_send_sms(d, serial)

            guard_check(d, serial)
            check_restricted_and_restart(d, serial)

            # ---------- OTP (60 วิ max) ----------
            otp, _ = get_otp_with_retry(
                d,
                order_id,
                timeout=60,
                serial=serial
            )

            set_status(serial, "INPUT", "Entering OTP")
            fast_set_text(d, otp, className="android.widget.EditText")
            spam_forward(d, rounds=3)

            guard_check(d, serial)
            check_restricted_and_restart(d, serial)

            # ---------- NAME ----------
            name = get_unique_mixed_name()
            set_status(serial, "PROFILE", f"Name {name}")

            edits = d(className="android.widget.EditText")
            if edits.exists(timeout=6):
                edits[0].set_text(name)

            d.click(0.92, 0.92)
            time.sleep(2)

            # ---------- PASSWORD ----------
            # ---------- PASSWORD ----------
            pwd = "Aa112233"
            set_status(serial, "SECURITY", "Setting password")

            if wait_for(d, timeout=20, className="android.widget.EditText"):
                edits = d(className="android.widget.EditText")

                if edits.exists:
                    if len(edits) == 1:
                        edits[0].set_text(pwd)

                    elif len(edits) >= 2:
                        edits[0].set_text(pwd)
                        time.sleep(0.2)
                        edits[1].set_text(pwd)

            time.sleep(1)

            # ---------- CLICK NEXT AFTER PASSWORD ----------
            set_status(serial, "REGISTER", "Click Next after password")

            if d(textMatches="(?i)ต่อไป|ต่อ|next").exists(timeout=5):
                d(textMatches="(?i)ต่อไป|ต่อ|next").click()
            else:
                w, h = d.window_size()
                d.click(int(w * 0.9), int(h * 0.92))

            time.sleep(2)

            # ---------- FRIEND SETTINGS PAGE ----------
            set_status(serial, "REGISTER", "Friend settings")

            if d(textContains="เพิ่มเพื่อน").exists(timeout=15):

                if d(textContains="เพิ่มเพื่อนอัตโนมัติ").exists:
                    try:
                        row = d(textContains="เพิ่มเพื่อนอัตโนมัติ").parent()

                        sw = row.child(className="android.widget.Switch")
                        if not sw.exists:
                            sw = row.child(className="android.widget.CheckBox")

                        if sw.exists and not sw.info.get("checked", False):
                            sw.click()
                            set_status(serial, "REGISTER", "Auto add friend ON")
                            time.sleep(1)

                    except:
                        b = d(textContains="เพิ่มเพื่อนอัตโนมัติ").info["bounds"]
                        d.click(b["left"] - 40, (b["top"] + b["bottom"]) // 2)
                        time.sleep(1)

                # next arrow
                w, h = d.window_size()
                d.click(int(w * 0.9), int(h * 0.92))
                time.sleep(2)

                # continue
                if d(text="ทำต่อ").exists(timeout=8):
                    d(text="ทำต่อ").click()
                    time.sleep(2)

                # permission
                if d(textMatches="(?i)อนุญาต|allow").exists(timeout=8):
                    d(textMatches="(?i)อนุญาต|allow").click()
                    time.sleep(2)

                set_status(serial, "DONE", f"Register success | {phone} | {pwd}")
                break



        except RestartFlow:
            set_status(serial, "RESTART", "Restarting flow")
            time.sleep(2)
            continue

        except Exception as e:
            set_status(serial, "ERROR", str(e))
            time.sleep(3)
            return
    return

import time
import random

def press_close_x(d, serial, retry=3):
    set_status(serial, "NAV", "Closing profile (X)")

    w, h = d.window_size()

    for _ in range(retry):

        # วิธี 1: accessibility
        if d(descriptionMatches="(?i)ปิด|close").exists(timeout=0.8):
            d(descriptionMatches="(?i)ปิด|close").click()
            time.sleep(1)
            return True

        # วิธี 2: resource id
        if d(resourceIdMatches=".*close.*").exists(timeout=0.8):
            d(resourceIdMatches=".*close.*").click()
            time.sleep(1)
            return True

        # วิธี 3: พิกัด X (ชัวร์สุดสำหรับ LINE)
        d.click(int(w * 0.06), int(h * 0.07))
        time.sleep(1)

        # ถ้าออกแล้วจะไม่เห็นคำว่า Keep Memo (อยู่หน้าโปรไฟล์เท่านั้น)
        if not d(textContains="Keep Memo").exists(timeout=0.8):
            return True

    return False



def flow_set_profile_picture(d, serial):
    set_status(serial, "PROFILE", "Start set profile picture")

    try:
        w, h = d.window_size()

        # 1 เปิดโปรไฟล์
        d.click(int(w * 0.88), int(h * 0.16))
        time.sleep(1.2)

        # 2 กดรูปโปรไฟล์
        d.click(int(w * 0.5), int(h * 0.45))
        time.sleep(1.2)

        # 3 แก้ไข
        if d(textContains="แก้ไข").exists(timeout=3):
            d(textContains="แก้ไข").click()
        else:
            d.click(int(w * 0.9), int(h * 0.1))
        time.sleep(0.8)

        # 4 เลือกรูป
        if d(textContains="เลือกรูป").exists(timeout=3):
            d(textContains="เลือกรูป").click()
        time.sleep(1.2)

        # 5 อนุญาต
        if d(textMatches="(?i)อนุญาต|allow").exists(timeout=2):
            d(textMatches="(?i)อนุญาต|allow").click()
            time.sleep(1)

        # สแกนรูป
        set_status(serial, "PROFILE", "Scanning gallery fast")
        all_valid_images = []

        for _ in range(4):
            images = d(className="android.widget.ImageView")

            for i in range(len(images)):
                try:
                    info = images[i].info
                    b = info.get("bounds")
                    if not b:
                        continue

                    width = b["right"] - b["left"]
                    height = b["bottom"] - b["top"]

                    if width > w * 0.18 and height > h * 0.12:
                        all_valid_images.append(images[i])
                except:
                    continue

            d.swipe(w//2, int(h*0.8), w//2, int(h*0.3), 0.12)
            time.sleep(0.4)

        if not all_valid_images:
            set_status(serial, "ERROR", "No image found")
            return False

        random.choice(all_valid_images).click()
        time.sleep(1.2)

        # Next
        if d(textMatches="(?i)ต่อไป|next").exists(timeout=3):
            d(textMatches="(?i)ต่อไป|next").click()
        else:
            d.click(int(w * 0.9), int(h * 0.92))

        time.sleep(1)

        # Done
        if d(textMatches="(?i)เสร็จสิ้น|เสร็จ|done").exists(timeout=3):
            d(textMatches="(?i)เสร็จสิ้น|เสร็จ|done").click()
        else:
            d.click(int(w * 0.9), int(h * 0.92))

        time.sleep(1.5)

        # ⭐ กด X อย่างเดียว
        press_close_x(d, serial)

        set_status(serial, "DONE", "Profile picture updated")
        return True

    except Exception as e:
        set_status(serial, "ERROR", f"Profile error: {e}")
        return False

# ---------- FLOW: ADD FRIEND FROM HOME (ICON +) ----------
# ---------- FLOW: ADD FRIEND FAST MODE ----------
# ---------- FLOW: ADD FRIEND FROM HOME (ICON +) ----------
def flow_add_friend_by_id(d, serial, line_id="swatch1150"):
    set_status(serial, "STEP6", f"Add friend {line_id}")

    try:
        w, h = d.window_size()

        # เปิด LINE และรอหน้า Home
        open_line(serial)
        time.sleep(3)

        # 1️⃣ กดไอคอน "รูปคน+" มุมขวาบน
        set_status(serial, "STEP6", "Click add friend icon (+)")

        clicked = False

        if d(descriptionContains="เพิ่มเพื่อน").exists(timeout=2):
            d(descriptionContains="เพิ่มเพื่อน").click()
            clicked = True

        if not clicked:
            d.click(int(w * 0.93), int(h * 0.12))

        time.sleep(1.5)

        # 2️⃣ กด "ค้นหา"
        if d(textContains="ค้นหา").exists(timeout=3):
            d(textContains="ค้นหา").click()
        else:
            set_status(serial, "ERROR", "ไม่เจอปุ่มค้นหา")
            return False

        time.sleep(1)

        # 3️⃣ เลือก LINE ID
        if d(textMatches="(?i)line id").exists(timeout=3):
            d(textMatches="(?i)line id").click()
        else:
            set_status(serial, "ERROR", "ไม่เจอเมนู LINE ID")
            return False

        time.sleep(1)

        # 4️⃣ ใส่ไอดี
        input_box = d(className="android.widget.EditText")
        if input_box.exists(timeout=3):
            input_box.set_text(line_id)
        else:
            set_status(serial, "ERROR", "ไม่เจอช่องกรอก")
            return False

        time.sleep(0.5)

        # 5️⃣ กด Enter
        d.press("enter")
        time.sleep(2)

        # 🔥 6️⃣ กดย้อนกลับ 2 ครั้ง
        set_status(serial, "STEP6", "Go back 2 times")

        d.press("back")
        time.sleep(0.6)
        d.press("back")
        time.sleep(1)

        set_status(serial, "DONE", f"Searched {line_id} and returned")
        return True

    except Exception as e:
        set_status(serial, "ERROR", f"Step6 error: {e}")
        return False




# ---------- FLOW: DELETE CONTACTS ----------
def flow_delete_contacts(d, serial):
    set_status(serial, "เริ่มต้น", "เปิดแอปรายชื่อผู้ติดต่อ")
    open_contacts(d, serial)
    time.sleep(5)

    round_count = 0
    fail_count = 0  # นับรอบที่ทำไม่สำเร็จติดกัน

    w, h = d.window_size()
    click_x = int(w * 0.3)
    click_y = int(h * 0.5)

    while True:
        if CANCEL_EVENT.is_set():
            set_status(serial, "ยกเลิก", "ผู้ใช้สั่งหยุด")
            time.sleep(4)
            return

        round_count += 1
        set_status(serial, "ตรวจสอบ", f"รอบที่ {round_count}")

        # ลองกดค้างกลางรายการ
        set_status(serial, "เลือก", "กดค้างกลางรายการ")
        try:
            d.long_click(click_x, click_y)
        except:
            fail_count += 1
            set_status(serial, "ผิดพลาด", f"กดค้างไม่สำเร็จ ({fail_count}/3)")
            if fail_count >= 3:
                set_status(serial, "เสร็จสิ้น", "ไม่พบรายการแล้ว (พยายามครบ 3 ครั้ง)")
                break
            time.sleep(2)
            continue

        time.sleep(1)

        # หาปุ่มเมนู 3 จุด
        if d(descriptionContains="เพิ่มเติม").exists:
            d(descriptionContains="เพิ่มเติม").click()
        elif d(descriptionContains="More").exists:
            d(descriptionContains="More").click()
        else:
            fail_count += 1
            set_status(serial, "ผิดพลาด", f"ไม่เจอเมนูเพิ่มเติม ({fail_count}/3)")
            if fail_count >= 3:
                set_status(serial, "เสร็จสิ้น", "ไม่พบรายการแล้ว (พยายามครบ 3 ครั้ง)")
                break

            # ลองเลื่อนแล้วค่อยใหม่
            d.swipe(w//2, int(h*0.7), w//2, int(h*0.3), 0.2)
            time.sleep(2)
            continue

        time.sleep(1)

        # ถ้ามาถึงตรงนี้ = สำเร็จอย่างน้อย 1 ขั้น รีเซ็ต fail_count
        fail_count = 0

        # เลือกทั้งหมด (ถ้ามี)
        if d(textContains="เลือกทั้งหมด").exists:
            set_status(serial, "เลือก", "เลือกทั้งหมด")
            d(textContains="เลือกทั้งหมด").click()
            time.sleep(1)

        # กดลบ
        set_status(serial, "กำลังลบ", "กดปุ่มลบ")
        if d(textContains="ลบ").exists:
            d(textContains="ลบ").click()
        elif d(descriptionContains="ลบ").exists:
            d(descriptionContains="ลบ").click()
        else:
            fail_count += 1
            set_status(serial, "ผิดพลาด", f"ไม่เจอปุ่มลบ ({fail_count}/3)")
            if fail_count >= 3:
                set_status(serial, "เสร็จสิ้น", "ไม่พบรายการแล้ว (พยายามครบ 3 ครั้ง)")
                break
            time.sleep(2)
            continue

        time.sleep(1)

        # ยืนยันลบ
        if d(text="ลบ").exists:
            d(text="ลบ").click()

        set_status(serial, "รอระบบ", "กำลังลบข้อมูล")
        time.sleep(4)

    set_status(serial, "เสร็จสิ้น", "ลบรายชื่อทั้งหมดเรียบร้อย")

# ---------- FLOW: DELETE LINE FRIENDS ----------
def flow_delete_line_friends(d, serial, max_delete=None):
    set_status(serial, "เริ่มต้น", "เปิด LINE")
    open_line(serial)
    time.sleep(3)

    # === เข้า "รายชื่อเพื่อน" โดยกดคำว่า "ดูทั้งหมด" ===
    set_status(serial, "นำทาง", "กด ดูทั้งหมด (รายชื่อเพื่อน)")

    if not d(text="ดูทั้งหมด").exists(timeout=8):
        set_status(serial, "ผิดพลาด", "ไม่เจอปุ่ม ดูทั้งหมด")
        return

    d(text="ดูทั้งหมด").click()
    time.sleep(1.5)

    if not d(textContains="รายชื่อเพื่อน").exists(timeout=8):
        set_status(serial, "ผิดพลาด", "ยังไม่เข้าเมนู รายชื่อเพื่อน")
        return

    set_status(serial, "สำเร็จ", "เข้าเมนู รายชื่อเพื่อนแล้ว")
    time.sleep(1)

    delete_count = 0
    fail_round = 0
    no_delete_menu_round = 0  # เอาไว้เช็คว่าลบหมดแล้วจริงไหม

    while True:
        if CANCEL_EVENT.is_set():
            set_status(serial, "ยกเลิก", "ผู้ใช้สั่งหยุด")
            return

        if max_delete is not None and delete_count >= max_delete:
            set_status(serial, "เสร็จสิ้น", f"ลบครบ {delete_count} คนแล้ว")
            break

        # === หา TextView ที่เป็น "ชื่อเพื่อน" จริง ===
        name_nodes = d(className="android.widget.TextView")

        target = None
        for i in range(len(name_nodes)):
            try:
                t = name_nodes[i].get_text()
                if not t:
                    continue

                # ตัดพวกที่ไม่ใช่ชื่อเพื่อน
                if t in ["เพื่อน", "กลุ่ม", "บัญชีทางการ", "ค้นหาด้วยชื่อ"]:
                    continue
                if "เพื่อน" in t and any(ch.isdigit() for ch in t):
                    # ข้ามหัวข้อ "เพื่อน 83/84"
                    continue

                target = name_nodes[i]
                break
            except:
                pass

        if target is None:
            set_status(serial, "เสร็จสิ้น", "ไม่เจอชื่อเพื่อนให้ลบแล้ว")
            break

        # === พยายามกดค้างที่ทั้งแถว (parent) ===
        clicked = False
        try:
            item = target.xpath("..")
            b = item.info.get("bounds")
            if b:
                x = (b["left"] + b["right"]) // 2
                y = (b["top"] + b["bottom"]) // 2
                set_status(serial, "เลือก", f"กดค้างที่ ({x},{y})")
                d.long_click(x, y, 2.2)
                clicked = True
        except:
            pass

        # === fallback: กดโซนกลางจอ ===
        if not clicked:
            try:
                w, h = d.window_size()
                x = int(w * 0.5)
                y = int(h * 0.35)
                set_status(serial, "เลือก", f"fallback กดค้างที่ ({x},{y})")
                d.long_click(x, y, 2.2)
                clicked = True
            except:
                pass

        if not clicked:
            fail_round += 1
            set_status(serial, "ผิดพลาด", "กดค้างไม่สำเร็จ")
            time.sleep(0.8)
            if fail_round >= 3:
                set_status(serial, "เสร็จสิ้น", "ไม่สามารถเลือกเพื่อนได้แล้ว")
                break
            continue

        fail_round = 0
        time.sleep(0.6)

        # === เช็คว่ามีเมนู "ลบ" โผล่มาไหม ===
        if not d(text="ลบ").exists(timeout=1.5):
            no_delete_menu_round += 1
            set_status(serial, "เช็ค", f"ไม่เจอเมนูลบ ({no_delete_menu_round}/3)")
            if no_delete_menu_round >= 3:
                set_status(serial, "เสร็จสิ้น", f"น่าจะลบหมดแล้ว ({delete_count} คน)")
                break
            else:
                continue
        else:
            no_delete_menu_round = 0

        # === กด "ลบ" ===
        d(text="ลบ").click()
        time.sleep(0.5)

        # === ยืนยัน "ลบ" ===
        if d(text="ลบ").exists(timeout=2):
            d(text="ลบ").click()
        else:
            set_status(serial, "ผิดพลาด", "ไม่เจอปุ่มยืนยันลบ")
            d.press("back")
            time.sleep(0.8)
            continue

        delete_count += 1
        set_status(serial, "กำลังลบ", f"ลบไปแล้ว {delete_count} คน")
        time.sleep(1.2)

    set_status(serial, "เสร็จสิ้น", f"ลบเพื่อน LINE เสร็จแล้ว ({delete_count} คน)")

def flow_clear_recent_and_clearall(d, serial, retry=5):
    set_status(serial, "STEP7", "Open recent apps")

    w, h = d.window_size()

    for i in range(retry):
        if CANCEL_EVENT.is_set():
            set_status(serial, "ยกเลิก", "ผู้ใช้สั่งหยุด")
            return False

        try:
            # วิธีหลัก: กดปุ่ม Recent (App switch)
            try:
                d.press("recent")  # uiautomator2 รองรับ key นี้ในหลายเครื่อง
            except:
                # fallback: กดพิกัดปุ่มสี่เหลี่ยมมุมขวาล่าง
                d.click(int(w * 0.93), int(h * 0.97))

            time.sleep(1.0)

            set_status(serial, "STEP7", "Looking for 'ล้างทั้งหมด'")

            # ปุ่ม "ล้างทั้งหมด" (ไทย) / "Clear all" (อังกฤษ) / "ล้างทั้งหมด▼" บางรุ่น
            if d(textContains="ล้างทั้งหมด").exists(timeout=1.5):
                d(textContains="ล้างทั้งหมด").click()
                time.sleep(0.8)
                set_status(serial, "DONE", "Cleared all recent apps")
                return True

            if d(textMatches="(?i)clear\\s*all").exists(timeout=1.5):
                d(textMatches="(?i)clear\\s*all").click()
                time.sleep(0.8)
                set_status(serial, "DONE", "Cleared all recent apps")
                return True

            # fallback สุดท้าย: กดโซนขวาบน/ขวากลางที่มักเป็นตำแหน่ง "ล้างทั้งหมด"
            # (เพราะบาง LD ซ่อนเป็น text เล็ก ๆ)
            d.click(int(w * 0.85), int(h * 0.12))
            time.sleep(0.8)
            if d(textContains="ล้างทั้งหมด").exists(timeout=1.0):
                d(textContains="ล้างทั้งหมด").click()
                time.sleep(0.8)
                set_status(serial, "DONE", "Cleared all recent apps")
                return True

        except Exception as e:
            set_status(serial, "ERROR", f"Step7 error: {e}")

        time.sleep(0.6)

    set_status(serial, "ERROR", "ไม่เจอปุ่ม 'ล้างทั้งหมด'")
    return False
    
    
def flow_back_and_reopen_line(d, serial):
    set_status(serial, "STEP8", "Back then reopen LINE")

    try:
        # 1) กด Back (ปุ่มสามเหลี่ยม)
        try:
            d.press("back")
        except:
            w, h = d.window_size()
            d.click(int(w * 0.93), int(h * 0.91))

        time.sleep(0.6)

        # 2) เปิด LINE ใหม่
        open_line(serial)
        time.sleep(2)

        set_status(serial, "DONE", "Back + Reopen LINE")
        return True

    except Exception as e:
        set_status(serial, "ERROR", f"Step8 error: {e}")
        return False


# ---------- WORKER ----------
def run_on_device(serial, mode):
    set_status(serial, "CONNECT", "Connecting")
    try:
        d = u2.connect(serial)
        set_status(serial, "CONNECTED", "OK")
    except Exception as e:
        set_status(serial, "ERROR", f"Connect fail: {e}")
        return

    if mode == "1":
        flow_register_line(d, serial)
    elif mode == "2":
        flow_delete_contacts(d, serial)
    elif mode == "3":
        flow_delete_line_friends(d, serial)
        
    elif mode == "4":
        set_status(serial, "START", "Profile picture only mode")
        open_line(serial)
        time.sleep(3)
        flow_set_profile_picture(d, serial)
        set_status(serial, "DONE", "Profile picture updated")  
    elif mode == "5":
        set_status(serial, "START", "Add friend mode")
        flow_add_friend_by_id(d, serial)       
    elif mode == "7":
        set_status(serial, "START", "Clear recent apps (Clear all)")
        flow_clear_recent_and_clearall(d, serial)
    
    elif mode == "8":
        set_status(serial, "START", "Back + Reopen LINE")
        flow_back_and_reopen_line(d, serial)

    
     # ---------- CANCEL_EVENT ----------
        
def cancel_listener():
    while not CANCEL_EVENT.is_set():
        if msvcrt.kbhit():
            key = msvcrt.getch().decode("utf-8", errors="ignore").lower()
            if key == "q":
                print("\n🛑 ผู้ใช้กด Q เพื่อยกเลิกงานทั้งหมด!")
                CANCEL_EVENT.set()
                break
        time.sleep(0.2)


def clear_all_status():
    global DEVICE_STATUS   # ชื่อ dict/list ที่คุณใช้เก็บสถานะ
    DEVICE_STATUS.clear()



# ---------- MENU ----------
def show_menu():
    show_banner(
        "MULTI LD AUTOMATION TOOL",
        "Auto Register LINE | Delete Contacts | Delete LINE Friends"
    )
    console.print("\n[bold cyan]" + "="*60 + "[/bold cyan]")
    console.print("[bold green]1) 🤖 สมัคร LINE อัตโนมัติ (🟢 ใช้งานได้ 🟢)[/bold green]")
    console.print("[bold blue]2) 🗑️ ลบรายชื่อผู้ติดต่อทั้งหมด (🟢 ใช้งานได้ 🟢)[/bold blue]")
    console.print("[bold white]3) 👥 ลบเพื่อนใน LINE ทั้งหมด (🟢 ใช้งานได้ 🟢)[/bold white]")
    console.print("[bold cyan]4) ⚙️ ตั้งค่ารูปโปรไฟล์ (🟢 ใช้งานได้ 🟢)[/bold cyan]")
    console.print("[bold yellow]5) ➕ เช๊คไอดีไลน์ (🟢 ใช้งานได้ 🟢)[/bold yellow]")
    console.print("[bold red]6) 🔄 รีสตาร์ทโปรแกรมเพื่ออัพเดตโค้ด[/bold red]")
    console.print("[bold magenta]7) 🧹 ปัดล้างทั้งหมด[/bold magenta]")
    console.print("[bold bright_cyan]8) 🔙 เปิด LINE ใหม่ [/bold bright_cyan]")
    console.print("[bold cyan]" + "="*60 + "[/bold cyan]")
    console.print("[yellow]⚡ รันทุก LD พร้อมกัน | 📊 มีสถานะ Real-time[/yellow]")
    console.print("[bold cyan]" + "="*60 + "[/bold cyan]")


# ---------- MAIN ----------
def main():
    while True:
        CANCEL_EVENT.clear()

        clear_screen()
        show_menu()

        mode = input("👉 เลือกโหมด (1/2/3/4/5/6/7/8) หรือพิมพ์ Q เพื่อออก: ").strip().lower()

        if mode == "q":
            print("👋 ออกจากโปรแกรมแล้ว")
            break
        if mode == "6":
            fancy_restart()
            
            
        if mode not in ["1", "2", "3", "4", "5", "6", "7", "8"]:
            print("❌ เลือกโหมดไม่ถูกต้อง")
            input("กด Enter เพื่อกลับไปเมนู...")
            continue

        devices = get_devices()
        if not devices:
            print("❌ ไม่เจอ LD Player")
            input("กด Enter เพื่อกลับไปเมนู...")
            continue

        clear_screen()
        print("🚀 เริ่มทำงาน... (กด Q เพื่อยกเลิก)\n")

        for s in devices:
            set_status(s, "รอ", "เตรียมทำงาน")

        stop_event = threading.Event()
        ui_thread = threading.Thread(target=status_ui_loop, args=(stop_event,), daemon=True)
        ui_thread.start()

        # ตัวดักปุ่ม Q
        listener_thread = threading.Thread(target=cancel_listener, daemon=True)
        listener_thread.start()

        max_workers = len(devices)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for serial in devices:
                futures.append(executor.submit(run_on_device, serial, mode))

            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"Thread error: {e}")

        stop_event.set()
        time.sleep(1)
                # ===== สรุปผล =====
        if CANCEL_EVENT.is_set():
            console.print("\n[bold red]🛑 งานถูกยกเลิกโดยผู้ใช้[/bold red]")
        else:
            console.print("\n[bold bright_green]🎉 DONE ALL DEVICES![/bold bright_green]")

        input("\nกด Enter เพื่อกลับไปเมนู...")


if __name__ == "__main__":
    try:
        clear_all_status()   # <-- ล้างประวัติทุกครั้งที่เปิดโปรแกรม
        main()
    except KeyboardInterrupt:
        print("\n🛑 ผู้ใช้กดยกเลิก (Ctrl+C)")
        CANCEL_EVENT.set()
