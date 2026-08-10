Set fso = CreateObject("Scripting.FileSystemObject")
Set ws = CreateObject("WScript.Shell")
base = fso.GetParentFolderName(WScript.ScriptFullName)
desktopDir = base & "\desktop"
exe = desktopDir & "\node_modules\electron\dist\electron.exe"
ws.CurrentDirectory = desktopDir
ws.Run """" & exe & """ """ & desktopDir & """", 1, False
