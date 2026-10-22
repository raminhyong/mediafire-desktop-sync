@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo === Cupy session helper ===
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] ไม่พบ .venv — รัน Setup-NewMachine.bat ก่อน
    pause
    exit /b 1
)
if not exist "config.json" (
    echo [ERROR] ไม่พบ config.json ในโฟลเดอร์นี้
    pause
    exit /b 1
)

".venv\Scripts\python.exe" get_session.py > "%TEMP%\cupy_session.txt" 2>&1
type "%TEMP%\cupy_session.txt"
clip < "%TEMP%\cupy_session.txt"

echo.
echo ============================================================
echo  คัดลอกลง clipboard แล้ว - ไปวางใน Telegram (Ctrl+V)
echo  ถ้าเห็นข้อความ ERROR ให้ส่งข้อความนั้นมาด้วย
echo ============================================================
pause
