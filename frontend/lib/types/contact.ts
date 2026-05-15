export interface Contact {
    id: number;
    name: string;
    phone: string;
    tags: string[];
    created_at: string;
    last_activity_at?: string;
    status?: "active" | "inactive";
}

export interface ContactActivity {
    id: number;
    contact_id: number;
    type: string;
    payload: Record<string, unknown>;
    created_at: string;
    actor_user_id?: number;
}

export interface ContactNote {
    id: number;
    contact_id: number;
    body: string;
    created_at: string;
    author_user_id: number;
    deleted_at?: string;
}

export interface ContactAttribute {
    key: string;
    label: string;
    value: string | number | boolean | null;
    type: "text" | "number" | "boolean" | "date";
}

export interface AttributeDefinition {
    id: number;
    key: string;
    label: string;
    type: "text" | "number" | "boolean" | "date";
    is_indexed?: boolean;
    workspace_id: number;
}

export interface ContactsListResponse {
    contacts: Contact[];
    total: number;
    page: number;
    page_size: number;
    total_pages: number;
}

export interface ContactCreateRequest {
    name: string;
    phone: string;
    tags?: string[];
}

export interface ContactUploadResponse {
    contacts_added: number;
    contacts_skipped: number;
}

export type ContactSortField = "name" | "phone" | "created_at" | "last_activity_at";
export type SortDirection = "asc" | "desc";

export interface ContactsFilters {
    search?: string;
    tags?: string[];
    status?: "active" | "inactive";
}

export interface ContactsQueryParams {
    page?: number;
    page_size?: number;
    search?: string;
    sort_by?: ContactSortField;
    sort_dir?: SortDirection;
    tags?: string[];
    status?: "active" | "inactive";
    filter?: FilterNode;
}

export type FilterOperator =
    | "eq" | "neq" | "contains" | "in"
    | "gt" | "gte" | "lt" | "lte"
    | "has_tag" | "attr";

export interface FilterCondition {
    id: string;
    op: FilterOperator;
    field?: string;
    value?: string | number | boolean | null;
    values?: string[];
    tag?: string;
    key?: string;
    cmp?: string;
}

export interface FilterGroup {
    id: string;
    op: "and" | "or";
    children: (FilterGroup | FilterCondition)[];
}

export type FilterNode = FilterGroup | FilterCondition;

export interface SavedFilter {
    id: number;
    name: string;
    definition: FilterNode;
    created_at: string;
}

// Segment Builder Types (enhanced filter DSL)
export type SegmentOperator =
    | "eq" | "neq" | "contains" | "in"
    | "gt" | "gte" | "lt" | "lte"
    | "has_tag" | "attr" | "activity";

export interface SegmentCondition {
    id: string;
    op: SegmentOperator;
    field?: string;
    value?: string | number | boolean | null;
    values?: string[];
    tag?: string;
    key?: string;
    cmp?: string;
    activityType?: string;
    activityDays?: number;
}

export interface SegmentGroup {
    id: string;
    op: "and" | "or";
    children: (SegmentGroup | SegmentCondition)[];
}

export type SegmentNode = SegmentGroup | SegmentCondition;

// Contact Import Types
export type ImportJobStatus = "queued" | "processing" | "completed" | "failed";

export interface ContactImportJob {
    id: number;
    status: ImportJobStatus;
    total_rows: number;
    processed_rows: number;
    inserted_rows: number;
    skipped_rows: number;
    failed_rows: number;
    error_message: string | null;
    created_at: string;
    completed_at: string | null;
}

export interface ContactImportCreateResponse {
    job_id: number;
    celery_task_id: string | null;
}

export interface ContactImportRowError {
    row_number: number;
    error: string;
    raw: Record<string, string>;
}

export interface ContactImportErrorsResponse {
    job_id: number;
    errors: ContactImportRowError[];
}

export interface CsvColumn {
    header: string;
    sample: string[];
    mappedTo?: "name" | "phone" | "tags" | "skip";
}

export interface ColumnMapping {
    name: string | null;
    phone: string | null;
    tags: string | null;
}

export interface CsvValidationResult {
    valid: boolean;
    totalRows: number;
    errors: { row: number; message: string }[];
    preview: { name: string; phone: string; tags: string }[];
}