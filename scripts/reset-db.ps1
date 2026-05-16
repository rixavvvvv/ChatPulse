# ChatPulse Database Reset Script (PowerShell)
# This script resets the database and re-runs bootstrap

$ErrorActionPreference = "Stop"

Write-Host "🔄 Resetting ChatPulse Database..." -ForegroundColor Yellow

# Check if containers are running
$running = docker compose ps --format json 2>$null | ConvertFrom-Json | Where-Object { $_.Service -eq "backend" -and $_.State -eq "running" }

if (-not $running) {
    Write-Host "❌ Backend container is not running. Please start the environment first:" -ForegroundColor Red
    Write-Host "  docker compose up -d" -ForegroundColor Gray
    exit 1
}

Write-Host "Running bootstrap with reset..." -ForegroundColor Yellow

# Run the bootstrap with reset flag
docker compose exec -T backend python -m app.bootstrap.bootstrap --reset

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✅ Database reset and re-bootstrap complete!" -ForegroundColor Green
    Write-Host ""
    Write-Host "You can now access the application with fresh demo data." -ForegroundColor White
} else {
    Write-Host "❌ Bootstrap failed" -ForegroundColor Red
    exit 1
}