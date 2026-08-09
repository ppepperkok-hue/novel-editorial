Set ws = CreateObject("WScript.Shell")
ws.CurrentDirectory = "E:\code\novel-pipeline\desktop"
ws.Run """E:\code\novel-pipeline\desktop\node_modules\electron\dist\electron.exe"" ""E:\code\novel-pipeline\desktop""", 1, False
