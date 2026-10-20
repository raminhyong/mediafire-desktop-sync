@echo off
chcp 65001 >nul
cls
echo ===================================================================
echo     MediaFire Cloud & Two-Way Sync System - Setup Wizard
echo ===================================================================
echo.

:: 1. ตรวจสอบ Python
echo [1/5] กำลังตรวจสอบ Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] ไม่พบ Python ในระบบนี้!
    echo กรุณาดาวน์โหลดและติดตั้ง Python 3.10 ขึ้นไปจาก https://www.python.org/
    echo และอย่าลืมติ๊กถูกที่ "Add Python to PATH" ขณะติดตั้ง
    pause
    exit /b 1
)
echo       -> ตรวจพบ Python ในระบบเรียบร้อยแล้ว

:: 2. สร้าง Virtual Environment (.venv)
echo [2/5] กำลังเตรียมสภาพแวดล้อม Python (.venv)...
if not exist "%~dp0.venv\Scripts\python.exe" (
    python -m venv "%~dp0.venv"
    if %errorlevel% neq 0 (
        echo [ERROR] ไม่สามารถสร้าง .venv ได้
        pause
        exit /b 1
    )
)
echo       -> สภาพแวดล้อม .venv พร้อมใช้งาน

:: 3. ติดตั้ง Dependencies
echo [3/5] กำลังติดตั้งโมดูลที่จำเป็น (Requirements)...
"%~dp0.venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
"%~dp0.venv\Scripts\pip.exe" install --quiet -r "%~dp0requirements.txt"
if %errorlevel% neq 0 (
    echo [ERROR] ติดตั้งโมดูลไม่สำเร็จ กรุณาตรวจสอบการเชื่อมต่ออินเทอร์เน็ต
    pause
    exit /b 1
)
echo       -> ติดตั้งโมดูลสำเร็จเรียบร้อย

:: 4. เตรียมไฟล์ config.json
echo [4/5] กำลังตรวจสอบไฟล์ตั้งค่า config.json...
if not exist "%~dp0config.json" (
    copy "%~dp0config.example.json" "%~dp0config.json" >nul
    echo.
    echo       [สำคัญ] ระบบได้สร้างไฟล์ config.json ให้แล้ว
    echo       กรุณาเปิดไฟล์ config.json แล้วกรอก email และ password ของคุณ!
    echo.
) else (
    echo       -> พบไฟล์ config.json พร้อมใช้งาน
)

if not exist "%~dp0MediaFire_Sync" (
    mkdir "%~dp0MediaFire_Sync"
)

:: 5. สร้าง Shortcut บน Desktop และ Startup
echo [5/5] กำลังสร้าง Desktop Shortcut และตั้งค่าเปิดระบบอัตโนมัติ...
powershell -ExecutionPolicy Bypass -File "%~dp0create_shortcut.ps1"
powershell -ExecutionPolicy Bypass -File "%~dp0install_autostart.ps1"

echo.
echo ===================================================================
echo                การติดตั้งเสร็จสมบูรณ์ 100%%
echo ===================================================================
echo.
echo สิ่งที่ต้องทำต่อไป:
echo  1. ตรวจสอบ/แก้ไขไฟล์ config.json (ใส่อีเมลและรหัสผ่าน MediaFire)
echo  2. ดับเบิลคลิกไฟล์ Start-Sync.bat เพื่อเริ่มซิงก์ข้อมูลทันที
echo  3. สามารถตรวจสอบสถานะได้ที่ไฟล์ Status-Sync.bat
echo.
pause
