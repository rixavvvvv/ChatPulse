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

export type WorkflowNodeType =
    | "trigger"
    | "condition"
    | "delay"
    | "send_message"
    | "add_tag"
    | "remove_tag"
    | "branch"
    | "webhook_call";

export interface WorkflowNodeConfig {
    name: string;
    config: Record<string, unknown>;
}

export interface WorkflowDefinitionNode {
    node_id: string;
    node_type: WorkflowNodeType;
    name: string;
    config: Record<string, unknown>;
    position: { x: number; y: number };
}

export interface WorkflowDefinitionEdge {
    edge_id: string;
    source_node_id: string;
    target_node_id: string;
    condition?: string | null;
}

export type WorkflowStatus = "draft" | "published" | "archived";
export type WorkflowExecutionStatus =
    | "pending"
    | "running"
    | "completed"
    | "failed"
    | "cancelled"
    | "paused";

export interface WorkflowDefinitionResponse {
    id: number;
    workspace_id: number;
    name: string;
    description?: string | null;
    status: WorkflowStatus;
    version: number;
    created_by: number;
    created_at: string;
    updated_at: string;
    nodes: WorkflowDefinitionNode[];
    edges: WorkflowDefinitionEdge[];
}

export interface WorkflowExecutionResponse {
    id: number;
    workspace_id: number;
    workflow_definition_id: number;
    execution_id: string;
    status: WorkflowExecutionStatus;
    trigger_data: Record<string, unknown>;
    context: Record<string, unknown>;
    current_node_id?: string | null;
    started_at?: string | null;
    completed_at?: string | null;
    error?: string | null;
    created_at: string;
}

export interface NodeExecutionResponse {
    id: number;
    node_id: string;
    node_type: string;
    status: WorkflowExecutionStatus;
    input_data?: Record<string, unknown>;
    output_data?: Record<string, unknown>;
    error?: string | null;
    started_at?: string | null;
    completed_at?: string | null;
}

export interface WorkflowExecutionDetailResponse extends WorkflowExecutionResponse {
    node_executions: NodeExecutionResponse[];
}

export interface WorkflowValidationError {
    error_type: string;
    message: string;
    node_ids: string[];
    details?: Record<string, unknown>;
}

export interface DashboardOverview {
    workspace_id: number;
    period: string;
    messages_sent_today: number;
    messages_sent_yesterday: number;
    campaigns_active: number;
    campaigns_completed_today: number;
    delivery_rate: number;
    avg_dispatch_time_ms: number;
    queue_depth: number;
    error_rate: number;
}

export interface RealtimeDashboardMetrics {
    workspace_id: number;
    active_campaigns: number;
    messages_in_flight: number;
    queue_depth: number;
    active_workers: number;
    messages_last_minute: number;
    messages_last_hour: number;
    messages_per_second?: number | null;
    avg_queue_latency_ms?: number | null;
    avg_dispatch_latency_ms?: number | null;
    p95_dispatch_latency_ms?: number | null;
    error_rate_percent?: number | null;
    updated_at: string;
}

export interface CampaignDeliveryResponse {
    summary: Record<string, unknown>;
    timeline: Array<Record<string, unknown>>;
    error_breakdown: Record<string, number>;
}

export interface QueueHealthResponse {
    summary: Record<string, unknown>;
    timeline: Array<Record<string, unknown>>;
    by_worker: Record<string, number>;
}

export interface WebhookHealthResponse {
    summary: Record<string, unknown>;
    timeline: Array<Record<string, unknown>>;
    recent_failures: Array<Record<string, unknown>>;
    by_source: Record<string, number>;
}

export interface RetryAnalyticsResponse {
    summary: Record<string, unknown>;
    timeline: Array<Record<string, unknown>>;
    by_error_type: Record<string, number>;
}

export interface RecoveryAnalyticsResponse {
    summary: Record<string, unknown>;
    timeline: Array<Record<string, unknown>>;
    recent_recoveries: Array<Record<string, unknown>>;
}

export interface DashboardAlert {
    id: string;
    severity: "info" | "warning" | "critical";
    message: string;
    metric_name?: string;
    current_value?: number;
    threshold?: number;
    created_at?: string;
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
