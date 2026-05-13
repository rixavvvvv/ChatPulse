# Shared Inbox Architecture

> Backend infrastructure design for the ChatPulse collaborative conversation system.

## System Overview

```
                    ┌──────────────────────────────────────────────────────┐
                    │                   SHARED INBOX                       │
                    │                                                      │
  Meta Webhook ────►│  ┌────────┐    ┌──────────┐    ┌───────────────┐   │
                    │  │ Inbound│───►│Conversation│───►│  WebSocket    │   │
  Agent UI ────────►│  │ Router │    │  Service  │    │  Broadcaster  │───┼──► Agents
                    │  └────────┘    └──────────┘    └───────────────┘   │
                    │       │              │                │             │
                    │       ▼              ▼                ▼             │
                    │  ┌────────┐    ┌──────────┐    ┌───────────────┐   │
                    │  │Message │    │  State   │    │  Presence     │   │
                    │  │Service │    │  Engine  │    │  Service      │   │
                    │  └────────┘    └──────────┘    └───────────────┘   │
                    │       │              │                              │
                    │       ▼              ▼                              │
                    │  ┌────────┐    ┌──────────┐                        │
                    │  │Unread  │    │Assignment│                        │
                    │  │Service │    │ Service  │                        │
                    │  └────────┘    └──────────┘                        │
                    └──────────────────────────────────────────────────────┘
```

## Database Schema

### Tables

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `conversations` | Core conversation entity | workspace_id, contact_id, channel, status, priority, version |
| `conversation_messages` | Message storage | conversation_id, direction, sender_type, content, provider_message_id |
| `conversation_assignments` | Agent assignment tracking | conversation_id, agent_user_id, is_active |
| `conversation_internal_notes` | Internal team notes | conversation_id, author_user_id, body, deleted_at |
| `conversation_labels` | Label definitions | workspace_id, name, color |
| `conversation_label_assignments` | Label-to-conversation mapping | conversation_id, label_id |
| `conversation_unread_states` | Per-agent unread tracking | conversation_id, user_id, unread_count |
| `agent_presence` | Online/offline/away status | user_id, workspace_id, status, last_heartbeat_at |

## Conversation State Machine

```
        ┌────────────────────────────────────────────┐
        │                                            │
        ▼                                            │
   ┌─────────┐     ┌──────────┐     ┌──────────┐    │    ┌────────┐
   │  OPEN   │────►│ ASSIGNED │────►│ RESOLVED │────┼───►│ CLOSED │
   └─────────┘     └──────────┘     └──────────┘    │    └────────┘
        ▲               │               │            │        │
        │               │               │            │        │
        │               └───────────────┘            │        │
        │               (back to open)               │        │
        └────────────────────────────────────────────┘        │
        │                    (reopen)                          │
        └─────────────────────────────────────────────────────┘
```

### Transition Rules

| From | To | Trigger |
|------|----|---------|
| open | assigned | Agent assignment |
| open | resolved | Manual resolution |
| open | closed | Manual close |
| assigned | open | Agent unassignment |
| assigned | resolved | Agent resolves |
| assigned | closed | Manual close |
| resolved | open | New inbound message (auto-reopen) |
| resolved | closed | Manual close |
| closed | open | New inbound message (auto-reopen) |

## Optimistic Locking

Every conversation has a `version` column (starting at 1).

### How It Works

1. Agent A reads conversation (version=3)
2. Agent B reads same conversation (version=3)
3. Agent A resolves → version becomes 4 ✓
4. Agent B tries to assign → expected version=3, actual=4 → **409 Conflict** ✗

### API Contract

All state-changing endpoints require the current `version`:

```json
POST /conversations/123/resolve
{
  "version": 3
}
```

If version mismatch: **HTTP 409 Conflict** with descriptive error.

## WebSocket Architecture

### Connection Lifecycle

```
Client                          Server
  │                                │
  │  ws://api/ws?token=JWT         │
  ├───────────────────────────────►│  authenticate
  │                                │  join workspace room
  │  {"event_type": "connected"}   │
  │◄───────────────────────────────┤
  │                                │
  │  {"action": "join_conversation",│
  │   "conversation_id": 123}      │
  ├───────────────────────────────►│  join conversation room
  │                                │
  │  conversation events           │
  │◄───────────────────────────────┤  broadcast to room
  │                                │
  │  {"action": "typing_start",    │
  │   "conversation_id": 123}      │
  ├───────────────────────────────►│  broadcast to conversation
  │                                │
  │  disconnect                    │
  ├───────────────────────────────►│  leave rooms
  │                                │  emit offline presence
```

### Event Types

| Event | Direction | Payload |
|-------|-----------|---------|
| `conversation.created` | Server→Client | Full conversation object |
| `conversation.updated` | Server→Client | Updated conversation fields |
| `conversation.assigned` | Server→Client | Assignment details |
| `message.received` | Server→Client | New inbound message |
| `message.sent` | Server→Client | New outbound message |
| `typing` | Bidirectional | conversation_id, user_id, is_typing |
| `presence.update` | Server→Client | user_id, status |
| `unread.update` | Server→Client | conversation_id, unread_count |

### Room Architecture

```
workspace:42
├── user:1 (Agent Alice)
├── user:2 (Agent Bob)
└── user:3 (Agent Charlie)

conversation:123
├── user:1 (viewing this conversation)
└── user:2 (viewing this conversation)
```

- **Workspace rooms**: All agents receive inbox-level updates
- **Conversation rooms**: Only agents viewing receive typing indicators

## Agent Presence

### Heartbeat Protocol

1. WebSocket connects → agent marked `online`
2. Client sends heartbeat every 30 seconds
3. Server considers agent `offline` after 120 seconds without heartbeat
4. WebSocket disconnects → agent marked `offline`
5. Periodic task expires stale agents (cron)

### Status Types

| Status | Meaning |
|--------|---------|
| `online` | Agent is active and available |
| `away` | Agent is idle (auto-set after 5 min inactivity) |
| `busy` | Agent manually set busy |
| `offline` | Agent disconnected or heartbeat expired |

## Unread Tracking

### How Unreads Work

1. New message arrives in conversation
2. Unread count incremented for ALL agents tracking that conversation (except sender)
3. Agent opens conversation → unread count reset to 0
4. Sidebar badge shows total unread across all conversations

### Batch Operations

- `POST /conversations/{id}/read` — mark single conversation as read
- Batch mark-read available via service layer for bulk operations

## Integration Points

### Inbound Message Flow
```
Meta Webhook → webhook_meta route → process_ingestion task
  → resolve contact
  → conversation_message_service.create_inbound_message()
  → get_or_create_conversation()
  → auto-reopen if resolved/closed
  → increment unread counts
  → WebSocket broadcast
```

### Outbound Message Flow
```
Agent UI → POST /conversations/{id}/messages
  → conversation_message_service.create_outbound_message()
  → dispatch via whatsapp_service (TODO: integrate)
  → WebSocket broadcast to other agents
```

## Metrics & Observability

| Metric | Description |
|--------|-------------|
| Active conversations | Count by status |
| Avg response time | First agent reply after inbound message |
| Avg resolution time | Creation → resolution timestamp |
| Agent workload | Active conversations per agent |
| Messages/hour | Throughput monitoring |
| Online agents | Current availability |
| Waiting conversations | Open conversations with no assignment |
