import { useMutation, useQuery } from "@tanstack/react-query";
import {
    contactsService,
    campaignsService,
    conversationsService,
    workflowsService,
    segmentsService,
    automationsService,
    templatesService,
} from "@/services/api-services";
import toast from "react-hot-toast";

// Contacts hooks
export function useContacts(page = 1, pageSize = 20, search?: string) {
    return useQuery({
        queryKey: ["contacts", page, pageSize, search],
        queryFn: () => contactsService.list(page, pageSize, search),
    });
}

export function useContact(id: number) {
    return useQuery({
        queryKey: ["contact", id],
        queryFn: () => contactsService.get(id),
        enabled: !!id,
    });
}

export function useCreateContact() {
    return useMutation({
        mutationFn: (data) => contactsService.create(data),
        onSuccess: () => {
            toast.success("Contact created successfully");
        },
        onError: (error: any) => {
            toast.error(error.response?.data?.error || "Failed to create contact");
        },
    });
}

export function useUpdateContact() {
    return useMutation({
        mutationFn: ({ id, data }: any) => contactsService.update(id, data),
        onSuccess: () => {
            toast.success("Contact updated successfully");
        },
        onError: (error: any) => {
            toast.error(error.response?.data?.error || "Failed to update contact");
        },
    });
}

export function useDeleteContact() {
    return useMutation({
        mutationFn: (id: number) => contactsService.delete(id),
        onSuccess: () => {
            toast.success("Contact deleted successfully");
        },
        onError: (error: any) => {
            toast.error(error.response?.data?.error || "Failed to delete contact");
        },
    });
}

export function useImportContacts() {
    return useMutation({
        mutationFn: (file: File) => contactsService.import(file),
        onSuccess: (data) => {
            toast.success(`Imported ${data.data.imported} contacts`);
        },
        onError: (error: any) => {
            toast.error(error.response?.data?.error || "Import failed");
        },
    });
}

// Campaigns hooks
export function useCampaigns(page = 1, pageSize = 20) {
    return useQuery({
        queryKey: ["campaigns", page, pageSize],
        queryFn: () => campaignsService.list(page, pageSize),
    });
}

export function useCampaign(id: number) {
    return useQuery({
        queryKey: ["campaign", id],
        queryFn: () => campaignsService.get(id),
        enabled: !!id,
    });
}

export function useCreateCampaign() {
    return useMutation({
        mutationFn: (data) => campaignsService.create(data),
        onSuccess: () => {
            toast.success("Campaign created successfully");
        },
        onError: (error: any) => {
            toast.error(error.response?.data?.error || "Failed to create campaign");
        },
    });
}

export function useLaunchCampaign() {
    return useMutation({
        mutationFn: (id: number) => campaignsService.launch(id),
        onSuccess: () => {
            toast.success("Campaign launched");
        },
        onError: (error: any) => {
            toast.error(error.response?.data?.error || "Failed to launch campaign");
        },
    });
}

// Conversations hooks
export function useConversations(page = 1, pageSize = 20) {
    return useQuery({
        queryKey: ["conversations", page, pageSize],
        queryFn: () => conversationsService.list(page, pageSize),
    });
}

export function useConversation(id: number) {
    return useQuery({
        queryKey: ["conversation", id],
        queryFn: () => conversationsService.get(id),
        enabled: !!id,
    });
}

export function useConversationMessages(conversationId: number, page = 1) {
    return useQuery({
        queryKey: ["conversation-messages", conversationId, page],
        queryFn: () => conversationsService.getMessages(conversationId, page),
        enabled: !!conversationId,
    });
}

export function useSendMessage() {
    return useMutation({
        mutationFn: ({ conversationId, content }: any) =>
            conversationsService.sendMessage(conversationId, content),
        onSuccess: () => {
            // Message sent successfully
        },
        onError: (error: any) => {
            toast.error(error.response?.data?.error || "Failed to send message");
        },
    });
}

// Workflows hooks
export function useWorkflows(page = 1, pageSize = 20) {
    return useQuery({
        queryKey: ["workflows", page, pageSize],
        queryFn: () => workflowsService.list(page, pageSize),
    });
}

export function useWorkflow(id: number) {
    return useQuery({
        queryKey: ["workflow", id],
        queryFn: () => workflowsService.get(id),
        enabled: !!id,
    });
}

export function useCreateWorkflow() {
    return useMutation({
        mutationFn: (data) => workflowsService.create(data),
        onSuccess: () => {
            toast.success("Workflow created successfully");
        },
        onError: (error: any) => {
            toast.error(error.response?.data?.error || "Failed to create workflow");
        },
    });
}

// Segments hooks
export function useSegments(page = 1, pageSize = 20) {
    return useQuery({
        queryKey: ["segments", page, pageSize],
        queryFn: () => segmentsService.list(page, pageSize),
    });
}

export function useSegment(id: number) {
    return useQuery({
        queryKey: ["segment", id],
        queryFn: () => segmentsService.get(id),
        enabled: !!id,
    });
}

// Automations hooks
export function useAutomations(page = 1, pageSize = 20) {
    return useQuery({
        queryKey: ["automations", page, pageSize],
        queryFn: () => automationsService.list(page, pageSize),
    });
}

export function useAutomation(id: number) {
    return useQuery({
        queryKey: ["automation", id],
        queryFn: () => automationsService.get(id),
        enabled: !!id,
    });
}

// Templates hooks
export function useTemplates(page = 1, pageSize = 20) {
    return useQuery({
        queryKey: ["templates", page, pageSize],
        queryFn: () => templatesService.list(page, pageSize),
    });
}

export function useTemplate(id: number) {
    return useQuery({
        queryKey: ["template", id],
        queryFn: () => templatesService.get(id),
        enabled: !!id,
    });
}
