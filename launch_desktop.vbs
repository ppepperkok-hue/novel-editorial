Set fso = CreateObject("Scripting.FileSystemObject")
Set ws = CreateObject("WScript.Shell")
base = fso.GetParentFolderName(WScript.ScriptFullName)
desktopDir = base & "\desktop"
exe = desktopDir & "\node_modules\electron\dist\electron.exe"
If Not fso.FileExists(exe) Then
  MsgBox "Electron 未安装，请先在 desktop 目录运行 npm install。", 48, "文学编辑部"
  WScript.Quit 1
End If
ws.CurrentDirectory = desktopDir
ws.Run """" & exe & """ """ & desktopDir & """", 1, False
