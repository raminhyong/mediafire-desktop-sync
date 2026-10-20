Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

edgePath = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
edgePath64 = "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
chromePath = "C:\Program Files\Google\Chrome\Application\chrome.exe"
targetUrl = "https://www.mediafire.com/myfiles.php"

If FSO.FileExists(edgePath) Then
    WshShell.Run """" & edgePath & """ --app=""" & targetUrl & """", 1, False
ElseIf FSO.FileExists(edgePath64) Then
    WshShell.Run """" & edgePath64 & """ --app=""" & targetUrl & """", 1, False
ElseIf FSO.FileExists(chromePath) Then
    WshShell.Run """" & chromePath & """ --app=""" & targetUrl & """", 1, False
Else
    WshShell.Run targetUrl, 1, False
End If
