# ChatPulse Local Development Setup

This guide covers setting up the ChatPulse application using Docker for local development.

## Prerequisites

- Docker Desktop (Windows/Mac) or Docker Engine (Linux)
- Docker Compose (included with Docker Desktop)
- 4GB+ RAM available
- Ports 3000, 5432, 6379, 8000, 5555 available

## Quick Start

### 1. Clone and Setup

```bash
# Clone the repository
git clone <repository-url>
cd Bulk-Messaging

# Copy the environment configuration
cp .env.docker .env
```

### 2. Start the Environment

**Windows (PowerShell):**
```powershell
.\scripts\docker-start.ps1
```

**Linux/Mac (Bash):**
```bash
chmod +x scripts/docker-start.sh
./scripts/docker-start.sh
```

### 3. Verify Services

After startup, verify all services are running:

```bash
docker compose ps
```

Expected output:
| Service | Status | URL |
|---------|--------|-----|
| postgres | Up | localhost:5432 |
| redis | Up | localhost:6379 |
| backend | Up | localhost:8000 |
| frontend | Up | localhost:3000 |
| celery-worker | Up | - |
| celery-beat | Up | - |
| flower | Up (optional) | localhost:5555 |

### 4. Access the Application

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Flower (Celery Monitor)**: http://localhost:5555

## Service Details

### PostgreSQL
- **Port**: 5432
- **Database**: bulk_messaging
- **Credentials**: postgres/postgres
- **Data Volume**: `postgres_data` (persistent)

### Redis
- **Port**: 6379
- **Used for**: Cache, Celery broker, Celery results
- **Data Volume**: `redis_data` (persistent)

### Backend (FastAPI)
- **Port**: 8000
- **Hot Reload**: Enabled (code changes auto-reload)
- **API Documentation**: `/docs` (Swagger UI)

### Frontend (Next.js)
- **Port**: 3000
- **Hot Reload**: Enabled
- **API Proxy**: Proxies `/api/*` to backend

### Celery Worker
- **Queues**: bulk-messages, webhooks
- **Concurrency**: 2 workers
- **Auto-restart**: On crash

### Celery Beat
- **Scheduler**: Periodic tasks
- **Tasks**: Campaign scheduling, cleanup jobs

### Flower (Optional)
- **Port**: 5555
- **Purpose**: Celery monitoring UI
- **Access**: username: `admin`, password: `admin`

## Common Tasks

### View Logs
```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f celery-worker
```

### Restart a Service
```bash
docker compose restart backend
docker compose restart frontend
```

### Rebuild After Code Changes
```bash
docker compose up -d --build
```

### Clear All Data and Start Fresh
```bash
# Stop and remove containers and volumes
docker compose down -v

# Start fresh
docker compose up -d
```

### Run Migrations
```bash
# Run database migrations inside the backend container
docker compose exec backend python -m alembic upgrade head
```

### Create Admin User
```bash
docker compose exec backend python -c "
import asyncio
from app.services.user_service import create_user
from app.db import AsyncSessionLocal
async def main():
    async with AsyncSessionLocal() as session:
        user = await create_user(session, email='admin@localhost', password='admin123', full_name='Admin')
        print(f'Created admin user: {user.email}')
asyncio.run(main())
"
```

## Environment Variables

Key environment variables (already configured in `.env.docker`):

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | postgresql+asyncpg://postgres:postgres@postgres:5432/bulk_messaging |
| `REDIS_URL` | Redis connection string | redis://redis:6379/0 |
| `JWT_SECRET_KEY` | Secret for JWT tokens | dev-secret-key |
| `CORS_ORIGINS` | Allowed CORS origins | http://localhost:3000 |
| `NEXT_PUBLIC_API_URL` | Frontend API URL | http://localhost:8000 |

## Troubleshooting

### Containers won't start
```bash
# Check Docker status
docker info

# Check available resources
docker system df
```

### Port already in use
```bash
# Find and kill process using the port
# Windows
netstat -ano | findstr :3000
taskkill /PID <PID> /F

# Linux/Mac
lsof -i :3000
kill <PID>
```

### Database connection issues
```bash
# Check PostgreSQL logs
docker compose logs postgres

# Test connection
docker compose exec postgres psql -U postgres -c "SELECT 1"
```

### Frontend not loading
```bash
# Check frontend logs
docker compose logs frontend

# Verify backend is responding
curl http://localhost:8000/health
```

### Celery worker issues
```bash
# Check worker logs
docker compose logs celery-worker

# Verify Redis connection
docker compose exec redis redis-cli ping
```

## Development Tips

1. **Backend hot reload**: Changes to Python files in `app/` automatically reload the server.

2. **Frontend hot reload**: Changes to React/Next.js files in `frontend/` automatically reload.

3. **Database persistence**: Data is preserved across restarts. Use `-v` flag to reset.

4. **Flower monitoring**: Use Flower to monitor Celery task status and queue health.

5. **Debugging**: Add breakpoints in VS Code by attaching to the container process.

## Next Steps

After setup, you can:
- Access the frontend at http://localhost:3000
- Explore the API at http://localhost:8000/docs
- Monitor Celery tasks at http://localhost:5555

For production deployment, refer to `LAUNCH_AND_DEPLOYMENT_PLAN.md`.