@echo off
chcp 65001 >nul
echo [MediaFire Sync] กำลังเริ่มระบบซิงก์ข้อมูลสองทิศทางในเบื้องหลัง...
start "" wscript.exe "%~dp0Launch-Sync-Background.vbs"
timeout /t 2 >nul
echo [MediaFire Sync] ระบบซิงก์ทำงานแล้ว ตรวจสอบสถานะได้ที่ Status-Sync.bat
pause
