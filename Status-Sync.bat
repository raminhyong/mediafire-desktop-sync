@echo off
chcp 65001 >nul
cls
echo ========================================================
echo          สถานะระบบซิงก์ข้อมูล MediaFire Cloud
echo ========================================================
echo.
powershell -Command "$p = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*sync_engine.py*' }; if ($p) { Write-Host ' [● RUNNING] ระบบซิงก์กำลังทำงานอยู่ในเบื้องหลัง (PID: ' $p.ProcessId ')' -ForegroundColor Green } else { Write-Host ' [○ STOPPED] ระบบซิงก์ไม่ได้ทำงานอยู่ในขณะนี้' -ForegroundColor Yellow }"
echo.
echo ---------------- บันทึกการทำงานล่าสุด (Last Logs) ----------------
if exist "%~dp0sync_activity.log" (
    powershell -Command "Get-Content -Path '%~dp0sync_activity.log' -Tail 15 -Encoding utf8"
) else (
    echo ยังไม่มีไฟล์บันทึกกิจกรรม
)
echo.
echo ========================================================
echo [1] เปิดโฟลเดอร์ซิงก์  [2] สตาร์ทระบบ  [3] หยุดระบบ  [4] ออก
echo ========================================================
choice /c 1234 /n /m "เลือกเมนู (1-4): "
if errorlevel 4 goto end
if errorlevel 3 call "%~dp0Stop-Sync.bat" & goto end
if errorlevel 2 call "%~dp0Start-Sync.bat" & goto end
if errorlevel 1 start "" explorer.exe "%~dp0MediaFire_Sync" & goto end
:end
