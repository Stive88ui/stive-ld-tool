import requests
import time

API_KEY = "f63643e17c5d2664ce09e28ddfd8ccc0c37d59d3f1cc8dd9a8a99489c54574c7"
BASE_URL = "https://otp24hr.store/api"
SERVICE_CODE = "me"  # หรือ "line" ถ้าอันนี้ไม่ผ่าน

def get_number():
    url = f"{BASE_URL}/getNumber.php"
    r = requests.get(url, params={
        "api_key": API_KEY,
        "service": SERVICE_CODE
    }, timeout=30)

    print("🌐 BUY STATUS:", r.status_code)
    print("🌐 BUY RESPONSE:", r.text)

    data = r.json()

    if not data.get("success"):
        raise Exception("❌ ซื้อเบอร์ไม่สำเร็จ: " + str(data))

    return data["order_id"], data["phone"]

def get_otp(order_id, timeout=120):
    start = time.time()

    while time.time() - start < timeout:
        url = f"{BASE_URL}/getStatus.php"
        r = requests.get(url, params={
            "api_key": API_KEY,
            "order_id": order_id
        }, timeout=30)

        print("🌐 OTP RESPONSE:", r.text)

        try:
            data = r.json()
        except:
            time.sleep(5)
            continue

        if data.get("success") and data.get("status") == "received":
            return data["otp_code"]

        time.sleep(5)

    return None
