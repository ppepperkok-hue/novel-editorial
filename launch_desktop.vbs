Set fso = CreateObject("Scripting.FileSystemObject")
Set ws = CreateObject("WScript.Shell")
base = fso.GetParentFolderName(WScript.ScriptFullName)
desktopDir = base & "\desktop"
exe = desktopDir & "\node_modules\electron\dist\electron.exe"
If Not fso.FileExists(exe) Then
  MsgBox "Electron is not installed. Run npm install in the desktop directory first.", 48, "Novel Editorial"
  WScript.Quit 1
End If
ws.CurrentDirectory = desktopDir
ws.Run """" & exe & """ """ & desktopDir & """", 1, False
