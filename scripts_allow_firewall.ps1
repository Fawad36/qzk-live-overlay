# Run PowerShell as Administrator if Windows Firewall blocks LAN clients.
New-NetFirewallRule -DisplayName 'QZK Overlay Server 9000' -Direction Inbound -Protocol TCP -LocalPort 9000 -Action Allow -Profile Private
