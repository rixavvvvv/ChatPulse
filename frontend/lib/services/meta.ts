import { apiRequest } from "@/lib/api";
import { getSession } from "@/lib/session";

export type MetaCredentialPayload = {
    phone_number_id: string;
    business_account_id: string;
    access_token: string;
    app_secret?: string | null;
    webhook_verify_token?: string | null;
};

export type MetaCredentialSummary = {
    is_connected: boolean;
    phone_number_id?: string | null;
    business_account_id?: string | null;
    access_token_last4?: string | null;
    app_secret_configured: boolean;
    webhook_verify_token_configured: boolean;
};

export type MetaTokenStatus = {
    is_valid: boolean;
    subject_id?: string | null;
    subject_name?: string | null;
    error?: string | null;
};

export type MetaPhoneNumberInfo = {
    id: string;
    display_phone_number?: string | null;
    verified_name?: string | null;
    quality_rating?: string | null;
    status?: string | null;
    code_verification_status?: string | null;
    platform_type?: string | null;
    throughput?: any | null;
};

export type MetaWabaInfo = {
    id?: string | null;
    name?: string | null;
    account_review_status?: string | null;
    health_status?: any | null;
    ownership_type?: string | null;
    message_template_namespace?: string | null;
};

export type MetaWebhookStatus = {
    callback_url?: string | null;
    verify_token_configured: boolean;
    signature_validation_enabled: boolean;
    links: string[];
    callback_host_matches_public_base_url?: boolean | null;
    public_base_url?: string | null;
};

export type MetaHealthSummary = {
    status: string;
    reasons: string[];
};

export type MetaConnectionResponse = {
    credentials: MetaCredentialSummary;
    waba?: MetaWabaInfo | null;
    phone_numbers: MetaPhoneNumberInfo[];
    token_status?: MetaTokenStatus | null;
    webhook?: MetaWebhookStatus | null;
    health?: MetaHealthSummary | null;
};

export type MetaWebhookDiagnostics = {
    status: string;
    workspace_id: number;
    callback_url?: string | null;
    verify_token: {
        env_configured: boolean;
        workspace_configured: boolean;
        effective_source?: string | null;
        effective_count: number;
        global_workspace_token_count: number;
    };
    signature: {
        env_configured: boolean;
        workspace_configured: boolean;
        validation_enabled: boolean;
        effective_source?: string | null;
        effective_count: number;
        global_workspace_secret_count: number;
    };
};

function requireToken(): string {
    const session = getSession();
    if (!session?.access_token) {
        throw new Error("Login required");
    }
    return session.access_token;
}

export async function getMetaConnection(): Promise<MetaConnectionResponse> {
    const token = requireToken();
    return apiRequest<MetaConnectionResponse>("/meta/connection", {}, token);
}

export async function connectMeta(payload: MetaCredentialPayload): Promise<void> {
    const token = requireToken();
    await apiRequest("/meta/connect", {
        method: "POST",
        body: JSON.stringify(payload),
    }, token);
}

export async function validateMeta(payload: MetaCredentialPayload): Promise<void> {
    const token = requireToken();
    await apiRequest("/meta/validate", {
        method: "POST",
        body: JSON.stringify(payload),
    }, token);
}

export async function rotateMetaToken(access_token: string): Promise<void> {
    const token = requireToken();
    await apiRequest("/meta/rotate-token", {
        method: "POST",
        body: JSON.stringify({ access_token }),
    }, token);
}

export async function disconnectMeta(): Promise<void> {
    const token = requireToken();
    await apiRequest("/meta/disconnect", { method: "POST" }, token);
}

export async function subscribeWebhook(): Promise<void> {
    const token = requireToken();
    await apiRequest("/meta/subscribe-webhook", { method: "POST" }, token);
}

export async function testWebhookVerifyToken(verify_token: string): Promise<{ ok: boolean; reason?: string }> {
    const token = requireToken();
    return apiRequest<{ ok: boolean; reason?: string }>(
        "/meta/webhook-test",
        {
            method: "POST",
            body: JSON.stringify({ verify_token }),
        },
        token,
    );
}

export async function syncMetaTemplates(): Promise<{ created: number; updated: number }> {
    const token = requireToken();
    return apiRequest<{ created: number; updated: number }>(
        "/meta/sync-templates",
        { method: "POST" },
        token,
    );
}

export async function getMetaWebhookDiagnostics(): Promise<MetaWebhookDiagnostics> {
    const token = requireToken();
    return apiRequest<MetaWebhookDiagnostics>("/meta/webhook-diagnostics", {}, token);
}
