@echo off
chcp 65001 >nul
echo ========================================================
echo        กำลังตรวจสอบสถานะระบบซิงก์ MediaFire
echo ========================================================
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*sync_engine.py*' }; if ($p) { Write-Host ' [!] ระบบกำลังทำงานอยู่ในเบื้องหลังอยู่แล้ว (PID: ' $p.ProcessId ')' -ForegroundColor Green; exit 1 } else { exit 0 }"
if %errorlevel% neq 0 (
    echo.
    echo ระบบทำงานอยู่แล้ว ไม่จำเป็นต้องเปิดซ้ำ
    timeout /t 3 >nul
    exit /b 0
)

echo.
echo กำลังเริ่มต้นระบบซิงก์ข้อมูลสองทิศทาง (Real-Time Background Sync)...
start "" wscript.exe "%~dp0Launch-Sync-Background.vbs"
timeout /t 2 >nul
echo ระบบเริ่มทำงานเรียบร้อยแล้ว ตรวจสอบสถานะได้ที่ Status-Sync.bat
timeout /t 2 >nul
