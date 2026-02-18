import os, sys, subprocess, time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_FILE = os.path.join(BASE_DIR, "Main.py")

def update():
    print("🔄 Checking for updates...")
    subprocess.run(["git", "pull"], cwd=BASE_DIR)

def start():
    print("🚀 Starting Main.py")
    os.execv(sys.executable, [sys.executable, MAIN_FILE])

if __name__ == "__main__":
    update()
    time.sleep(0.3)
    start()
