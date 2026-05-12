# Service Contracts

> Input/output contracts, side effects, and emitted events for core services. Last updated: 2026-05-12.

---

## Overview

Each service has clear contracts that define inputs, outputs, side effects, and event emissions. This prevents implicit dependencies and enables testing.

---

## Contract Notation

```
┌─────────────────────────────────────────────────────────────┐
│ ServiceName                                                 │
├─────────────────────────────────────────────────────────────┤
│ Input:                                                       │
│   - param1: Type (required/optional)                       │
│   - param2: Type                                          │
│                                                             │
│ Output:                                                      │
│   - return_type: Description                               │
│                                                             │
│ Side Effects:                                                │
│   - Database writes: Table[columns]                        │
│   - External calls: ExternalService                       │
│                                                             │
│ Events Emitted:                                              │
│   - event.type: When emitted                              │
│                                                             │
│ Errors:                                                      │
│   - ErrorType: When raised                                 │
└─────────────────────────────────────────────────────────────┘
```

---

## Core Service Contracts

### MessageDispatchService

**File**: `app/services/message_dispatch_service.py`

```
┌─────────────────────────────────────────────────────────────┐
│ send_template_with_tracking                                  │
├─────────────────────────────────────────────────────────────┤
│ Input:                                                       │
│   - session: AsyncSession (required)                        │
│   - workspace_id: int (required)                            │
│   - phone: str (required)                                   │
│   - template_name: str (required)                          │
│   - language: str (required)                                │
│   - body_parameters: list[str] | None (optional)           │
│   - header_parameters: list[str] | None (optional)          │
│   - campaign_id: int | None (optional)                     │
│   - campaign_contact_id: int | None (optional)              │
│   - contact_id: int | None (optional)                      │
│   - max_attempts: int | None (optional, default=4)         │
│                                                             │
│ Output:                                                      │
│   - DispatchResult(provider_message_id, retryable,          │
│                    error_message, failure_classification)  │
│                                                             │
│ Side Effects:                                                │
│   - Database writes: message_tracking[insert]              │
│   - Database writes: message_events[insert]                │
│   - External calls: Meta API / Simulation                  │
│                                                             │
│ Events Emitted:                                              │
│   - message.sent: On successful dispatch                   │
│                                                             │
│ Errors:                                                      │
│   - InvalidNumberError: Invalid phone format               │
│   - RateLimitError: Meta rate limit hit                    │
│   - ApiError: Meta API failure                             │
│   - BillingLimitExceeded: No quota remaining              │
└─────────────────────────────────────────────────────────────┘
```

### CampaignService

**File**: `app/services/campaign_service.py`

```
┌─────────────────────────────────────────────────────────────┐
│ create_campaign                                              │
├─────────────────────────────────────────────────────────────┤
│ Input:                                                       │
│   - session: AsyncSession                                  │
│   - workspace_id: int                                      │
│   - name: str                                               │
│   - template_id: int | None                                │
│   - message_template: str | None                           │
│                                                             │
│ Output:                                                      │
│   - Campaign: Newly created campaign entity                │
│                                                             │
│ Side Effects:                                               │
│   - Database writes: campaigns[insert]                     │
│                                                             │
│ Events Emitted:                                              │
│   - campaign.created: On successful creation               │
│                                                             │
│ Errors:                                                      │
│   - ValueError: Invalid template or missing data            │
└─────────────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────────────────────┐
│ queue_campaign_send                                          │
├─────────────────────────────────────────────────────────────┤
│ Input:                                                       │
│   - session: AsyncSession                                  │
│   - workspace_id: int                                      │
│   - campaign_id: int                                       │
│   - schedule_at: datetime | None                           │
│                                                             │
│ Output:                                                      │
│   - str: Celery task ID                                    │
│                                                             │
│ Side Effects:                                               │
│   - Database writes: campaigns[update status=queued]      │
│   - Queue: Enqueue campaign.send task                       │
│                                                             │
│ Events Emitted:                                              │
│   - campaign.started: On successful queue                  │
│                                                             │
│ Errors:                                                      │
│   - ValueError: Campaign not in draft state                │
│   - ValueError: No audience bound                          │
│   - ValueError: Template not approved                      │
└─────────────────────────────────────────────────────────────┘
```

### SegmentService

**File**: `app/services/segment_service.py`

```
┌─────────────────────────────────────────────────────────────┐
│ create_segment                                              │
├─────────────────────────────────────────────────────────────┤
│ Input:                                                       │
│   - session: AsyncSession                                  │
│   - workspace_id: int                                      │
│   - name: str                                               │
│   - definition: dict (Filter DSL)                           │
│                                                             │
│ Output:                                                      │
│   - Segment: Newly created segment entity                   │
│                                                             │
│ Side Effects:                                               │
│   - Database writes: segments[insert]                      │
│                                                             │
│ Events Emitted:                                              │
│   - segment.created: On successful creation                 │
│                                                             │
│ Errors:                                                      │
│   - SegmentDefinitionError: Invalid DSL                    │
│   - ValueError: Duplicate segment name                     │
└─────────────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────────────────────┐
│ materialize_segment_membership                              │
├─────────────────────────────────────────────────────────────┤
│ Input:                                                       │
│   - session: AsyncSession                                  │
│   - workspace_id: int                                      │
│   - segment: Segment entity                                 │
│                                                             │
│ Output:                                                      │
│   - int: Number of memberships created                     │
│                                                             │
│ Side Effects:                                               │
│   - Database writes: segment_memberships[delete+insert]    │
│   - Database writes: segments[update approx_size]          │
│   - Database reads: contacts (filtered by DSL)            │
│                                                             │
│ Events Emitted:                                              │
│   - segment.materialized: On successful materialization    │
│                                                             │
│ Errors:                                                      │
│   - SegmentDefinitionError: Invalid DSL                    │
└─────────────────────────────────────────────────────────────┘
```

### WebhookDispatcherService

**File**: `app/services/webhook_dispatcher_service.py`

```
┌─────────────────────────────────────────────────────────────┐
│ dispatch_webhook_ingestion                                   │
├─────────────────────────────────────────────────────────────┤
│ Input:                                                       │
│   - session: AsyncSession                                  │
│   - ingestion: WebhookIngestion entity                     │
│                                                             │
│ Output:                                                      │
│   - bool: True if processed, False if skipped              │
│                                                             │
│ Side Effects:                                               │
│   - Database writes: webhook_ingestions[update status]     │
│   - Database writes: domain_events[insert]                  │
│   - Database writes: message_tracking[update]              │
│   - External calls: Meta API (for status lookups)          │
│                                                             │
│ Events Emitted:                                              │
│   - webhook.processed: On successful processing             │
│   - webhook.failed: On processing failure                  │
│   - message.delivered: On delivery webhook                  │
│   - message.read: On read webhook                           │
│   - message.failed: On failure webhook                      │
│                                                             │
│ Errors:                                                      │
│   - WebhookProcessingError: Processing failed              │
│   - DeduplicationError: Duplicate webhook                   │
└─────────────────────────────────────────────────────────────┘
```

### ContactImportService

**File**: `app/services/contact_import_service.py`

```
┌─────────────────────────────────────────────────────────────┐
│ create_import_job                                           │
├─────────────────────────────────────────────────────────────┤
│ Input:                                                       │
│   - session: AsyncSession                                  │
│   - workspace_id: int                                       │
│   - file_content: bytes (CSV)                             │
│   - filename: str                                           │
│   - created_by_user_id: int | None                         │
│                                                             │
│ Output:                                                      │
│   - ContactImportJob: Newly created job entity             │
│                                                             │
│ Side Effects:                                               │
│   - Database writes: contact_import_jobs[insert]           │
│   - Queue: Enqueue contacts.import_job task                 │
│                                                             │
│ Events Emitted:                                              │
│   - (none at creation - emitted on completion)             │
└─────────────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────────────────────┐
│ run_contact_import_job                                       │
├─────────────────────────────────────────────────────────────┤
│ Input:                                                       │
│   - session: AsyncSession                                  │
│   - workspace_id: int                                       │
│   - job_id: int                                             │
│                                                             │
│ Output:                                                      │
│   - dict: { processed, inserted, failed, skipped }         │
│                                                             │
│ Side Effects:                                               │
│   - Database writes: contact_import_jobs[update progress]  │
│   - Database writes: contact_import_rows[insert errors]    │
│   - Database writes: contacts[upsert]                       │
│   - Database writes: contact_activities[insert]             │
│                                                             │
│ Events Emitted:                                              │
│   - contact.imported: On job completion                    │
│   - contact.created: Per contact upsert                    │
│                                                             │
│ Errors:                                                      │
│   - ValueError: Job not in queued/processing state          │
│   - ImportValidationError: Row validation failed           │
└─────────────────────────────────────────────────────────────┘
```

### ContactNoteService

**File**: `app/services/contact_note_service.py`

```
┌─────────────────────────────────────────────────────────────┐
│ create_note                                                  │
├─────────────────────────────────────────────────────────────┤
│ Input:                                                       │
│   - session: AsyncSession                                  │
│   - workspace_id: int                                      │
│   - contact_id: int                                         │
│   - body: str                                               │
│   - author_user_id: int | None                             │
│                                                             │
│ Output:                                                      │
│   - ContactNote: Newly created note entity                   │
│                                                             │
│ Side Effects:                                               │
│   - Database writes: contact_notes[insert]                 │
│                                                             │
│ Events Emitted:                                              │
│   - contact.note_added: On successful creation              │
└─────────────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────────────────────┐
│ soft_delete_note                                             │
├─────────────────────────────────────────────────────────────┤
│ Input:                                                       │
│   - session: AsyncSession                                  │
│   - workspace_id: int                                      │
│   - contact_id: int                                        │
│   - note_id: int                                           │
│                                                             │
│ Output:                                                      │
│   - bool: True if deleted, False if not found              │
│                                                             │
│ Side Effects:                                               │
│   - Database writes: contact_notes[update deleted_at]      │
│                                                             │
│ Events Emitted:                                              │
│   - contact.note_deleted: On successful deletion            │
└─────────────────────────────────────────────────────────────┘
```

### TagService

**File**: `app/services/tag_service.py`

```
┌─────────────────────────────────────────────────────────────┐
│ create_tag                                                   │
├─────────────────────────────────────────────────────────────┤
│ Input:                                                       │
│   - session: AsyncSession                                  │
│   - workspace_id: int                                      │
│   - name: str                                               │
│   - color: str | None                                      │
│                                                             │
│ Output:                                                      │
│   - Tag: Newly created tag entity                          │
│                                                             │
│ Side Effects:                                               │
│   - Database writes: tags[insert]                         │
│                                                             │
│ Events Emitted:                                              │
│   - (none directly)                                        │
│                                                             │
│ Errors:                                                      │
│   - ValueError: Duplicate tag name                        │
└─────────────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────────────────────┐
│ add_tag_to_contact                                           │
├─────────────────────────────────────────────────────────────┤
│ Input:                                                       │
│   - session: AsyncSession                                  │
│   - workspace_id: int                                      │
│   - contact_id: int                                        │
│   - tag_name: str                                          │
│                                                             │
│ Output:                                                      │
│   - bool: True if added, False if already exists            │
│                                                             │
│ Side Effects:                                               │
│   - Database writes: contact_tags[insert if new]           │
│                                                             │
│ Events Emitted:                                              │
│   - contact.tag_added: On successful add                   │
│                                                             │
│ Errors:                                                      │
│   - ValueError: Tag not found                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Cross-Service Dependencies

### Service Dependency Graph

```
API Routes
    │
    ▼
CampaignService ◀─── TemplateService
    │                    │
    │                    ▼
    │              MetaCredentialService
    │
    ▼
MessageDispatchService ──── WhatsAppService ──── Meta API
    │
    ├──────► UsageTrackingService
    │
    ├──────► ContactActivityService
    │
    └──────► MessageEventService
```

### Safe Dependencies

```
CampaignService ──► TemplateService (read-only)
CampaignService ──► BillingService (read-only for check, write for tracking)
MessageDispatchService ──► MetaCredentialService (read-only for credentials)
MessageDispatchService ──► UsageTrackingService (increment only)
```

### Forbidden Dependencies

```
❌ BillingService ──► CampaignService (billing owns usage, not campaigns)
❌ CampaignService ──► WebhookDispatcherService (decoupled via events)
❌ WebhookDispatcherService ──► CampaignService (updates tracking, not campaigns)
```

---

## Event Emission Rules

### Rule 1: Emit at Domain Boundary

```python
# ✅ Good: Emit at service boundary
async def create_campaign(session, ...):
    campaign = await session.insert(Campaign, ...)
    await emit_event(session, "campaign.created", campaign.id)
    return campaign

# ❌ Bad: Emit inside inner function
async def _insert_campaign(session, ...):
    campaign = await session.insert(Campaign, ...)
    # Should not emit here - caller decides
    return campaign
```

### Rule 2: Idempotent Event Emission

```python
# ✅ Good: Check before emitting
async def send_template_with_tracking(session, ...):
    dispatch = await _do_send(session, ...)
    if dispatch.success:
        # Check if already emitted (idempotent)
        existing = await session.execute(
            select(MessageEvent).where(
                MessageEvent.campaign_id == campaign_id,
                MessageEvent.contact_id == contact_id,
                MessageEvent.status == 'sent'
            )
        )
        if not existing.first():
            await record_message_event(...)
    return dispatch
```

### Rule 3: Fail-Fast on Event Emission

```python
# ✅ Good: Commit transaction after event emission
async def send_template_with_tracking(session, ...):
    dispatch = await _do_send(session, ...)
    if dispatch.success:
        await record_message_event(session, ...)
    await session.commit()  # Commit after event
    return dispatch

# ❌ Bad: Emit event after return
async def send_template_with_tracking(session, ...):
    dispatch = await _do_send(session, ...)
    if dispatch.success:
        await record_message_event(session, ...)
    await session.commit()
    return dispatch
    # Don't emit event after return
```

---

## Testing Contracts

### Unit Test Pattern

```python
class TestMessageDispatchService:
    async def test_send_template_success(self, mock_session):
        # Arrange
        mock_session.execute.return_value = MagicMock()
        mock_session.commit = AsyncMock()

        # Act
        result = await send_template_with_tracking(
            session=mock_session,
            workspace_id=1,
            phone="+1234567890",
            template_name="hello_world",
            language="en",
        )

        # Assert
        assert result.provider_message_id == "wamid.xxx"
        assert result.error_message is None
        mock_session.execute.assert_called()  # MessageTracking insert
        mock_session.commit.assert_called()   # Transaction commit
```

### Integration Test Pattern

```python
class TestCampaignService:
    async def test_queue_campaign_emits_event(self, db_session):
        # Arrange
        campaign = await create_campaign(db_session, workspace_id=1, ...)

        # Act
        task_id = await queue_campaign_send(db_session, 1, campaign.id)

        # Assert
        event = await db_session.execute(
            select(DomainEvent).where(
                DomainEvent.event_type == "campaign.started",
                DomainEvent.workspace_id == 1
            )
        )
        assert event.scalar_one_or_none() is not None
```

---

## Future Service Contracts (Planned)

### RealtimeService (Planned)

```
┌─────────────────────────────────────────────────────────────┐
│ broadcast_campaign_update                                     │
├─────────────────────────────────────────────────────────────┤
│ Input:                                                       │
│   - workspace_id: int                                       │
│   - campaign_id: int                                       │
│   - status: CampaignStatus                                  │
│   - progress: dict                                          │
│                                                             │
│ Output:                                                      │
│   - int: Number of clients notified                        │
│                                                             │
│ Side Effects:                                               │
│   - WebSocket: Broadcast to workspace room                 │
│                                                             │
│ Errors:                                                      │
│   - ConnectionError: WebSocket gateway unavailable         │
└─────────────────────────────────────────────────────────────┘
```

### AutomationService (Planned)

```
┌─────────────────────────────────────────────────────────────┐
│ execute_trigger                                              │
├─────────────────────────────────────────────────────────────┤
│ Input:                                                       │
│   - trigger_type: str (e.g., "order.created")              │
│   - workspace_id: int                                       │
│   - payload: dict                                           │
│                                                             │
│ Output:                                                      │
│   - list[DispatchResult]: Results per recipient            │
│                                                             │
│ Side Effects:                                               │
│   - Database writes: message_tracking                       │
│   - External calls: Meta API                                │
│   - Database writes: automation_logs                        │
│                                                             │
│ Events Emitted:                                              │
│   - automation.executed: On trigger execution              │
│   - message.sent: Per message sent                         │
│                                                             │
│ Errors:                                                      │
│   - TriggerNotFoundError: No automation for trigger        │
│   - TemplateNotApprovedError: Mapped template not ready    │
└─────────────────────────────────────────────────────────────┘
```
