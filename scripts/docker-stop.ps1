# ChatPulse Docker Stop Script (PowerShell)

$ErrorActionPreference = "Stop"

Write-Host "🛑 Stopping ChatPulse Development Environment..." -ForegroundColor Yellow

# Stop and remove containers
docker compose down

Write-Host "✅ All services stopped and removed." -ForegroundColor Green
Write-Host ""
Write-Host "Note: Data volumes are preserved. To remove data:" -ForegroundColor Gray
Write-Host "  docker compose down -v" -ForegroundColor Gray