import { create } from "zustand";
import { User, Workspace } from "@/types";

interface AuthStore {
    user: User | null;
    workspace: Workspace | null;
    isLoading: boolean;
    isAuthenticated: boolean;
    setUser: (user: User | null) => void;
    setWorkspace: (workspace: Workspace | null) => void;
    setIsLoading: (loading: boolean) => void;
    logout: () => void;
}

export const useAuthStore = create<AuthStore>((set) => ({
    user: null,
    workspace: null,
    isLoading: false,
    isAuthenticated: false,
    setUser: (user) =>
        set({ user, isAuthenticated: user !== null }),
    setWorkspace: (workspace) => set({ workspace }),
    setIsLoading: (loading) => set({ isLoading: loading }),
    logout: () =>
        set({
            user: null,
            workspace: null,
            isAuthenticated: false,
        }),
}));
