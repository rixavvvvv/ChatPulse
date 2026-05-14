import { apiClient } from "./api";
import {
    Contact,
    PaginatedResponse,
    Campaign,
    Conversation,
    Message,
    Workflow,
    Segment,
    Automation,
    Template,
} from "@/types";

// Contacts
export const contactsService = {
    list: (page = 1, pageSize = 20, search?: string) =>
        apiClient.get<PaginatedResponse<Contact>>("/contacts", {
            params: { page, page_size: pageSize, search },
        }),

    get: (id: number) =>
        apiClient.get<Contact>(`/contacts/${id}`),

    create: (data: Partial<Contact>) =>
        apiClient.post<Contact>("/contacts", data),

    update: (id: number, data: Partial<Contact>) =>
        apiClient.put<Contact>(`/contacts/${id}`, data),

    delete: (id: number) =>
        apiClient.delete(`/contacts/${id}`),

    import: (file: File) => {
        const formData = new FormData();
        formData.append("file", file);
        return apiClient.post<{ imported: number; skipped: number }>(
            "/contacts/import",
            formData
        );
    },
};

// Campaigns
export const campaignsService = {
    list: (page = 1, pageSize = 20) =>
        apiClient.get<PaginatedResponse<Campaign>>("/campaigns", {
            params: { page, page_size: pageSize },
        }),

    get: (id: number) =>
        apiClient.get<Campaign>(`/campaigns/${id}`),

    create: (data: Partial<Campaign>) =>
        apiClient.post<Campaign>("/campaigns", data),

    update: (id: number, data: Partial<Campaign>) =>
        apiClient.put<Campaign>(`/campaigns/${id}`, data),

    delete: (id: number) =>
        apiClient.delete(`/campaigns/${id}`),

    launch: (id: number) =>
        apiClient.post(`/campaigns/${id}/launch`),

    pause: (id: number) =>
        apiClient.post(`/campaigns/${id}/pause`),

    resume: (id: number) =>
        apiClient.post(`/campaigns/${id}/resume`),
};

// Conversations
export const conversationsService = {
    list: (page = 1, pageSize = 20) =>
        apiClient.get<PaginatedResponse<Conversation>>("/conversations", {
            params: { page, page_size: pageSize },
        }),

    get: (id: number) =>
        apiClient.get<Conversation>(`/conversations/${id}`),

    getMessages: (conversationId: number, page = 1, pageSize = 50) =>
        apiClient.get<PaginatedResponse<Message>>(`/conversations/${conversationId}/messages`, {
            params: { page, page_size: pageSize },
        }),

    sendMessage: (conversationId: number, content: string) =>
        apiClient.post<Message>(`/conversations/${conversationId}/messages`, {
            content,
        }),

    markAsRead: (id: number) =>
        apiClient.post(`/conversations/${id}/mark-read`),

    assign: (id: number, agentId: number) =>
        apiClient.post(`/conversations/${id}/assign`, { agent_id: agentId }),
};

// Workflows
export const workflowsService = {
    list: (page = 1, pageSize = 20) =>
        apiClient.get<PaginatedResponse<Workflow>>("/workflows", {
            params: { page, page_size: pageSize },
        }),

    get: (id: number) =>
        apiClient.get<Workflow>(`/workflows/${id}`),

    create: (data: Partial<Workflow>) =>
        apiClient.post<Workflow>("/workflows", data),

    update: (id: number, data: Partial<Workflow>) =>
        apiClient.put<Workflow>(`/workflows/${id}`, data),

    delete: (id: number) =>
        apiClient.delete(`/workflows/${id}`),

    activate: (id: number) =>
        apiClient.post(`/workflows/${id}/activate`),

    deactivate: (id: number) =>
        apiClient.post(`/workflows/${id}/deactivate`),
};

// Segments
export const segmentsService = {
    list: (page = 1, pageSize = 20) =>
        apiClient.get<PaginatedResponse<Segment>>("/segments", {
            params: { page, page_size: pageSize },
        }),

    get: (id: number) =>
        apiClient.get<Segment>(`/segments/${id}`),

    create: (data: Partial<Segment>) =>
        apiClient.post<Segment>("/segments", data),

    update: (id: number, data: Partial<Segment>) =>
        apiClient.put<Segment>(`/segments/${id}`, data),

    delete: (id: number) =>
        apiClient.delete(`/segments/${id}`),
};

// Automations
export const automationsService = {
    list: (page = 1, pageSize = 20) =>
        apiClient.get<PaginatedResponse<Automation>>("/automations", {
            params: { page, page_size: pageSize },
        }),

    get: (id: number) =>
        apiClient.get<Automation>(`/automations/${id}`),

    create: (data: Partial<Automation>) =>
        apiClient.post<Automation>("/automations", data),

    update: (id: number, data: Partial<Automation>) =>
        apiClient.put<Automation>(`/automations/${id}`, data),

    delete: (id: number) =>
        apiClient.delete(`/automations/${id}`),

    activate: (id: number) =>
        apiClient.post(`/automations/${id}/activate`),

    deactivate: (id: number) =>
        apiClient.post(`/automations/${id}/deactivate`),
};

// Templates
export const templatesService = {
    list: (page = 1, pageSize = 20) =>
        apiClient.get<PaginatedResponse<Template>>("/templates", {
            params: { page, page_size: pageSize },
        }),

    get: (id: number) =>
        apiClient.get<Template>(`/templates/${id}`),

    create: (data: Partial<Template>) =>
        apiClient.post<Template>("/templates", data),

    update: (id: number, data: Partial<Template>) =>
        apiClient.put<Template>(`/templates/${id}`, data),

    delete: (id: number) =>
        apiClient.delete(`/templates/${id}`),
};
