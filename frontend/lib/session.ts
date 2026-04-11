export type AppSession = {
    access_token: string;
    workspace_id: number;
    role: string;
};

const SESSION_STORAGE_KEY = "chatpulse.session";
const SESSION_EVENT = "chatpulse:session-updated";

export function getSession(): AppSession | null {
    if (typeof window === "undefined") {
        return null;
    }

    const raw = window.localStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) {
        return null;
    }

    try {
        const parsed = JSON.parse(raw) as AppSession;
        if (!parsed.access_token || !parsed.workspace_id) {
            return null;
        }
        return parsed;
    } catch {
        return null;
    }
}

export function saveSession(session: AppSession): void {
    if (typeof window === "undefined") {
        return;
    }

    window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
    window.dispatchEvent(new Event(SESSION_EVENT));
}

export function clearSession(): void {
    if (typeof window === "undefined") {
        return;
    }

    window.localStorage.removeItem(SESSION_STORAGE_KEY);
    window.dispatchEvent(new Event(SESSION_EVENT));
}

export function onSessionUpdated(callback: () => void): () => void {
    const handler = () => callback();
    window.addEventListener(SESSION_EVENT, handler);
    window.addEventListener("storage", handler);

    return () => {
        window.removeEventListener(SESSION_EVENT, handler);
        window.removeEventListener("storage", handler);
    };
}
