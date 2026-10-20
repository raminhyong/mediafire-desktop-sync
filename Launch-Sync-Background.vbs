Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

currentDir = FSO.GetParentFolderName(WScript.ScriptFullName)
pythonExe = currentDir & "\.venv\Scripts\python.exe"
syncScript = currentDir & "\sync_engine.py"

WshShell.CurrentDirectory = currentDir
WshShell.Run """" & pythonExe & """ """ & syncScript & """", 0, False
