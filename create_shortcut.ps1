$wsh = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$scriptDir = $PSScriptRoot

# 1. Cloud Web App Shortcut
$shortcutPath = Join-Path $desktop "MediaFire Cloud.lnk"
$shortcut = $wsh.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "wscript.exe"
$shortcut.Arguments = "`"$scriptDir\Launch-MediaFire.vbs`""
$shortcut.IconLocation = "$scriptDir\mediafire.ico,0"
$shortcut.Description = "MediaFire Cloud Desktop Application"
$shortcut.WorkingDirectory = $scriptDir
$shortcut.Save()

# 2. Local Sync Folder Shortcut
$syncDir = Join-Path $scriptDir "MediaFire_Sync"
if (-not (Test-Path $syncDir)) {
    New-Item -ItemType Directory -Path $syncDir | Out-Null
}

$folderShortcutPath = Join-Path $desktop "MediaFire Sync Folder.lnk"
$folderShortcut = $wsh.CreateShortcut($folderShortcutPath)
$folderShortcut.TargetPath = $syncDir
$folderShortcut.IconLocation = "$scriptDir\mediafire.ico,0"
$folderShortcut.Description = "MediaFire Local Sync Folder"
$folderShortcut.WorkingDirectory = $syncDir
$folderShortcut.Save()

Write-Output "Shortcuts created successfully on Desktop:"
Write-Output " [1] $shortcutPath"
Write-Output " [2] $folderShortcutPath"
