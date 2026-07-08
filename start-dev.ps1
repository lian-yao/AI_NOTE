param(
  [ValidateSet("mock", "real")]
  [string]$Backend = "real",

  [string]$HostAddress = "127.0.0.1",

  [int]$MockBackendPort = 8010,

  [int]$RealBackendPort = 8000,

  [int]$FrontendPort = 5173,

  [switch]$StrictPorts,

  [switch]$NoReload,

  [switch]$SeedMockDemo,

  [switch]$NoSeedMockFixture
)

$ErrorActionPreference = "Stop"

$RepoRoot = $PSScriptRoot
$FrontendDir = Join-Path $RepoRoot "frontend"

if (-not (Test-Path $FrontendDir)) {
  throw "Frontend directory not found: $FrontendDir"
}

function Resolve-BindAddress([string]$Address) {
  $ipAddress = $null
  if ([Net.IPAddress]::TryParse($Address, [ref]$ipAddress)) {
    return $ipAddress
  }

  $resolved = [Net.Dns]::GetHostAddresses($Address) |
    Where-Object { $_.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork } |
    Select-Object -First 1
  if (-not $resolved) {
    throw "Host address cannot be resolved: $Address"
  }
  return $resolved
}

$VenvRoot = Join-Path $RepoRoot ".venv"
$VenvPython = Join-Path $VenvRoot "Scripts\python.exe"

function Test-PortAvailable([string]$Address, [int]$Port) {
  $listener = $null
  try {
    $ip = Resolve-BindAddress $Address
    $listener = [Net.Sockets.TcpListener]::new($ip, $Port)
    $listener.Start()
    return $true
  }
  catch {
    return $false
  }
  finally {
    if ($listener) {
      $listener.Stop()
    }
  }
}

function Find-FreePort([string]$Address, [int]$StartPort) {
  for ($port = $StartPort; $port -lt ($StartPort + 100); $port++) {
    if (Test-PortAvailable $Address $port) {
      return $port
    }
  }
  throw "No free port found from $StartPort to $($StartPort + 99)."
}

function Test-BackendHealth([string]$BaseUrl) {
  try {
    $res = Invoke-RestMethod -Uri "$BaseUrl/health" -Method Get -TimeoutSec 2
    return [bool]$res
  }
  catch {
    return $false
  }
}

$RequestedBackendPort = if ($Backend -eq "mock") { $MockBackendPort } else { $RealBackendPort }
$BackendPort = $RequestedBackendPort
$ApiHostAddress = if ($HostAddress -eq "0.0.0.0" -or $HostAddress -eq "::") { "127.0.0.1" } else { $HostAddress }
$BackendApp = if ($Backend -eq "mock") { "mock_backend.app:app" } else { "app.main:app" }
$ApiBaseUrl = "http://${ApiHostAddress}:$BackendPort"
$ReloadArg = if ($NoReload) { "" } else { " --reload" }
$SeedMockFixture = $Backend -eq "mock" -and -not $NoSeedMockFixture
if ($SeedMockDemo) {
  $SeedMockFixture = $true
}
$SeedMockDemoValue = if ($SeedMockFixture) { "true" } else { "false" }
$StartBackend = $true
$Uv = Get-Command uv -ErrorAction SilentlyContinue
$Python = Get-Command python -ErrorAction SilentlyContinue
$Py = Get-Command py -ErrorAction SilentlyContinue

if (Test-Path $VenvPython) {
  $BackendRunner = "& `"$VenvPython`" -m uvicorn"
}
elseif ($Uv) {
  $BackendRunner = "uv run uvicorn"
}
elseif ($Python) {
  $BackendRunner = "python -m uvicorn"
}
elseif ($Py) {
  $BackendRunner = "py -m uvicorn"
}
else {
  throw "Neither uv nor Python was found. Install Python or add it to PATH before starting the backend."
}

if (-not (Test-PortAvailable $HostAddress $BackendPort)) {
  if (Test-BackendHealth $ApiBaseUrl) {
    Write-Host "Backend port $BackendPort is already serving /health; reusing it."
    $StartBackend = $false
  }
  elseif ($StrictPorts) {
    throw "Backend port $BackendPort is occupied or unavailable. Use another -RealBackendPort/-MockBackendPort, stop the existing process, or omit -StrictPorts."
  }
  else {
    $BackendPort = Find-FreePort $HostAddress ($RequestedBackendPort + 1)
    $ApiBaseUrl = "http://${ApiHostAddress}:$BackendPort"
    Write-Host "Backend port $RequestedBackendPort is occupied or unavailable; using $BackendPort instead."
  }
}

if (-not (Test-PortAvailable "0.0.0.0" $FrontendPort)) {
  if ($StrictPorts) {
    throw "Frontend port $FrontendPort is occupied or unavailable. Use another -FrontendPort, stop the existing process, or omit -StrictPorts."
  }
  $RequestedFrontendPort = $FrontendPort
  $FrontendPort = Find-FreePort "0.0.0.0" ($FrontendPort + 1)
  Write-Host "Frontend port $RequestedFrontendPort is occupied or unavailable; using $FrontendPort instead."
}

$BackendCommand = @"
`$Host.UI.RawUI.WindowTitle = 'AI_NOTE backend ($Backend)'
cd "$RepoRoot"
`$env:AI_NOTE_MOCK_SEED_DEMO = "$SeedMockDemoValue"
$BackendRunner $BackendApp$ReloadArg --host $HostAddress --port $BackendPort
"@

$FrontendCommand = @"
`$Host.UI.RawUI.WindowTitle = 'AI_NOTE frontend -> $Backend'
cd "$FrontendDir"
  `$env:VITE_BACKEND_MODE = "$Backend"
  `$env:VITE_FRONTEND_PORT = "$FrontendPort"
`$env:VITE_ENABLE_WORKSPACE_MOCK = "false"
npm run dev
"@

$Pwsh = Get-Command pwsh -ErrorAction SilentlyContinue
$PowerShellExe = if ($Pwsh) { $Pwsh.Source } else { (Get-Command powershell).Source }

function ConvertTo-EncodedCommand([string]$Command) {
  return [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($Command))
}

Write-Host "Starting AI_NOTE dev stack"
Write-Host "Backend mode : $Backend"
Write-Host "Backend API  : $ApiBaseUrl"
if ($StartBackend) {
  Write-Host "Backend run  : $BackendRunner"
}
else {
  Write-Host "Backend run  : already running"
}
Write-Host "Frontend     : http://localhost:$FrontendPort"
Write-Host ""

if ($StartBackend) {
  Start-Process -FilePath $PowerShellExe -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy",
    "Bypass",
    "-EncodedCommand",
    (ConvertTo-EncodedCommand $BackendCommand)
  )

  Start-Sleep -Seconds 1
}

Start-Process -FilePath $PowerShellExe -ArgumentList @(
  "-NoExit",
  "-ExecutionPolicy",
  "Bypass",
  "-EncodedCommand",
  (ConvertTo-EncodedCommand $FrontendCommand)
)
