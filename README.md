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

Run backend : uvicorn app.main:app --reload
docke
Frontend: npm run dev

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

## Meta Webhook (Delivery Tracking)

- `GET /webhook/meta` performs Meta webhook verification using query parameters:
   - `hub.mode`
   - `hub.verify_token`
   - `hub.challenge`
- Alternate callback form supported:
   - `GET /whatsapp-webhook/{webhook_id}`
- `POST /webhook/meta` receives Meta webhook payloads and processes status events:
   - `delivered`
   - `read`
   - `failed`
- Alternate callback form supported:
   - `POST /whatsapp-webhook/{webhook_id}`

Additional webhook helper endpoint:
- `GET /webhook/meta/config`
  - Returns computed callback URL when `PUBLIC_BASE_URL` is configured
  - Indicates whether verify token and signature validation are configured

Set `META_WEBHOOK_VERIFY_TOKEN` in `.env` and configure the same token in your Meta app webhook settings.

Recommended production hardening:
- Set `META_APP_SECRET` in `.env`
- With `META_APP_SECRET`, webhook POST now verifies `X-Hub-Signature-256`

## Expose Backend Publicly For Meta Webhooks

Meta cannot call `localhost` directly. Expose your backend and use the public URL in Meta.

1. If ngrok is not already authenticated on this machine, add your authtoken once:
   ```powershell
   ngrok config add-authtoken <YOUR_NGROK_AUTH_TOKEN>
   ```
1. Start API on all interfaces:
   ```powershell
   ./scripts/start_api_public.ps1 -Port 8010
   ```
2. Start ngrok tunnel (if installed):
   ```powershell
   ./scripts/start_ngrok_tunnel.ps1 -Port 8010
   ```
3. Set `PUBLIC_BASE_URL` in `.env` to your tunnel URL and restart API.
4. Validate your webhook setup config:
   - `GET /webhook/meta/config`
5. Configure Meta webhook callback URL to:
   - `{PUBLIC_BASE_URL}/webhook/meta`
6. Subscribe Meta app webhook field:
   - `messages`

## Message Events + Analytics

- Message event rows are recorded with:
   - `id`
   - `campaign_id`
   - `contact_id`
   - `status` (`sent`, `delivered`, `read`, `failed`)
   - `timestamp`
- Workspace analytics endpoint:
   - `GET /analytics/messages`
   - Returns `total_sent`, `delivered_percentage`, `read_percentage`, and `failure_percentage`

## Admin + RBAC

- Global roles:
   - `super_admin`
   - `user`
- Workspace role:
   - `admin`

Configure bootstrap super admin email with `SUPER_ADMIN_EMAIL` in `.env`.

Super admin endpoints:
- `POST /admin/users` create user
- `GET /admin/users` list users
- `GET /admin/plans` list subscription plans
- `POST /admin/plans` create a subscription plan
- `PATCH /admin/users/{user_id}/role` assign role
- `PATCH /admin/users/{user_id}/subscription` assign subscription by `plan_id`
- `PATCH /admin/users/{user_id}/status` activate/deactivate user
- `GET /admin/workspaces` view all workspaces
- `GET /admin/usage/messages` monitor message usage by workspace and billing cycle

## Subscription System + Usage Tracking

- `plans` stores:
   - `name`
   - `message_limit`
   - `price`
- `user_subscriptions` stores:
   - `user_id`
   - `plan_id`
   - `status`
- `usage_tracking` stores:
   - `workspace_id`
   - `messages_sent`
   - `billing_cycle` (format: `YYYY-MM`)

Usage tracking is incremented automatically whenever a `sent` message event is recorded.

## Critical Product Flows

### Flow 1: User Onboarding

- Admin creates user: `POST /admin/users`
- User logs in: `POST /auth/login`
- User creates workspace: `POST /workspaces`
- User switches workspace JWT context: `POST /workspaces/switch`
- User connects Meta credentials: `POST /meta/connect`
- Readiness check: `GET /onboarding/status`

### Flow 2: Campaign Execution

- Create campaign draft: `POST /campaigns`
- Bind audience snapshot: `POST /campaigns/{campaign_id}/audience`
- Queue now or schedule: `POST /campaigns/{campaign_id}/queue` with optional `schedule_at`
- Queue status: `GET /campaigns/{campaign_id}/queue/{job_id}`
- Live progress: `GET /campaigns/{campaign_id}/progress`
- Webhook updates: `POST /webhook/meta`
- Dashboard analytics data:
   - `GET /analytics/messages`
   - `GET /analytics/messages/timeline`

### Flow 3: Billing

- Usage tracked in `usage_tracking` by billing cycle when `sent` events are recorded.
- Limit checks enforced before sends and queueing in:
   - `POST /send-message`
   - `POST /bulk-send/queue`
   - `POST /campaigns/{campaign_id}/queue`
   - Campaign worker runtime loop
- Billing usage endpoint: `GET /billing/usage`

## Notes

- Database configuration uses `DATABASE_URL` and is ready for async PostgreSQL via `asyncpg`.
- CORS origins are controlled by `CORS_ORIGINS` as a comma-separated list.
