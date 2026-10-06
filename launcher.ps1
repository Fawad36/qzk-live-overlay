param([string]$ServerUrl=$env:QZK_SERVER,[string]$Token=$env:QZK_TOKEN,[string]$Label=$env:QZK_LABEL,[string]$RepoRaw=$env:QZK_RAW_BASE)
$ErrorActionPreference='Stop'
if(-not $ServerUrl){$ServerUrl=Read-Host 'Server URL (enter auto for LAN discovery, or Laptop B URL e.g. http://192.168.1.10:9000)'}
if(-not $Token){$Token=Read-Host 'Session token'}
if(-not $Label){$Label=$env:COMPUTERNAME}
if(-not $RepoRaw){$RepoRaw=Read-Host 'Raw GitHub base URL (folder containing agent.py)'}
$RepoRaw=$RepoRaw.TrimEnd('/')
$Root=Join-Path $env:LOCALAPPDATA 'QZKOverlayAgent'; New-Item -ItemType Directory -Force -Path $Root | Out-Null
$Agent=Join-Path $Root 'agent.py'; $Req=Join-Path $Root 'requirements-agent.txt'
Invoke-WebRequest -UseBasicParsing -Uri ($RepoRaw+'/agent.py') -OutFile $Agent
Invoke-WebRequest -UseBasicParsing -Uri ($RepoRaw+'/requirements-agent.txt') -OutFile $Req
$Py=(Get-Command py -ErrorAction SilentlyContinue); if(-not $Py){$Py=(Get-Command python -ErrorAction SilentlyContinue)}
if(-not $Py){throw 'Python 3 is required.'}
& $Py.Source -m pip install -r $Req
& $Py.Source $Agent --server $ServerUrl --token $Token --label $Label --port 9000
