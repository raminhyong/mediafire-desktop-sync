# MediaFire Desktop Cloud & Two-Way Sync System

ระบบไคลเอนต์เดสก์ท็อปและระบบซิงก์ข้อมูลสองทิศทาง (Two-Way Sync) อัตโนมัติระหว่างเครื่อง Windows PC กับ MediaFire Cloud Storage (เสมือน Google Drive / OneDrive) ทำงานเงียบในเบื้องหลัง พร้อมระบบเริ่มทำงานอัตโนมัติเมื่อเปิดเครื่อง (Auto-Start on Boot)

---

## 1. จุดเด่นและคุณสมบัติของระบบ (Key Features)

```text
+-----------------------+                    +------------------------+
|      Windows PC       |                    |    MediaFire Cloud     |
|                       |  Two-Way Sync      |                        |
|  [ MediaFire_Sync ]   |<==================>|   [ My Files / Cloud ] |
|  - เอกสาร/ไฟล์งาน      | (Upload/Download)  |   - เข้าถึงผ่านเว็บ     |
|  - บันทึกการเปลี่ยนแปลง|                    |   - เข้าถึงผ่านมือถือ   |
+-----------------------+                    +------------------------+
           |
           +---> Silent Daemon (Pythonw / Background VBS)
           +---> Desktop App Sandbox (Edge / Chrome App Mode)
           +---> Auto-Start on Windows Boot (Startup Registry)
```

1. **Two-Way Continuous Sync (ซิงก์ 2 ทิศทาง)**:
   - **PC -> Cloud**: วางไฟล์ลงในโฟลเดอร์ `MediaFire_Sync` ไฟล์จะถูกอัปโหลดขึ้นสู่คลาวด์ให้อัตโนมัติ
   - **Cloud -> PC**: อัปโหลดไฟล์จากมือถือหรือหน้าเว็บ MediaFire ไฟล์จะถูกดึงลงมาที่เครื่องอัตโนมัติ
2. **Silent Background Daemon**:
   - ทำงานผ่าน VBScript และ `pythonw.exe` ไม่มีหน้าต่าง Command Prompt ดำคอยกวนสายตา
3. **Turnkey Setup for All Machines (ติดตั้งง่ายทุกเครื่อง)**:
   - สคริปต์ `Setup-NewMachine.bat` ตั้งค่าสภาพแวดล้อม Python, ติดตั้ง Dependencies, สร้างโฟลเดอร์ซิงก์, ทำ Desktop Shortcuts และลงทะเบียน Startup ให้เสร็จสิ้นในคลิกเดียว
4. **Desktop App Experience**:
   - เข้าถึงหน้าเว็บจัดเก็บไฟล์แบบแอปพลิเคชันเดสก์ท็อปผ่านชอร์ตคัต `MediaFire Cloud`
5. **Interactive Control Console**:
   - สคริปต์ `Status-Sync.bat` สำหรับดูสถานะการทำงาน, ดู Logs แบบ Real-time และสั่ง Start/Stop ได้ในเมนูเดียว

---

## 2. โครงสร้างไฟล์ในโปรเจกต์ (Project Structure)

```text
Mediafire/
├── MediaFire_Sync/             # โฟลเดอร์ซิงก์ไฟล์ในเครื่อง (ละเว้นจาก Git)
├── .gitignore                  # กฎการป้องกันข้อมูลส่วนตัวและรหัสผ่าน
├── Setup-NewMachine.bat        # ตัวช่วยติดตั้งระบบอัตโนมัติสำหรับเครื่องใหม่
├── Start-Sync.bat              # สั่งเริ่มระบบซิงก์ในเบื้องหลัง
├── Stop-Sync.bat               # สั่งหยุดการทำงานของระบบซิงก์
├── Status-Sync.bat             # ตรวจสอบสถานะการทำงานและดูบันทึกกิจกรรมล่าสุด
├── Launch-Sync-Background.vbs  # ตัวเรียก Daemon แบบซ่อนหน้าต่าง
├── Launch-MediaFire.bat        # เปิดหน้าต่างแอป MediaFire Cloud
├── Launch-MediaFire.vbs        # สคริปต์เปิดเว็บ MediaFire ในรูปแบบ App Mode
├── create_shortcut.ps1         # สคริปต์สร้างทางลัดบนหน้าเดสก์ท็อป
├── install_autostart.ps1       # สคริปต์ลงทะเบียนเริ่มทำงานอัตโนมัติเมื่อเปิดเครื่อง
├── sync_engine.py              # เครื่องยนต์หลักในการซิงก์ไฟล์สองทิศทาง
├── config.example.json         # ตัวอย่างโครงสร้างไฟล์ตั้งค่า
├── config.json                 # ไฟล์ตั้งค่าบัญชีจริง (เก็บรหัสผ่าน - ห้ามแชร์)
├── requirements.txt            # รายการไลบรารี Python ที่ต้องใช้
└── mediafire.ico               # ไอคอนทางการของ MediaFire
```

---

## 3. ขั้นตอนการติดตั้งบนเครื่องใหม่ (Installation Guide)

### ความต้องการของระบบ:
- ระบบปฏิบัติการ: Windows 10 หรือ Windows 11 (64-bit)
- Python 3.10 ขึ้นไป (ดาวน์โหลดได้จาก [python.org](https://www.python.org/) โดยขณะติดตั้งต้องติ๊กถูก **"Add Python to PATH"**)
- บัญชี GitHub และ Git CLI

---

### ขั้นตอนที่ 1: Clone Repository
เปิด PowerShell หรือ Command Prompt ในโฟลเดอร์ที่ต้องการจัดเก็บ แล้วรันคำสั่ง:
```bash
git clone https://github.com/raminhyong/mediafire-desktop-sync.git Mediafire
cd Mediafire
```

### ขั้นตอนที่ 2: รันตัวติดตั้งอัตโนมัติ
ดับเบิลคลิกที่ไฟล์ **`Setup-NewMachine.bat`**
ระบบจะดำเนินการดังนี้ให้อัตโนมัติ:
- สร้าง Virtual Environment (`.venv`)
- ติดตั้ง Dependencies ทั้งหมดจาก `requirements.txt`
- สร้างไฟล์ `config.json` จากเทมเพลต
- สร้างโฟลเดอร์ `MediaFire_Sync`
- สร้าง Shortcuts บนหน้าเดสก์ท็อป
- ลงทะเบียนระบบเข้า Windows Startup เพื่อให้เปิดทำงานพร้อมเครื่องทันที

### ขั้นตอนที่ 3: ระบุข้อมูลบัญชีใน config.json
เปิดไฟล์ `config.json` ด้วยโปรแกรม Text Editor (เช่น Notepad) แล้วกรอกข้อมูลบัญชี MediaFire ของคุณ:
```json
{
  "email": "your_email@example.com",
  "password": "your_mediafire_password",
  "app_id": "42511",
  "sync_directory": "./MediaFire_Sync",
  "remote_folder_key": "myfiles",
  "poll_interval_seconds": 30
}
```

### ขั้นตอนที่ 4: เริ่มต้นใช้งาน
ดับเบิลคลิกไฟล์ **`Start-Sync.bat`** เพื่อเริ่มทำงานทันที

---

## 4. เครื่องมือควบคุมและตรวจสอบระบบ (Control Scripts)

| สคริปต์ | คำอธิบายการทำงาน |
| :--- | :--- |
| **`Status-Sync.bat`** | เปิดแผงควบคุมหลัก: เช็กว่าระบบกำลังทำงานอยู่หรือไม่ (PID), ดูบันทึก 15 รายการล่าสุด และมีปุ่มลัดสั่งเปิดโฟลเดอร์/เริ่ม/หยุด |
| **`Start-Sync.bat`** | สั่งเริ่มรัน Background Sync Daemon โดยไม่มีหน้าต่างดำ |
| **`Stop-Sync.bat`** | ยุติการทำงานของ Sync Process ในเบื้องหลังทั้งหมด |
| **`MediaFire Sync Folder`** | ทางลัดบนหน้าเดสก์ท็อปสำหรับเปิดโฟลเดอร์จัดเก็บข้อมูล |
| **`MediaFire Cloud`** | ทางลัดบนหน้าเดสก์ท็อปสำหรับเปิดหน้าเว็บคลาวด์แบบหน้าต่างแอป |

---

## 5. ความปลอดภัยและข้อมูลส่วนตัว (Security & Privacy)

- ไฟล์ `config.json` ซึ่งเก็บรหัสผ่านบัญชีจริงถูกระบุไว้ใน `.gitignore` เรียบร้อยแล้ว **จะไม่ถูก Commit หรือ Push ขึ้นสู่ GitHub เด็ดขาด**
- ข้อมูลไฟล์ในโฟลเดอร์ `MediaFire_Sync/` และบันทึกประวัติ `sync_activity.log` ถูกยกเว้นจากการติดตามของ Git เพื่อความปลอดภัยและความเป็นส่วนตัว
