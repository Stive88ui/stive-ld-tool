import os, sys, subprocess, time, shutil, webbrowser

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_FILE = os.path.join(BASE_DIR, "Main.py")

COMMON_GIT_PATHS = [
    r"C:\Program Files\Git\cmd\git.exe",
    r"C:\Program Files\Git\bin\git.exe",
    r"C:\Program Files (x86)\Git\cmd\git.exe",
    r"C:\Program Files (x86)\Git\bin\git.exe",
]

def find_git():
    # 1) เช็คจาก PATH
    p = shutil.which("git")
    if p:
        return p

    # 2) เช็คจาก path มาตรฐาน
    for gp in COMMON_GIT_PATHS:
        if os.path.exists(gp):
            return gp

    return None

def has_winget():
    return shutil.which("winget") is not None

def install_git_winget():
    # ติดตั้ง Git.Git ผ่าน winget (อาจต้องมีสิทธิ์)
    print("🧩 Git not found. Installing Git via winget...")
    cmd = [
        "winget", "install", "--id", "Git.Git",
        "-e",
        "--accept-source-agreements",
        "--accept-package-agreements"
    ]
    r = subprocess.run(cmd, cwd=BASE_DIR)
    return r.returncode == 0

def git_pull(git_path):
    print("🔄 Checking for updates...")
    subprocess.run([git_path, "pull"], cwd=BASE_DIR)

def start_main():
    print("🚀 Starting Main.py")
    os.execv(sys.executable, [sys.executable, MAIN_FILE])

if __name__ == "__main__":
    git_path = find_git()

    if not git_path:
        # ลองติดตั้งอัตโนมัติด้วย winget
        if has_winget():
            ok = install_git_winget()
            time.sleep(1.0)
            git_path = find_git()
            if not ok or not git_path:
                print("❌ Auto install failed. Opening Git download page...")
                webbrowser.open("https://git-scm.com/download/win")
                input("ติดตั้ง Git ให้เสร็จ แล้วเปิดโปรแกรมใหม่ (กด Enter เพื่อปิด)...")
                sys.exit(1)
        else:
            print("❌ This PC has no Git and no winget.")
            print("Opening Git download page...")
            webbrowser.open("https://git-scm.com/download/win")
            input("ติดตั้ง Git ให้เสร็จ แล้วเปิดโปรแกรมใหม่ (กด Enter เพื่อปิด)...")
            sys.exit(1)

    # มี git แล้ว
    try:
        git_pull(git_path)
    except Exception as e:
        print("⚠️ git pull error:", e)

    time.sleep(0.2)
    start_main()
