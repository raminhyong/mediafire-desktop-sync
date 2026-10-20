$startupFolder = [Environment]::GetFolderPath('Startup')
$shortcutPath = Join-Path $startupFolder "MediaFire-Sync.lnk"
$scriptDir = $PSScriptRoot

$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "wscript.exe"
$shortcut.Arguments = "`"$scriptDir\Launch-Sync-Background.vbs`""
$shortcut.IconLocation = "$scriptDir\mediafire.ico,0"
$shortcut.WorkingDirectory = "$scriptDir"
$shortcut.Description = "MediaFire Automatic Background Sync Service"
$shortcut.Save()

Write-Output "Successfully registered MediaFire Sync to Windows Startup:"
Write-Output $shortcutPath
