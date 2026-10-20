@echo off
chcp 65001 >nul
echo [MediaFire Sync] กำลังหยุดการทำงานของระบบซิงก์ข้อมูล...
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*sync_engine.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Output ('Stopped Process ID: ' + $_.ProcessId) }"
echo [MediaFire Sync] ระบบซิงก์ข้อมูลถูกหยุดเรียบร้อยแล้ว
pause
