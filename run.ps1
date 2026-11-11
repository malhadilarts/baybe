param([switch]$Bg)
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $dir "backend"
if ($Bg) {
  Start-Process -FilePath "python" -ArgumentList "-m","uvicorn","main:app","--host","127.0.0.1","--port","7890" -WorkingDirectory $backend -WindowStyle Hidden
  Write-Host "Bay Be started on http://127.0.0.1:7890"
} else {
  Set-Location $backend
  python -m uvicorn main:app --host 127.0.0.1 --port 7890
}
