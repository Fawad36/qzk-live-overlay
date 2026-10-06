$ErrorActionPreference='Stop'
$Port=9000
try {
  $rule=Get-NetFirewallRule -DisplayName 'QZK Overlay Server 9000' -ErrorAction SilentlyContinue
  if(-not $rule){ New-NetFirewallRule -DisplayName 'QZK Overlay Server 9000' -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow -Profile Private | Out-Null }
} catch { Write-Host 'Firewall rule was not changed. If another PC cannot connect, run this script as Administrator.' -ForegroundColor Yellow }
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port $Port
