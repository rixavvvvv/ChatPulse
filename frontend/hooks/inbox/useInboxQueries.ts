import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { inboxService } from "@/services/inbox/inbox-service";
import { ConversationMessage } from "@/types";
import toast from "react-hot-toast";

const defaultLimit = 30;

export function useConversationList(params: Parameters<typeof inboxService.listConversations>[0]) {
    return useInfiniteQuery({
        queryKey: ["inbox", "conversations", params],
        queryFn: ({ pageParam }) =>
            inboxService.listConversations({
                ...params,
                limit: params.limit ?? defaultLimit,
                offset: pageParam ?? 0,
            }),
        initialPageParam: 0,
        getNextPageParam: (lastPage, allPages, lastPageParam) =>
            lastPage.data.length === (params.limit ?? defaultLimit)
                ? (lastPageParam as number) + (params.limit ?? defaultLimit)
                : undefined,
    });
}

export function useConversationDetails(conversationId?: number) {
    return useQuery({
        queryKey: ["inbox", "conversation", conversationId],
        queryFn: () => inboxService.getConversation(conversationId as number),
        enabled: !!conversationId,
    });
}

export function useConversationMessages(conversationId?: number) {
    return useInfiniteQuery({
        queryKey: ["inbox", "messages", conversationId],
        queryFn: ({ pageParam }) =>
            inboxService.listMessages(conversationId as number, {
                limit: defaultLimit,
                before_id: pageParam,
            }),
        initialPageParam: undefined as number | undefined,
        getNextPageParam: (lastPage) =>
            lastPage.data.length === defaultLimit
                ? lastPage.data[0]?.id
                : undefined,
        enabled: !!conversationId,
    });
}

export function useUnreadSummary() {
    return useQuery({
        queryKey: ["inbox", "unread"],
        queryFn: () => inboxService.getUnreadSummary(),
        refetchInterval: 30000,
    });
}

export function useSendMessageMutation(conversationId?: number) {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (content: string) =>
            inboxService.sendMessage(conversationId as number, content),
        onMutate: async (content) => {
            if (!conversationId) return;
            await queryClient.cancelQueries({
                queryKey: ["inbox", "messages", conversationId],
            });

            const previous = queryClient.getQueryData([
                "inbox",
                "messages",
                conversationId,
            ]);

            const optimisticMessage: ConversationMessage = {
                id: Date.now(),
                conversation_id: conversationId,
                workspace_id: 0,
                direction: "outbound",
                sender_type: "agent",
                sender_id: undefined,
                content_type: "text",
                content,
                provider_message_id: null,
                metadata_json: {},
                created_at: new Date().toISOString(),
            };

            queryClient.setQueryData([
                "inbox",
                "messages",
                conversationId,
            ], (old: any) => {
                if (!old?.pages) return old;
                const updatedPages = [...old.pages];
                updatedPages[updatedPages.length - 1] = {
                    data: [...updatedPages[updatedPages.length - 1].data, optimisticMessage],
                };
                return {
                    ...old,
                    pages: updatedPages,
                };
            });

            return { previous };
        },
        onError: (error: any, _content, context) => {
            if (context?.previous) {
                queryClient.setQueryData(
                    ["inbox", "messages", conversationId],
                    context.previous
                );
            }
            toast.error(error.response?.data?.error || "Failed to send message");
        },
        onSuccess: () => {
            queryClient.invalidateQueries({
                queryKey: ["inbox", "messages", conversationId],
            });
        },
    });
}

export function useCreateNoteMutation(conversationId?: number) {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (body: string) =>
            inboxService.createNote(conversationId as number, body),
        onSuccess: () => {
            queryClient.invalidateQueries({
                queryKey: ["inbox", "notes", conversationId],
            });
            toast.success("Note added");
        },
        onError: (error: any) => {
            toast.error(error.response?.data?.error || "Failed to add note");
        },
    });
}

export function useConversationNotes(conversationId?: number) {
    return useQuery({
        queryKey: ["inbox", "notes", conversationId],
        queryFn: () => inboxService.listNotes(conversationId as number),
        enabled: !!conversationId,
    });
}

export function useConversationLabels() {
    return useQuery({
        queryKey: ["inbox", "labels"],
        queryFn: () => inboxService.listWorkspaceLabels(),
    });
}

export function useConversationLabelAssignments(conversationId?: number) {
    return useQuery({
        queryKey: ["inbox", "labels", conversationId],
        queryFn: () => inboxService.listConversationLabels(conversationId as number),
        enabled: !!conversationId,
    });
}

export function useAssignConversation() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ conversationId, agentUserId, version }: any) =>
            inboxService.assignConversation(conversationId, agentUserId, version),
        onSuccess: (_data, variables) => {
            queryClient.invalidateQueries({
                queryKey: ["inbox", "conversation", variables.conversationId],
            });
            toast.success("Conversation assigned");
        },
        onError: (error: any) => {
            toast.error(error.response?.data?.error || "Assignment failed");
        },
    });
}

export function useUnassignConversation() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ conversationId, version }: any) =>
            inboxService.unassignConversation(conversationId, version),
        onSuccess: (_data, variables) => {
            queryClient.invalidateQueries({
                queryKey: ["inbox", "conversation", variables.conversationId],
            });
            toast.success("Conversation unassigned");
        },
        onError: (error: any) => {
            toast.error(error.response?.data?.error || "Unassign failed");
        },
    });
}
