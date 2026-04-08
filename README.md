# Bulk Messaging Backend

Production-oriented FastAPI backend scaffold with async routing, CORS middleware, and PostgreSQL-ready SQLAlchemy setup.

## Project Structure

```
app/
  main.py
  core/
  db.py
  routes/
  models/
  schemas/
  services/
```

## Quick Start

1. Create and activate a virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and update values as needed.
4. Run the API:
   ```bash
   uvicorn app.main:app --reload
   ```

## Health Check

- `GET /` returns service health payload.

## Queue Engine (Celery + Redis)

1. Ensure Redis is running and `REDIS_URL` is configured.
2. Start API server:
   ```bash
   uvicorn app.main:app --reload
   ```
3. Start Celery worker:
   ```bash
   celery -A app.worker.celery_app worker --loglevel=info
   ```

### Bulk Send Endpoints

- `POST /bulk-send` executes synchronous bulk send.
- `POST /bulk-send/queue` enqueues a bulk send job and returns a workspace-scoped `job_id`.
- `GET /bulk-send/queue/{job_id}` returns queue job status and final counts when completed.

## Notes

- Database configuration uses `DATABASE_URL` and is ready for async PostgreSQL via `asyncpg`.
- CORS origins are controlled by `CORS_ORIGINS` as a comma-separated list.
