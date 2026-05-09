param(
    [switch]$SkipMap,
    [switch]$KeepExistingMap
)

$ErrorActionPreference = "Stop"

function Test-PortOpen {
    param([int]$Port)

    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $iar = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        $connected = $iar.AsyncWaitHandle.WaitOne(250, $false)
        if ($connected) {
            $client.EndConnect($iar)
        }
        $client.Close()
        return $connected
    }
    catch {
        return $false
    }
}

function Start-CommandWindow {
    param(
        [string]$Title,
        [string]$WorkingDirectory,
        [string]$Command
    )

    $escapedTitle = $Title.Replace("'", "''")
    $escapedCommand = $Command.Replace("'", "''")
    $windowCommand = "& { `$Host.UI.RawUI.WindowTitle = '$escapedTitle'; $escapedCommand }"

    Start-Process powershell.exe -WorkingDirectory $WorkingDirectory -ArgumentList @(
        "-NoExit",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        $windowCommand
    )
}

function Wait-ForPort {
    param(
        [int]$Port,
        [string]$Name,
        [int]$TimeoutSeconds = 30
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-PortOpen -Port $Port) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }

    Write-Warning "$Name did not answer on port $Port within $TimeoutSeconds seconds."
    return $false
}

function Get-ListeningProcessIds {
    param([int]$Port)

    @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
}

function Stop-LocalMapServer {
    param([string]$ExpectedRoot)

    foreach ($processId in Get-ListeningProcessIds -Port 5173) {
        $process = Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -eq [int]$processId }
        if ($process -and ($process.CommandLine -like "*$ExpectedRoot*")) {
            Write-Host "Restarting existing public map dev server (PID $processId)"
            Stop-Process -Id $processId -Force
        }
    }
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PublicMapRoot = Join-Path $RepoRoot "public_map"

Write-Host "Opening GovJobs local tools..." -ForegroundColor Cyan

if (-not (Test-PortOpen -Port 8501)) {
    Write-Host "Starting Streamlit dashboard on http://localhost:8501"
    Start-CommandWindow `
        -Title "GovJobs Streamlit Dashboard" `
        -WorkingDirectory $RepoRoot `
        -Command "python -m streamlit run app.py --server.port 8501"
}
else {
    Write-Host "Streamlit is already running on http://localhost:8501"
}

if (-not $SkipMap) {
    if (-not $KeepExistingMap) {
        Stop-LocalMapServer -ExpectedRoot $PublicMapRoot
        Start-Sleep -Milliseconds 500
    }
    if (-not (Test-PortOpen -Port 5173)) {
        Write-Host "Starting public map on http://localhost:5173/map"
        Start-CommandWindow `
            -Title "GovJobs Public Map" `
            -WorkingDirectory $PublicMapRoot `
            -Command "if (-not (Test-Path node_modules)) { npm install }; npm run dev -- --host 127.0.0.1"
    }
    else {
        Write-Host "Public map is already running on http://localhost:5173"
    }
}

$streamlitReady = Wait-ForPort -Port 8501 -Name "Streamlit"
if ($streamlitReady) {
    Start-Process "http://localhost:8501"
    Start-Process "http://localhost:8501/Settings"
}

if (-not $SkipMap) {
    $mapReady = Wait-ForPort -Port 5173 -Name "Public map"
    if ($mapReady) {
        Start-Process "http://localhost:5173/map"
    }
}

Write-Host "Done. You can close this launcher window." -ForegroundColor Green
Start-Sleep -Seconds 3
