# ChatPulse Docker Development Startup Script (PowerShell)

$ErrorActionPreference = "Stop"

Write-Host "🚀 Starting ChatPulse Development Environment..." -ForegroundColor Green

# Check if Docker is running
try {
    docker info 2>&1 | Out-Null
} catch {
    Write-Host "❌ Docker is not running. Please start Docker first." -ForegroundColor Red
    exit 1
}

# Check if Docker Compose is available
try {
    docker compose version 2>&1 | Out-Null
} catch {
    Write-Host "❌ Docker Compose is not available. Please install Docker Compose." -ForegroundColor Red
    exit 1
}

# Build and start services
Write-Host "📦 Building and starting services..." -ForegroundColor Yellow
docker compose build

Write-Host "▶️  Starting all services..." -ForegroundColor Yellow
docker compose up -d

# Wait for services to be healthy
Write-Host "⏳ Waiting for services to be ready..." -ForegroundColor Yellow

# Wait for PostgreSQL
Write-Host "  - Waiting for PostgreSQL..." -ForegroundColor Gray
$postgresReady = $false
$attempts = 0
while (-not $postgresReady -and $attempts -lt 30) {
    try {
        docker compose exec -T postgres pg_isready -U postgres 2>&1 | Out-Null
        $postgresReady = $true
    } catch {
        Start-Sleep -Seconds 2
        $attempts++
    }
}
if ($postgresReady) {
    Write-Host "  ✅ PostgreSQL is ready" -ForegroundColor Green
} else {
    Write-Host "  ❌ PostgreSQL failed to start" -ForegroundColor Red
}

# Wait for Redis
Write-Host "  - Waiting for Redis..." -ForegroundColor Gray
$redisReady = $false
$attempts = 0
while (-not $redisReady -and $attempts -lt 15) {
    try {
        docker compose exec -T redis redis-cli ping 2>&1 | Out-Null
        $redisReady = $true
    } catch {
        Start-Sleep -Seconds 2
        $attempts++
    }
}
if ($redisReady) {
    Write-Host "  ✅ Redis is ready" -ForegroundColor Green
} else {
    Write-Host "  ❌ Redis failed to start" -ForegroundColor Red
}

# Wait for backend
Write-Host "  - Waiting for Backend..." -ForegroundColor Gray
$backendReady = $false
$attempts = 0
while (-not $backendReady -and $attempts -lt 30) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 5 -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            $backendReady = $true
        }
    } catch {
        Start-Sleep -Seconds 5
        $attempts++
    }
}
if ($backendReady) {
    Write-Host "  ✅ Backend is ready" -ForegroundColor Green
} else {
    Write-Host "  ⚠️  Backend may not be ready yet (this is okay if it's still starting)" -ForegroundColor Yellow
}

# Wait for frontend
Write-Host "  - Waiting for Frontend..." -ForegroundColor Gray
$frontendReady = $false
$attempts = 0
while (-not $frontendReady -and $attempts -lt 30) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:3000" -UseBasicParsing -TimeoutSec 5 -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            $frontendReady = $true
        }
    } catch {
        Start-Sleep -Seconds 5
        $attempts++
    }
}
if ($frontendReady) {
    Write-Host "  ✅ Frontend is ready" -ForegroundColor Green
} else {
    Write-Host "  ⚠️  Frontend may not be ready yet (this is okay if it's still starting)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "🎉 ChatPulse is now running!" -ForegroundColor Green
Write-Host ""
Write-Host "Services:" -ForegroundColor White
Write-Host "  - Frontend:   http://localhost:3000" -ForegroundColor Cyan
Write-Host "  - Backend:    http://localhost:8000" -ForegroundColor Cyan
Write-Host "  - API Docs:   http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "  - Flower:     http://localhost:5555 (optional)" -ForegroundColor Cyan
Write-Host "  - PostgreSQL: localhost:5432" -ForegroundColor Cyan
Write-Host "  - Redis:      localhost:6379" -ForegroundColor Cyan
Write-Host ""
Write-Host "To view logs: docker compose logs -f" -ForegroundColor Gray
Write-Host "To stop:      docker compose down" -ForegroundColor Gray
Write-Host "To rebuild:   docker compose up -d --build" -ForegroundColor Gray