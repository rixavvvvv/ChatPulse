param(
    [int]$Port = 8010
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    Write-Error "Python executable not found at $pythonExe"
    exit 1
}

Push-Location $repoRoot
try {
    & $pythonExe -m uvicorn app.main:app --host 0.0.0.0 --port $Port --reload
}
finally {
    Pop-Location
}
