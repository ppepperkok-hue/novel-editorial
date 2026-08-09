Set ws = CreateObject("WScript.Shell")
ws.CurrentDirectory = "C:\Users\Administrator\Documents\Codex\2026-08-09\new-chat-2\outputs\novel-pipeline\desktop"
ws.Run """C:\Users\Administrator\Documents\Codex\2026-08-09\new-chat-2\outputs\novel-pipeline\desktop\node_modules\electron\dist\electron.exe"" ""C:\Users\Administrator\Documents\Codex\2026-08-09\new-chat-2\outputs\novel-pipeline\desktop""", 1, False
