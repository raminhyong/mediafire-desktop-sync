Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

currentDir = FSO.GetParentFolderName(WScript.ScriptFullName)
pythonwExe = currentDir & "\.venv\Scripts\pythonw.exe"
syncScript = currentDir & "\sync_engine.py"

WshShell.CurrentDirectory = currentDir
WshShell.Run """" & pythonwExe & """ """ & syncScript & """", 0, False
