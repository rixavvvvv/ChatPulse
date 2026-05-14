/**
 * Core type definitions for ChatPulse frontend
 */

export interface User {
    id: number;
    email: string;
    first_name: string;
    last_name: string;
    avatar_url?: string;
}

export interface Workspace {
    id: number;
    name: string;
    slug: string;
    plan: "free" | "pro" | "enterprise";
    created_at: string;
}

export interface Contact {
    id: number;
    phone_number: string;
    email?: string;
    first_name: string;
    last_name: string;
    tags: string[];
    is_active: boolean;
    created_at: string;
    last_message_at?: string;
}

export interface Campaign {
    id: number;
    name: string;
    description?: string;
    status: "draft" | "scheduled" | "running" | "completed" | "paused";
    message_template_id: number;
    target_audience: string;
    scheduled_at?: string;
    created_at: string;
    updated_at: string;
    stats: {
        total_recipients: number;
        sent: number;
        delivered: number;
        opened: number;
        clicked: number;
        failed: number;
    };
}

export interface Conversation {
    id: number;
    contact_id: number;
    contact: Contact;
    workspace_id: number;
    last_message?: string;
    last_message_at?: string;
    unread_count: number;
    is_active: boolean;
}

export interface Message {
    id: number;
    conversation_id: number;
    sender: "user" | "contact";
    content: string;
    status: "pending" | "sent" | "delivered" | "read" | "failed";
    created_at: string;
    media?: {
        url: string;
        type: string;
    }[];
}

export type ConversationStatus = "open" | "assigned" | "resolved" | "closed";
export type ConversationPriority = "low" | "normal" | "high" | "urgent";
export type ConversationChannel = "whatsapp" | "sms" | "email" | "web";
export type MessageDirection = "inbound" | "outbound";
export type MessageSenderType = "contact" | "agent" | "system" | "bot";
export type MessageContentType =
    | "text"
    | "image"
    | "video"
    | "document"
    | "audio"
    | "location"
    | "template"
    | "interactive"
    | "system";

export interface ConversationListItem {
    id: number;
    workspace_id: number;
    contact_id: number;
    channel: ConversationChannel;
    status: ConversationStatus;
    priority: ConversationPriority;
    subject?: string | null;
    last_message_preview?: string | null;
    last_message_at?: string | null;
    unread_count: number;
    created_at: string;
    updated_at: string;
}

export interface ConversationDetails extends ConversationListItem {
    metadata_json?: Record<string, unknown>;
    resolved_at?: string | null;
    closed_at?: string | null;
    version: number;
}

export interface ConversationMessage {
    id: number;
    conversation_id: number;
    workspace_id: number;
    direction: MessageDirection;
    sender_type: MessageSenderType;
    sender_id?: number | null;
    content_type: MessageContentType;
    content: string;
    provider_message_id?: string | null;
    metadata_json?: Record<string, unknown>;
    created_at: string;
}

export interface ConversationAssignment {
    id: number;
    conversation_id: number;
    agent_user_id: number;
    assigned_by?: number | null;
    is_active: boolean;
    assigned_at: string;
    unassigned_at?: string | null;
}

export interface ConversationInternalNote {
    id: number;
    conversation_id: number;
    author_user_id: number;
    body: string;
    deleted_at?: string | null;
    created_at: string;
    updated_at: string;
}

export interface ConversationLabel {
    id: number;
    workspace_id: number;
    name: string;
    color: string;
    description?: string | null;
    created_at: string;
}

export interface ConversationLabelAssignment {
    id: number;
    conversation_id: number;
    label_id: number;
    created_at: string;
}

export interface ConversationUnreadState {
    conversation_id: number;
    unread_count: number;
    last_read_at?: string | null;
}

export interface UnreadSummary {
    total_unread: number;
    conversations: ConversationUnreadState[];
}

export type AgentPresenceStatus = "online" | "away" | "busy" | "offline";

export interface AgentPresence {
    user_id: number;
    status: AgentPresenceStatus;
    last_seen_at?: string | null;
}

export interface Template {
    id: number;
    name: string;
    content: string;
    category: string;
    created_at: string;
    updated_at: string;
}

export interface Workflow {
    id: number;
    name: string;
    description?: string;
    status: "active" | "inactive" | "archived";
    trigger_type: string;
    nodes: WorkflowNode[];
    created_at: string;
    updated_at: string;
}

export interface WorkflowNode {
    id: string;
    type: string;
    data: Record<string, unknown>;
    position: { x: number; y: number };
}

export interface Segment {
    id: number;
    name: string;
    description?: string;
    criteria: SegmentCriteria;
    contact_count: number;
    created_at: string;
    updated_at: string;
}

export interface SegmentCriteria {
    filters: Array<{
        field: string;
        operator: string;
        value: unknown;
    }>;
    logic: "AND" | "OR";
}

export interface Automation {
    id: number;
    name: string;
    description?: string;
    trigger: string;
    actions: AutomationAction[];
    is_active: boolean;
    created_at: string;
}

export interface AutomationAction {
    type: string;
    config: Record<string, unknown>;
}

export interface Notification {
    id: string;
    type: "success" | "error" | "info" | "warning";
    title: string;
    message: string;
    timestamp: number;
}

export interface PaginatedResponse<T> {
    data: T[];
    total: number;
    page: number;
    page_size: number;
    total_pages: number;
}

export interface ApiError {
    error: string;
    status: number;
    details?: Record<string, unknown>;
}
