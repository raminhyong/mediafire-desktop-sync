"""พิมพ์ session ของ MediaFire (session_token / time / secret_key) เป็น JSON บรรทัดเดียว

ใช้คู่กับ Get-Cupy-Session.bat — อ่านบัญชีจาก config.json ในโฟลเดอร์เดียวกัน
ไม่พิมพ์รหัสผ่านออกมา · ใช้ session นี้กับเครื่องมือ mf_upload.py ของ Cupy
"""
import json
import sys
from pathlib import Path

try:
    from mediafire import MediaFireApi, MediaFireApiError
except ImportError:
    sys.exit("ยังไม่ได้ติดตั้งไลบรารี mediafire — รัน Setup-NewMachine.bat ก่อน")

cfg_path = Path(__file__).with_name("config.json")
if not cfg_path.exists():
    sys.exit("ไม่พบ config.json ในโฟลเดอร์นี้")

cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
api = MediaFireApi()
try:
    r = api.user_get_session_token(
        app_id=str(cfg.get("app_id", "42511")),
        email=cfg["email"],
        password=cfg["password"],
    )
except MediaFireApiError as e:
    sys.exit(f"MediaFire ปฏิเสธ: {e}")
except Exception as e:  # noqa: BLE001
    sys.exit(f"เชื่อมต่อไม่ได้: {type(e).__name__}: {e}")

print(json.dumps({
    "session_token": r["session_token"],
    "time": r["time"],
    "secret_key": r["secret_key"],
}, ensure_ascii=False))
