$chrome = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
$tmp = 'C:\Users\Administrator\Documents\Codex\2026-08-09\new-chat-2\outputs\novel-pipeline\tools\chrome-profile'
$args = @(
  '--headless=new',
  '--remote-debugging-port=9333',
  "--user-data-dir=$tmp",
  '--no-first-run',
  '--disable-gpu',
  'about:blank'
)
$p = Start-Process -FilePath $chrome -ArgumentList $args -WindowStyle Hidden -PassThru
Write-Output ("chrome pid=" + $p.Id)
Start-Sleep -Seconds 3
try {
  $r = Invoke-WebRequest -Uri 'http://127.0.0.1:9333/json/version' -UseBasicParsing -TimeoutSec 5
  Write-Output $r.Content
} catch {
  Write-Output ("cdp err: " + $_.Exception.Message)
}
