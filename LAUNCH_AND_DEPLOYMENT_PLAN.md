# ChatPulse — Scalability, Launch & Deployment Plan

> **Goal**: Take the current MVP to a production-ready, scalable SaaS and launch ASAP.  
> **Last updated**: 2026-05-11

---

## Part A: Scalability & Launch Roadmap

### Phase 1: Production Hardening (Week 1–2) — CRITICAL PATH

These are **blockers** — nothing ships without them.

#### 1.1 Database Migrations (Alembic)
- [ ] Install `alembic` and initialize with async PostgreSQL support
- [ ] Generate initial migration from current models
- [ ] Remove all `ALTER TABLE` / `INSERT` statements from `init_db()` in `db.py`
- [ ] Keep `init_db()` to only run `alembic upgrade head`
- **Why**: Current `create_all` + raw SQL approach will break in production with schema changes

#### 1.2 Environment & Config Hardening
- [ ] Generate secure random keys for `JWT_SECRET_KEY`, `META_CREDENTIALS_ENCRYPTION_KEY`
- [ ] Switch to a proper encryption library (e.g., `cryptography` Fernet) instead of custom XOR keystream
- [ ] Add `ENVIRONMENT` flag (`development`/`staging`/`production`) with behavior switches
- [ ] Validate all required secrets are set on startup in production mode
- [ ] Add structured JSON logging (replace `print`/basic `logging`)

#### 1.3 Auth & Security
- [ ] Add refresh token flow (current 60-min JWT = poor UX)
- [ ] Implement password reset via email (use Resend/SendGrid)
- [ ] Add email verification on registration
- [ ] Add CSRF protection for cookie-based flows
- [ ] Rate limit login attempts (Redis-based)
- [ ] Add API key auth option for programmatic access

#### 1.4 Error Handling & Observability
- [ ] Add global exception handler middleware in FastAPI
- [ ] Add request ID middleware for trace correlation
- [ ] Set up Sentry for error tracking (both backend + frontend)
- [ ] Add health check endpoints: `/health/ready` (DB + Redis + Celery ping)
- [ ] Add structured logging with correlation IDs

---

### Phase 2: Feature Completeness (Week 2–4)

#### 2.1 Campaign Scheduling
- [ ] Implement `schedule_at` in campaign queue — Celery `eta` parameter
- [ ] Add scheduler UI on campaigns page (date/time picker)
- [ ] Add campaign cancel/pause functionality

#### 2.2 Template Management
- [ ] Template editing (update draft templates)
- [ ] Template deletion
- [ ] Template duplication/clone
- [ ] Auto-poll Meta for status changes (background Celery beat task)
- [ ] Template preview with sample data

#### 2.3 Contact Management
- [ ] Contact editing and deletion
- [ ] Tag-based filtering for campaign audience selection
- [ ] Contact search and pagination
- [ ] Contact groups / segments
- [ ] Export contacts to CSV
- [ ] Duplicate phone detection on import
p
#### 2.4 Team Collaboration
- [ ] Invite team members to workspace (email invitation flow)
- [ ] Role-based permissions UI
- [ ] Workspace settings page
- [ ] Activity audit log

#### 2.5 Admin Dashboard (Frontend)
- [ ] Admin layout and pages at `/admin/*`
- [ ] User management UI
- [ ] Plan management UI
- [ ] Global analytics / usage monitoring
- [ ] Workspace overview

---

### Phase 3: Scalability Architecture (Week 3–5)

#### 3.1 Database Scaling
- [ ] Add proper indexes for all query patterns (check EXPLAIN ANALYZE)
- [ ] Add connection pooling via PgBouncer for production
- [ ] Increase `DATABASE_POOL_SIZE` for production (current: 2)
- [ ] Partition `message_events` and `message_tracking` by month (for high-volume workspaces)
- [ ] Add pagination to all list endpoints (contacts, campaigns, templates, events)
- [ ] Add database read replicas for analytics queries

#### 3.2 Queue Scaling
- [ ] Split Celery queues: `campaigns`, `bulk-sends`, `webhooks`, `scheduled`
- [ ] Add Celery Beat for periodic tasks (template sync, usage reports, cleanup)
- [ ] Add dead letter queue for permanently failed messages
- [ ] Implement campaign chunking — batch audience into sub-tasks for parallelism
- [ ] Add Flower for Celery monitoring
- [ ] Consider switching to Redis Streams or BullMQ for better job visibility

#### 3.3 Caching
- [ ] Cache template lookups (Redis, 5-min TTL)
- [ ] Cache workspace meta credentials (Redis, with invalidation on update)
- [ ] Cache billing snapshots per billing cycle (invalidate on usage increment)
- [ ] Add ETag/If-None-Match for list endpoints

#### 3.4 API Performance
- [ ] Add response compression (gzip middleware)
- [ ] Add API rate limiting per user/workspace (return `Retry-After` headers)
- [ ] Add API versioning (`/api/v1/`)
- [ ] Add OpenAPI docs customization for public API

---

### Phase 4: Monetization & Launch (Week 4–6)

#### 4.1 Payment Integration
- [ ] Integrate Razorpay (India) or Stripe for plan subscriptions
- [ ] Subscription lifecycle: create → active → renewal → cancellation
- [ ] Webhook handler for payment status updates
- [ ] Grace period for `past_due` subscriptions
- [ ] Invoice generation (PDF)
- [ ] Plan upgrade/downgrade with prorated billing

#### 4.2 Landing Page & Marketing
- [ ] Public landing page (features, pricing, testimonials)
- [ ] SEO optimization
- [ ] Documentation / knowledge base
- [ ] API documentation for developers

#### 4.3 Compliance
- [ ] Add opt-in/opt-out tracking for contacts (WhatsApp compliance)
- [ ] GDPR data export/deletion endpoints
- [ ] Terms of Service and Privacy Policy
- [ ] WhatsApp Business Policy compliance checks
- [ ] Message content moderation

---

## Part B: Deployment Plan

### Architecture Diagram

```
                    ┌──────────────┐
                    │   Cloudflare  │  (DNS + CDN + DDoS)
                    │     CDN       │
                    └──────┬───────┘
                           │
              ┌────────────┴────────────┐
              │                         │
     ┌────────▼────────┐     ┌─────────▼─────────┐
     │  Vercel/Netlify  │     │   VPS / Cloud      │
     │  (Frontend)      │     │   (Backend)        │
     │  Next.js SSR     │     │                    │
     └─────────────────┘     │  ┌──────────────┐  │
                              │  │  Nginx       │  │
                              │  │  (reverse    │  │
                              │  │   proxy)     │  │
                              │  └──────┬───────┘  │
                              │         │          │
                              │  ┌──────▼───────┐  │
                              │  │  Gunicorn +   │  │
                              │  │  Uvicorn      │  │
                              │  │  Workers      │  │
                              │  └──────┬───────┘  │
                              │         │          │
                              │  ┌──────▼───────┐  │
                              │  │  Celery       │  │
                              │  │  Workers (2+) │  │
                              │  └──────────────┘  │
                              └────────────────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │                  │                   │
           ┌───────▼───────┐  ┌───────▼───────┐  ┌──────▼──────┐
           │  PostgreSQL    │  │    Redis       │  │  S3/Spaces   │
           │  (Managed)     │  │  (Managed)     │  │  (Media)     │
           └───────────────┘  └───────────────┘  └─────────────┘
```

### Option A: Budget VPS Deployment (~$20–40/month) — Recommended for Launch

**Provider**: DigitalOcean / Hetzner / AWS Lightsail

#### Infrastructure
| Component | Spec | Monthly Cost |
|-----------|------|-------------|
| VPS (API + Workers) | 2 vCPU, 4GB RAM, 80GB SSD | ~$20 |
| Managed PostgreSQL | Basic (1GB RAM, 10GB) | ~$15 |
| Managed Redis | Basic (25MB) | ~$10 |
| Frontend | Vercel Free Tier | $0 |
| Domain + SSL | Cloudflare Free | $0 |
| **Total** | | **~$45/month** |

#### Deployment Steps

**Step 1: Dockerize the Application**
```dockerfile
# Backend Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini .
CMD ["gunicorn", "app.main:app", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
```

```yaml
# docker-compose.yml
version: '3.8'
services:
  api:
    build: .
    ports: ["8000:8000"]
    env_file: .env
    depends_on: [postgres, redis]
    command: >
      sh -c "alembic upgrade head &&
             gunicorn app.main:app -w 2 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000"

  celery-worker:
    build: .
    env_file: .env
    depends_on: [postgres, redis]
    command: celery -A app.worker:celery_app worker --loglevel=info --concurrency=4

  celery-beat:
    build: .
    env_file: .env
    depends_on: [redis]
    command: celery -A app.worker:celery_app beat --loglevel=info

  postgres:
    image: postgres:16-alpine
    volumes: [pgdata:/var/lib/postgresql/data]
    environment:
      POSTGRES_DB: bulk_messaging
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${DB_PASSWORD}

  redis:
    image: redis:7-alpine
    volumes: [redisdata:/data]

volumes:
  pgdata:
  redisdata:
```

**Step 2: Nginx Reverse Proxy**
```nginx
server {
    listen 443 ssl http2;
    server_name api.chatpulse.io;

    ssl_certificate /etc/letsencrypt/live/api.chatpulse.io/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.chatpulse.io/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Step 3: Frontend on Vercel**
```bash
cd frontend
npx vercel --prod
# Set env: NEXT_PUBLIC_API_URL=https://api.chatpulse.io
```

**Step 4: CI/CD with GitHub Actions**
```yaml
# .github/workflows/deploy.yml
name: Deploy
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: SSH Deploy
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.VPS_HOST }}
          username: deploy
          key: ${{ secrets.VPS_SSH_KEY }}
          script: |
            cd /opt/chatpulse
            git pull origin main
            docker compose build
            docker compose up -d
            docker compose exec api alembic upgrade head
```

### Option B: Cloud-Native (AWS/GCP) — For Scale

| Component | Service | Notes |
|-----------|---------|-------|
| API | AWS ECS Fargate / GCP Cloud Run | Auto-scaling containers |
| Workers | ECS Fargate (separate task definition) | Scale independently |
| Database | AWS RDS PostgreSQL / GCP Cloud SQL | Managed, auto-backup |
| Cache/Queue | AWS ElastiCache Redis / GCP Memorystore | Managed Redis |
| Frontend | Vercel / AWS Amplify | Edge CDN |
| Media | S3 / GCP Cloud Storage | Template media |
| Monitoring | CloudWatch / GCP Monitoring + Sentry | — |
| CI/CD | GitHub Actions → ECR → ECS deploy | — |

---

### Deployment Checklist

#### Pre-Launch
- [ ] All env vars set with production values
- [ ] `JWT_SECRET_KEY` is a 64+ char random string
- [ ] `META_CREDENTIALS_ENCRYPTION_KEY` is unique and backed up
- [ ] `WHATSAPP_PROVIDER=cloud`
- [ ] `DEBUG=false`, `ENVIRONMENT=production`
- [ ] Database backups configured (daily automated)
- [ ] SSL/TLS certificates active
- [ ] CORS origins set to production domain only
- [ ] Meta webhook callback URL points to production
- [ ] `META_APP_SECRET` set for webhook signature verification
- [ ] Alembic migrations run successfully
- [ ] Health check endpoints responding

#### Monitoring Setup
- [ ] Sentry DSN configured (backend + frontend)
- [ ] Uptime monitoring (UptimeRobot / Better Uptime)
- [ ] Database connection pool monitoring
- [ ] Redis memory monitoring
- [ ] Celery queue length alerts
- [ ] Disk space alerts
- [ ] Error rate alerting (>1% failure rate)

#### Post-Launch
- [ ] Verify webhook delivery (Meta + Shopify)
- [ ] Send test campaign end-to-end
- [ ] Verify billing enforcement works
- [ ] Monitor error rates for 48 hours
- [ ] Enable automated DB backups
- [ ] Document runbook for common operations

---

## Priority Order for Solo Developer

If you're working alone and want to launch fastest:

1. **Week 1**: Dockerize + Alembic + Deploy to VPS → you're live
2. **Week 2**: Payment integration (Razorpay) + Landing page → you can charge
3. **Week 3**: Campaign scheduling + Template editing → core UX polish
4. **Week 4**: Error tracking (Sentry) + Monitoring → sleep well at night
5. **Week 5+**: Team features, admin dashboard, contact segments → growth features
