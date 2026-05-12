# ChatPulse — Bulk Messaging Platform — Project Context

> **Purpose**: This document gives any new coding agent full context of the project so it can continue work without losing progress. Last updated: 2026-05-12.

---

## 1. Project Overview

**ChatPulse** is a multi-tenant SaaS platform for WhatsApp bulk messaging built on the **Meta Cloud API**. It has evolved from a simple bulk messaging sender into an event-driven WhatsApp automation and customer engagement infrastructure platform.

The platform now follows:
- Asynchronous queue-driven processing
- Centralized message dispatching
- Event ingestion + replay architecture
- Domain event normalization
- Contact intelligence systems
- Dynamic segmentation
- Scalable webhook processing
- Centralized delivery tracking

**Repository**: `d:\On-going Projects\Bulk Messaging`
**Git Remote**: `rixavvvvv/ChatPulse`

### Git History (4 commits)
```
0054f64 Refactor code for improved readability and consistency
c0387fd Campaign creation and forwarding feature added
5e3d197 Campaign architecture creation
e18b716 first commit
```

---

## 2. Tech Stack

### Backend
| Component | Technology | Version |
|-----------|-----------|---------|
| Framework | FastAPI | ≥0.116 |
| Server | Uvicorn | ≥0.34 |
| ORM | SQLAlchemy (async) | ≥2.0.40 |
| Database | PostgreSQL | via asyncpg ≥0.30 |
| Queue | Celery + Redis | celery ≥5.4 |
| HTTP Client | httpx | ≥0.27.2 |
| Auth | PyJWT + bcrypt | JWT HS256 |
| Settings | pydantic-settings | ≥2.8 |
| Encryption | Custom XOR keystream (SHA-256 based) | in `core/security.py` |

### Frontend
| Component | Technology | Version |
|-----------|-----------|---------|
| Framework | Next.js | 14.2.12 |
| Language | TypeScript | ^5.6.2 |
| Styling | Tailwind CSS | ^3.4.13 |
| Icons | lucide-react | ^0.469 |
| UI Primitives | Custom (class-variance-authority + clsx + tailwind-merge) | — |

### Infrastructure (Development)
- **Database**: PostgreSQL on localhost:5432, DB name `bulk_messaging`
- **Redis**: localhost:6379/0
- **API**: uvicorn on port 8000 (dev) or 8010 (public via ngrok)
- **Frontend**: Next.js dev server on port 3000
- **Tunnel**: ngrok for Meta webhook callbacks

---

## 3. Project Structure

```
d:\On-going Projects\Bulk Messaging\
├── .env / .env.example          # Environment configuration
├── requirements.txt             # Python dependencies
├── README.md                    # Existing docs
├── LAUNCH_AND_DEPLOYMENT_PLAN.md # Deployment plan
├── docs/
│   └── architecture/            # Detailed architecture docs
│       ├── queue-topology.md
│       ├── event-lifecycle.md
│       ├── message-dispatch.md
│       ├── segment-engine.md
│       ├── webhook-processing.md
│       ├── webhook-idempotency.md
│       ├── campaign-runtime.md
│       ├── worker-scaling.md
│       ├── database-boundaries.md
│       ├── analytics-pipeline.md
│       ├── service-contracts.md
│       ├── observability.md
│       └── CELERY_CRASH_RECOVERY.md
├── scripts/
│   ├── start_api_public.ps1     # Start API on 0.0.0.0 for webhook testing
│   └── start_ngrok_tunnel.ps1   # ngrok tunnel helper
├── app/                         # FastAPI backend
│   ├── main.py                  # App factory + lifespan (init_db on startup)
│   ├── db.py                    # SQLAlchemy async engine, session factory, init_db()
│   ├── worker.py                # Celery worker entry point
│   ├── core/
│   │   ├── config.py            # Pydantic Settings (all env vars + validators)
│   │   └── security.py          # encrypt_secret / decrypt_secret (XOR keystream)
│   ├── dependencies/
│   │   ├── auth.py              # get_current_user, require_super_admin
│   │   └── workspace.py         # get_current_workspace, require_workspace_admin
│   ├── models/                  # SQLAlchemy ORM models (29 models)
│   ├── schemas/                 # Pydantic request/response schemas (22 files)
│   ├── routes/                  # FastAPI routers (23 routers)
│   ├── services/                # Business logic layer (38 services)
│   └── queue/
│       ├── celery_app.py        # Celery config (broker=Redis, JSON serializer)
│       ├── tasks.py             # Celery tasks (bulk.send, campaign.send, etc.)
│       ├── webhook_tasks.py     # Webhook processing tasks
│       ├── registry.py          # Queue routing registry
│       └── rate_limit.py        # Redis-based rate limiting
└── frontend/                    # Next.js 14 frontend
    ├── package.json
    ├── app/
    │   ├── layout.tsx           # Root layout
    │   ├── page.tsx             # Landing redirect
    │   ├── globals.css
    │   ├── (auth)/
    │   │   ├── login/page.tsx
    │   │   └── signup/page.tsx
    │   └── (workspace)/
    │       ├── layout.tsx       # Sidebar + header + workspace guard
    │       ├── dashboard/page.tsx
    │       ├── campaigns/page.tsx       # Full campaign CRUD UI
    │       ├── contacts/page.tsx
    │       ├── bulk-messaging/page.tsx
    │       ├── onboarding/page.tsx
    │       └── integrations/shopify/page.tsx
    ├── components/
    │   ├── sidebar-nav.tsx
    │   ├── workspace-switcher.tsx
    │   └── ui/ (button, card, input, table)
    └── lib/
        ├── api.ts               # apiRequest<T> generic fetch wrapper
        ├── session.ts           # localStorage session (chatpulse.session)
        └── utils.ts             # cn() helper
```

---

## 4. Database Schema (29 Tables)

### Core Entities
| Table | Key Columns | Notes |
|-------|------------|-------|
| `users` | id, email, password_hash, role (`super_admin`/`user`), subscription_plan, is_active, created_at | Auth + RBAC |
| `workspaces` | id, name, owner_id (FK→users), created_at | Multi-tenant isolation unit |
| `memberships` | id, user_id, workspace_id, role (`admin`/`member`) | UQ(user_id, workspace_id) |
| `contacts` | id, workspace_id, name, phone, tags (ARRAY), created_at | UQ(workspace_id, phone) |

### Messaging & Campaigns
| Table | Key Columns | Notes |
|-------|------------|-------|
| `templates` | id, workspace_id, name, body, body_text, language, category (MARKETING/UTILITY/AUTH), header_type, header_content, footer_text, buttons (JSONB), variables (JSONB), body_examples (JSONB), status (`draft`/`pending`/`approved`/`rejected`), meta_template_id, rejection_reason | UQ(workspace_id, name). Meta Graph API sync. |
| `campaigns` | id, workspace_id, template_id (FK), name, message_template, status (`draft`/`queued`/`running`/`completed`/`failed`), queued_job_id, success_count, failed_count, last_error | State machine transitions enforced |
| `campaign_contacts` | id, workspace_id, campaign_id, source_contact_id, idempotency_key, name, phone, delivery_status (`pending`/`sent`/`failed`/`skipped`), failure_classification, attempt_count, last_error | UQ(campaign_id, phone), UQ(campaign_id, idempotency_key) |
| `message_events` | id, workspace_id, campaign_id?, contact_id?, status (`sent`/`delivered`/`read`/`failed`), timestamp | Analytics aggregation source |
| `message_tracking` | id, workspace_id, campaign_id?, campaign_contact_id?, provider_message_id (UQ), recipient_phone, current_status, sent_at, delivered_at, read_at, failed_at, last_error, last_webhook_at, last_webhook_payload (JSONB) | Maps Meta wamid to internal state |

### Contact Intelligence
| Table | Key Columns | Notes |
|-------|------------|-------|
| `tags` | id, workspace_id, name, color, created_at | UQ(workspace_id, name) |
| `contact_tags` | id, workspace_id, contact_id, tag_id, created_at | UQ(workspace_id, contact_id, tag_id) |
| `attribute_definitions` | id, workspace_id, key, label, type, is_indexed, created_at | UQ(workspace_id, key) |
| `contact_attribute_values` | id, workspace_id, contact_id, attribute_definition_id, value_text/number/bool/date, updated_at | UQ(workspace_id, contact_id, attribute_definition_id) |
| `contact_notes` | id, workspace_id, contact_id, author_user_id, body, deleted_at, created_at | Soft delete via deleted_at |
| `contact_activities` | id, workspace_id, contact_id, actor_user_id, type, payload (JSONB), created_at | Append-only activity log |
| `contact_import_jobs` | id, workspace_id, created_by_user_id, original_filename, status, total_rows, processed_rows, inserted_rows, skipped_rows, failed_rows, error_message, celery_task_id, created_at, completed_at | CSV import tracking |
| `contact_import_rows` | id, job_id, row_number, raw (JSONB), status, error, created_at | UQ(job_id, row_number) |
| `segments` | id, workspace_id, name, status, definition (JSONB), approx_size, last_materialized_at, created_at, updated_at | UQ(workspace_id, name) |
| `segment_memberships` | id, workspace_id, segment_id, contact_id, materialized_at | UQ(workspace_id, segment_id, contact_id) |

### Queue & Event Infrastructure
| Table | Key Columns | Notes |
|-------|------------|-------|
| `webhook_ingestions` | id, workspace_id, source, event_type, raw_payload (JSONB), status, retry_count, error, celery_task_id, trace_id, client_ip, created_at, processed_at | Raw webhook storage with replay support |
| `domain_events` | id, workspace_id, event_type, payload (JSONB), created_at | Normalized event bus |
| `queue_dead_letters` | id, task_name, celery_task_id, exception_type, exception_message, task_kwargs (JSONB), retries_at_failure, max_retries, created_at, replayed_at | Failed worker payload storage |

### Billing & Subscriptions
| Table | Key Columns | Notes |
|-------|------------|-------|
| `plans` | id, name (UQ), message_limit, price | Seeded: free(1K/$0), pro(10K/$29), business(50K/$99), enterprise(200K/$299) |
| `user_subscriptions` | id, user_id (UQ), plan_id, status (`active`/`canceled`/`past_due`) | 1:1 per user |
| `usage_tracking` | id, workspace_id, messages_sent, billing_cycle (`YYYY-MM`) | UQ(workspace_id, billing_cycle). Auto-incremented on `sent` events. |

### Meta Integration
| Table | Key Columns | Notes |
|-------|------------|-------|
| `meta_credentials` | id, workspace_id (UQ), phone_number_id, access_token (encrypted), business_account_id | Encrypted at rest via XOR keystream |

### Ecommerce / Shopify
| Table | Key Columns | Notes |
|-------|------------|-------|
| `ecommerce_store_connections` | id, workspace_id, store_identifier (UQ), webhook_secret_encrypted, access_token_encrypted | Shopify store link |
| `ecommerce_event_template_maps` | id, workspace_id, event_type, template_id | UQ(workspace_id, event_type). Maps `order_created` → template |
| `order_webhook_delivery_logs` | id, workspace_id, store_connection_id?, phone, message_preview, status, error, attempts | Audit trail for order notifications |

---

## 5. Queue Architecture

### Active Queues
| Queue | Purpose |
|-------|---------|
| `bulk-messages` | Bulk messaging execution |
| `webhooks` | Webhook processing |
| `default` | Generic async jobs |
| `retries` | Retry scheduling |
| `dead-letter` | Failed jobs |

### Queue Tasks
| Task | Purpose |
|------|---------|
| `bulk.send_messages` | Async bulk send |
| `campaign.send` | Campaign execution with retry logic |
| `contacts.import_job` | CSV contact import processing |
| `segments.materialize` | Segment membership materialization |

### Queue Features
- Retry strategies with exponential backoff
- Dead-letter queue handling
- Queue routing registry
- Worker monitoring via `/admin/queues/inspect`
- Redis-based rate limiting (sliding window)
- Idempotency handling (inflight + sent keys)
- Replay capabilities for failed webhooks

### Worker Responsibilities
Workers handle campaign execution, webhook dispatch, CSV imports, segment materialization, retry processing, template synchronization, and delivery tracking updates.

---

## 6. Webhook Infrastructure

### Centralized Webhook Processing Flow
```
Webhook HTTP Request
→ Verification (HMAC-SHA256 / challenge)
→ Raw ingestion storage (webhook_ingestions)
→ Queue enqueue
→ Dispatcher worker
→ Domain event generation
→ Downstream processing
```

### Features Implemented
- **Provider-level idempotency**: Dual-layer dedupe using Redis SETNX + PostgreSQL UNIQUE constraints
- **Meta Webhooks**: signature verification, challenge verification, delivery status normalization, replay support
- **Shopify Webhooks**: HMAC verification, raw payload storage, replay support
- **Webhook Replay System**: Replay failed or dead ingestion records with idempotency guarantees

### Admin Endpoints
- `GET /admin/queues/dead-letters` — List failed worker payloads
- `POST /admin/queues/webhook-ingestions/replay` — Replay failed webhook ingestions

---

## 7. Contact Intelligence Architecture

### Features Implemented
- Normalized tags (`Tag`, `ContactTag`)
- Custom attributes (`AttributeDefinition`, `ContactAttributeValue`)
- Contact notes with soft delete (`ContactNote`)
- Append-only activities (`ContactActivity`)
- CSV imports with error tracking (`ContactImportJob`, `ContactImportRow`)
- Dynamic segmentation (`Segment`, `SegmentMembership`)
- Audience filtering with Filter DSL

### Segmentation Engine (Filter DSL)
Reusable JSON-based filter DSL supporting:
- Logical: `and`, `or`, `not`
- Comparison: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`
- Text: `contains`
- Set: `in`
- Tags: `has_tag`
- Attributes: `attr` (with typed comparisons)

Segment materialization runs asynchronously via `segments.materialize` task.

---

## 8. Message Dispatch Architecture

### Centralized Dispatch Pipeline
```txt
Campaign
→ Queue Worker
→ Dispatch Service (send_template_with_tracking)
→ Meta API
→ Tracking Registration
→ Message Event
→ Analytics
```

### Dispatch Flow
`send_template_with_tracking()` centralizes:
- Meta API sends
- Retries with exponential backoff
- Delivery tracking registration
- Message event emission
- Provider abstraction

### Delivery Tracking
Supports: `sent`, `delivered`, `read`, `failed` with webhook updates and provider message mapping.

---

## 9. System Boundaries

The platform is organized into bounded contexts with clear responsibilities:

### Contact Intelligence Boundary
**Responsibility**: Contact data, enrichment, and audience management

| Component | Files |
|-----------|-------|
| Models | `models/contact.py`, `models/contact_intelligence.py` |
| Services | `services/tag_service.py`, `services/contact_*_service.py`, `services/segment_*.py` |
| Routes | `routes/contacts.py`, `routes/tags.py`, `routes/segments.py` |

**Key Entities**: Contact, Tag, AttributeDefinition, ContactNote, ContactActivity, Segment

### Messaging Infrastructure Boundary
**Responsibility**: Message sending, tracking, and delivery

| Component | Files |
|-----------|-------|
| Models | `models/template.py`, `models/campaign.py`, `models/message_*.py` |
| Services | `services/whatsapp_service.py`, `services/message_dispatch_service.py` |
| Routes | `routes/campaigns.py`, `routes/bulk.py`, `routes/templates.py` |

**Key Entities**: Template, Campaign, CampaignContact, MessageTracking, MessageEvent

### Queue Infrastructure Boundary
**Responsibility**: Async task execution and worker management

| Component | Files |
|-----------|-------|
| Config | `queue/celery_app.py`, `queue/registry.py`, `queue/rate_limit.py` |
| Tasks | `queue/tasks.py`, `queue/webhook_tasks.py` |
| Services | `services/queue_service.py`, `services/queue_monitoring_service.py` |
| Routes | `routes/admin.py` (queues section) |

**Key Entities**: queue_dead_letters (for monitoring)

### Webhook Infrastructure Boundary
**Responsibility**: Incoming webhook ingestion, verification, and dispatch

| Component | Files |
|-----------|-------|
| Models | `models/webhook_ingestion.py`, `models/domain_event.py` |
| Services | `services/webhook_*.py` |
| Routes | `routes/webhook_meta.py`, `routes/webhook_order.py` |

**Key Entities**: WebhookIngestion, DomainEvent

### Ecommerce Automation Boundary
**Responsibility**: Shopify integration and order notifications

| Component | Files |
|-----------|-------|
| Models | `models/ecommerce.py` |
| Services | `services/ecommerce_store_service.py`, `services/order_webhook_service.py` |
| Routes | `routes/ecommerce.py` |

**Key Entities**: EcommerceStoreConnection, EcommerceEventTemplateMap, OrderWebhookDeliveryLog

### Analytics Infrastructure Boundary
**Responsibility**: Aggregations, rollups, and metrics (planned)

| Component | Files |
|-----------|-------|
| Services | `services/analytics_service.py`, `services/billing_service.py` |
| Routes | `routes/analytics.py`, `routes/billing.py` |

**Status**: Basic aggregates exist; rollups and event projections planned.

---

## 10. Domain Events

### Event Naming Convention
Events follow `{action}.{resource}` pattern (e.g., `message.sent`, `contact.created`).

### Event Taxonomy

#### Message Events
| Event | Trigger |
|-------|---------|
| `message.sent` | Message dispatched to Meta API |
| `message.delivered` | Webhook: `delivered` status |
| `message.read` | Webhook: `read` status |
| `message.failed` | Max retries or delivery failure webhook |

#### Contact Events
| Event | Trigger |
|-------|---------|
| `contact.created` | Contact upsert |
| `contact.updated` | Contact update |
| `contact.imported` | Import job completion |
| `contact.tag_added` | Tag assigned |
| `contact.tag_removed` | Tag removed |
| `contact.note_added` | Note created |
| `contact.note_deleted` | Note soft-deleted |

#### Campaign Events
| Event | Trigger |
|-------|---------|
| `campaign.created` | Campaign draft created |
| `campaign.started` | Campaign queued |
| `campaign.completed` | All messages processed |
| `campaign.failed` | Critical error during send |

#### Webhook Events
| Event | Trigger |
|-------|---------|
| `webhook.received` | Incoming webhook ingested |
| `webhook.processed` | Webhook processing complete |
| `webhook.failed` | Webhook processing failed |

#### Ecommerce Events
| Event | Trigger |
|-------|---------|
| `order.created` | Shopify order webhook |
| `order.notification_sent` | Template message dispatched |

### Event Payload Standard
```json
{
  "event_id": "uuid",
  "event_type": "message.sent",
  "workspace_id": 1,
  "timestamp": "2026-05-12T10:00:00Z",
  "trace_id": "abc123",
  "payload": {}
}
```

### Trace ID Architecture
- `trace_id` generated at webhook ingestion
- Stored in `webhook_ingestions.trace_id`
- Propagated through async tasks
- Future: OpenTelemetry instrumentation for distributed tracing

### Event Projections (Planned)
- Contact activity feed from `contact.*` events
- Campaign aggregates from `message.*` events
- Hourly/daily message count rollups

---

## 11. Realtime Architecture (Future Direction)

### Current State
No real-time updates exist. Campaigns poll progress via `GET /campaigns/{id}/progress`.

### Planned Architecture
```
┌─────────────┐
│  WebSocket  │  ← WebSocket gateway (future)
│  Gateway   │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Pub/Sub   │  ← Redis pub/sub or SSE
│  (Events)   │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Rooms    │  ← Workspace/Campaign rooms
│ (Broadcast)│
└─────────────┘
```

### Planned Components
- **WebSocket Gateway**: `ws://api/stream?workspace_id=X`
- **Room Architecture**: Join room by workspace/campaign/contact
- **Event Broadcasts**: Push updates on status changes
- **SSE Alternative**: Server-Sent Events for simpler clients

### Frontend Integration
- Connect WebSocket on authenticated session
- Join relevant rooms
- Update UI state on events
- Reconnection with backoff

---

## 12. Authentication & Authorization

- **JWT tokens** with `sub` (user_id) and `workspace_id` claims
- Token issued at login, refreshed via workspace switch
- **Global roles**: `super_admin`, `user`
- **Workspace roles**: `admin`, `member` (via `memberships` table)
- **Dependency injection**: `get_current_user` → `get_current_workspace` → validates membership
- Session stored in browser `localStorage` as `chatpulse.session` = `{access_token, workspace_id, role}`

---

## 10. API Endpoints (Complete)

### Auth (`/auth`)
- `POST /auth/login` — email/password → JWT
- `POST /auth/register` — create user account

### Workspaces (`/workspaces`)
- `POST /workspaces` — create workspace
- `GET /workspaces` — list user's workspaces
- `POST /workspaces/switch` — switch workspace context (new JWT)

### Onboarding (`/onboarding`)
- `GET /onboarding/status` — readiness check (has workspace, meta creds, contacts, template)

### Meta Credentials (`/meta`)
- `POST /meta/connect` — save/update Meta credentials (validates via Graph API)
- `GET /meta/status` — credential summary
- `GET /meta/webhook-config` — webhook callback URL + setup info
- `GET /meta/subscribed-apps` — WABA subscription status
- `POST /meta/subscribe-app` — auto-subscribe app to WABA

### Templates (`/templates`)
- `POST /templates` — create template (draft)
- `GET /templates` — list workspace templates
- `GET /templates/{id}` — get template detail
- `POST /templates/{id}/submit` — submit to Meta for approval
- `POST /templates/{id}/sync` — sync status from Meta
- `POST /templates/sync-all` — sync all templates from Meta (workspace-wide)

### Contacts (`/contacts`)
- `POST /contacts` — create contact
- `GET /contacts` — list contacts (workspace-scoped)
- `POST /contacts/import` — bulk import from CSV
- `GET /contacts/{contact_id}/notes` — get contact notes
- `POST /contacts/{contact_id}/notes` — add note
- `DELETE /contacts/{contact_id}/notes/{note_id}` — soft delete note
- `GET /contacts/{contact_id}/activities` — get contact activity log
- `GET /contacts/{contact_id}/attributes` — get contact attributes
- `PUT /contacts/{contact_id}/attributes` — upsert contact attributes

### Tags (`/tags`)
- `GET /tags` — list workspace tags
- `POST /tags` — create tag

### Attributes (`/attributes`)
- `GET /attributes/definitions` — list attribute definitions
- `POST /attributes/definitions` — create attribute definition

### Contact Imports (`/contacts/imports`)
- `POST /contacts/imports` — create import job (returns job_id for polling)
- `GET /contacts/imports` — list import jobs
- `GET /contacts/imports/{job_id}` — get import job status
- `GET /contacts/imports/{job_id}/errors` — get import row errors

### Segments (`/segments`)
- `GET /segments` — list workspace segments
- `POST /segments` — create segment
- `POST /segments/preview` — preview segment matching contacts
- `POST /segments/{segment_id}/materialize` — trigger async materialization

### Campaigns (`/campaigns`)
- `POST /campaigns` — create campaign draft
- `GET /campaigns` — list campaigns
- `GET /campaigns/{id}` — get campaign detail
- `POST /campaigns/{id}/audience` — bind audience snapshot (contact_ids)
- `POST /campaigns/{id}/queue` — queue/schedule campaign send
- `GET /campaigns/{id}/queue/{job_id}` — job status
- `GET /campaigns/{id}/progress` — live progress (sent/failed/skipped counts)

### Bulk Send (`/bulk-send`)
- `POST /bulk-send` — synchronous bulk send
- `POST /bulk-send/queue` — async bulk send via Celery
- `GET /bulk-send/queue/{job_id}` — job status

### Analytics (`/analytics`)
- `GET /analytics/messages` — aggregate stats (total_sent, delivered%, read%, failure%)
- `GET /analytics/messages/timeline` — daily sent/delivered over N days

### Billing (`/billing`)
- `GET /billing/usage` — current cycle usage snapshot

### Webhooks
- `GET /webhook/meta` — Meta webhook verification
- `POST /webhook/meta` — Meta delivery status callbacks (delivered/read/failed)
- `GET /whatsapp-webhook/{webhook_id}` — alternate verification
- `POST /whatsapp-webhook/{webhook_id}` — alternate callback
- `GET /webhook/meta/config` — webhook setup diagnostics
- `POST /webhook/order-created` — Shopify order webhook (HMAC verified)
- `POST /webhook/order-created/{store_identifier}` — path-based store identifier

### Ecommerce (`/ecommerce`)
- `POST /ecommerce/stores` — register Shopify store connection
- `GET /ecommerce/stores` — list store connections
- `PUT /ecommerce/event-mappings` — map event type → template
- `GET /ecommerce/event-mappings` — list event mappings

### Admin (`/admin`) — super_admin only
- `POST /admin/users` — create user
- `GET /admin/users` — list all users
- `PATCH /admin/users/{id}/role` — assign role
- `PATCH /admin/users/{id}/subscription` — assign plan
- `PATCH /admin/users/{id}/status` — activate/deactivate
- `GET /admin/workspaces` — list all workspaces
- `GET /admin/plans` — list plans
- `POST /admin/plans` — create plan
- `GET /admin/usage/messages` — usage by workspace
- `GET /admin/queues/inspect` — live Celery worker snapshot
- `GET /admin/queues/dead-letters` — list dead letter records
- `POST /admin/queues/webhook-ingestions/replay` — replay failed webhook ingestions

### Health
- `GET /` — health check

---

## 11. Key Business Logic

### Campaign Execution Pipeline
1. Create campaign draft → bind template + audience snapshot
2. Queue via Celery (`campaign.send` task)
3. Status transitions: `draft` → `queued` → `running` → `completed`/`failed`
4. Per-recipient: idempotency check (Redis) → rate limit → billing check → send via Meta API → register tracking → record event
5. Retry: exponential backoff up to 4 attempts, classifies errors (invalid_number, api_error, rate_limit)
6. Webhook callbacks update `message_tracking` → refresh campaign aggregates

### Template Lifecycle
1. Create as `draft` with Meta-format variables (`{{1}}`, `{{2}}`)
2. Submit to Meta Graph API → status becomes `pending`
3. Sync status from Meta → `approved`/`rejected`
4. Only `approved` templates with `meta_template_id` can be used in campaigns

### Shopify Integration
1. Register store connection (store_identifier + HMAC webhook_secret)
2. Map `order_created` event → approved template
3. Shopify sends `POST /webhook/order-created` → HMAC verified → extract customer phone/name/order → send template message
4. Delivery logged in `order_webhook_delivery_logs` with retry (3 attempts)

### Contact Import Flow
1. CSV Upload → Import Job Creation
2. Queue Worker (`contacts.import_job`)
3. Row Validation
4. Contact Upserts
5. Activity Events
6. Error Tracking

### Segment Materialization Flow
1. Segment DSL definition
2. Query Compilation (via `segment_filter_dsl.py`)
3. Worker Execution (`segments.materialize`)
4. Membership Rebuild
5. Cached Audience Generation

### Billing Enforcement
- Checked before every send: `POST /send-message`, `POST /bulk-send/queue`, `POST /campaigns/{id}/queue`, and inside campaign worker loop
- Plans: free (1K msgs), pro (10K), business (50K), enterprise (200K)
- Usage tracked per workspace per billing cycle (YYYY-MM)

---

## 13. Environment Variables

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/bulk_messaging
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
JWT_SECRET_KEY=<secret>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
SUPER_ADMIN_EMAIL=<email>
WHATSAPP_PROVIDER=cloud              # "cloud" for real sends, "simulation" for dev
WHATSAPP_PHONE_NUMBER_ID=<id>
WHATSAPP_ACCESS_TOKEN=<token>
WHATSAPP_DEFAULT_CALLING_CODE=91     # India
META_CREDENTIALS_ENCRYPTION_KEY=<min 16 chars>
META_GRAPH_API_BASE_URL=https://graph.facebook.com
META_GRAPH_API_VERSION=v18.0
META_API_TIMEOUT_SECONDS=15
META_WEBHOOK_VERIFY_TOKEN=<min 8 chars>
META_APP_SECRET=<optional, enables X-Hub-Signature-256 verification>
PUBLIC_BASE_URL=<ngrok URL for webhooks>
REDIS_URL=redis://localhost:6379/0
CELERY_DEFAULT_QUEUE=bulk-messages
CELERY_WEBHOOK_QUEUE=webhooks
CELERY_RESULT_TTL_SECONDS=86400
QUEUE_RETRY_MAX_ATTEMPTS=4
QUEUE_RETRY_BASE_DELAY_SECONDS=2
QUEUE_IDEMPOTENCY_TTL_SECONDS=604800
QUEUE_INFLIGHT_TTL_SECONDS=120
QUEUE_WORKSPACE_RATE_LIMIT_COUNT=20
QUEUE_WORKSPACE_RATE_LIMIT_WINDOW_SECONDS=1
WEBHOOK_DISPATCH_MAX_RETRIES=5
WEBHOOK_DEDUPE_TTL_SECONDS=300
WEBHOOK_INGEST_RATE_LIMIT_PER_IP_PER_MINUTE=120
QUEUE_DLQ_ENABLED=true
```

Frontend: `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000` (in `frontend/.env.local`)

---

## 14. Frontend Pages (Current State)

| Page | Route | Status | Description |
|------|-------|--------|-------------|
| Login | `/login` | ✅ Built | Email/password auth |
| Signup | `/signup` | ✅ Built | User registration |
| Onboarding | `/onboarding` | ✅ Built | Setup wizard (workspace, meta creds, contacts, template) |
| Dashboard | `/dashboard` | ✅ Built | Analytics overview |
| Campaigns | `/campaigns` | ✅ Built | Full CRUD — create, audience bind, queue, progress tracking |
| Contacts | `/contacts` | ✅ Built | Contact management + CSV import |
| Bulk Messaging | `/bulk-messaging` | ✅ Built | Direct bulk send UI |
| Shopify Integration | `/integrations/shopify` | ✅ Built | Store connection + event mapping |

### Frontend Architecture
- **Layout**: Sidebar nav (fixed left 72px wide) + top header with search + workspace switcher
- **Auth guard**: `useEffect` checks `getSession()` on workspace layout mount → redirect to `/login`
- **API layer**: `apiRequest<T>()` in `lib/api.ts` — auto-adds Bearer token, handles 401 redirect, parses error details
- **Session**: `localStorage` key `chatpulse.session` with custom event system for cross-tab sync
- **UI Components**: Custom button, card, input, table using CVA pattern

---

## 15. Security Considerations

- Meta credentials encrypted at rest (XOR keystream with SHA-256)
- Webhook HMAC-SHA256 verification (Shopify + Meta `X-Hub-Signature-256`)
- JWT tokens with configurable expiry
- CORS whitelist via env
- Rate limiting per workspace (Redis sliding window)
- Idempotency keys prevent duplicate sends (Redis TTL)
- Billing limits enforced at every send path

---

## 15. What's NOT Built Yet

- [ ] No proper Alembic migrations (uses `create_all` + manual `ALTER TABLE` in `init_db`)
- [ ] No tests (unit, integration, or e2e)
- [ ] No CI/CD pipeline
- [ ] No Docker/containerization
- [ ] No production deployment config
- [ ] No password reset / email verification flow
- [ ] No team member invitation flow (memberships exist but no invite API)
- [ ] No template editing (only create + submit)
- [ ] No campaign scheduling (queue endpoint accepts `schedule_at` but not fully implemented in worker)
- [ ] No contact segmentation UI in frontend (backend DSL exists but no UI)
- [ ] No admin dashboard frontend
- [ ] No real-time updates (WebSocket/SSE) — campaigns poll progress
- [ ] No logging/monitoring infrastructure (structured logging, observability dashboards)
- [ ] No payment gateway integration (plans exist but no Stripe/Razorpay)
- [ ] No rate limit headers returned to clients
- [ ] No API versioning
- [ ] No multi-language support beyond template language field
- [ ] Frontend lacks loading states, error boundaries, toast notifications in some pages
- [ ] No mobile-responsive testing
- [ ] No workflow runtime engine / visual flow builder
- [ ] No abandoned cart automation
- [ ] No drip sequence engine
- [ ] No advanced analytics rollups
- [ ] No event sourcing replay tooling UI
- [ ] No distributed tracing/correlation IDs
- [ ] No conversation state engine / inbox system
- [ ] No transactional automation rules engine
- [ ] No campaign scheduling runtime

---

## 14. Critical Product Flows

### Flow 1: User Onboarding
```
POST /auth/register → POST /auth/login → POST /workspaces →
POST /workspaces/switch → POST /meta/connect → GET /onboarding/status
```

### Flow 2: Campaign Execution
```
POST /campaigns → POST /campaigns/{id}/audience →
POST /campaigns/{id}/queue → [Celery worker runs] →
GET /campaigns/{id}/progress → POST /webhook/meta (delivery updates) →
GET /analytics/messages
```

### Flow 3: Shopify Order Notification
```
POST /ecommerce/stores → PUT /ecommerce/event-mappings →
[Shopify sends POST /webhook/order-created] → HMAC verify →
send_whatsapp_template_message → log to order_webhook_delivery_logs
```

### Flow 4: Contact Import
```
POST /contacts/imports → [Celery worker: contacts.import_job] →
row validation → contact upserts → activity events → error tracking
```

### Flow 5: Segment Targeting
```
POST /segments → POST /segments/{id}/materialize →
[Celery worker: segments.materialize] → DSL compilation →
contact filtering → membership rebuild
```

---

## 16. Running the Project

```bash
# Backend
cd "d:\On-going Projects\Bulk Messaging"
.venv\Scripts\activate
uvicorn app.main:app --reload                    # port 8000

# Celery worker (separate terminal)
celery -A app.worker:celery_app worker --loglevel=info

# Webhook worker (separate terminal)
celery -A app.worker:celery_app worker --loglevel=info -Q webhooks

# Frontend (separate terminal)
cd frontend
npm run dev                                       # port 3000

# For Meta webhooks (requires ngrok)
./scripts/start_api_public.ps1 -Port 8010
./scripts/start_ngrok_tunnel.ps1 -Port 8010
```

---

## 17. Code Conventions

- **Async everywhere**: All DB operations use `async/await` with SQLAlchemy async sessions
- **Service layer pattern**: Routes → Services → Models (routes never touch DB directly)
- **Dependency injection**: FastAPI `Depends()` for auth, workspace context, DB sessions
- **Error handling**: Services raise `ValueError`/custom exceptions, routes convert to `HTTPException`
- **Naming**: snake_case Python, camelCase TypeScript, kebab-case URLs
- **DB**: Auto-create tables on startup via `Base.metadata.create_all` + inline migrations in `init_db()`
- **Queue tasks**: Use `asyncio.run()` wrapper pattern to handle engine lifecycle in Celery workers
