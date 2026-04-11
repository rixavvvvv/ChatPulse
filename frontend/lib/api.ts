import { clearSession } from "@/lib/session";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000")
    .trim()
    .replace(/\/$/, "");

export function getApiUrl(path: string): string {
    if (path.startsWith("http://") || path.startsWith("https://")) {
        return path;
    }
    return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

export async function apiRequest<T>(
    path: string,
    options: RequestInit = {},
    accessToken?: string,
): Promise<T> {
    const headers = new Headers(options.headers ?? {});
    const hasBody = options.body !== undefined && options.body !== null;
    const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
    if (!headers.has("Content-Type") && hasBody && !isFormData) {
        headers.set("Content-Type", "application/json");
    }
    if (accessToken) {
        headers.set("Authorization", `Bearer ${accessToken}`);
    }

    const response = await fetch(getApiUrl(path), {
        ...options,
        headers,
    });

    if (response.status === 401 && accessToken) {
        if (typeof window !== "undefined") {
            clearSession();
            if (!window.location.pathname.startsWith("/login")) {
                window.location.replace("/login");
            }
        }
        throw new Error("Session expired. Please log in again.");
    }

    if (!response.ok) {
        let detail = response.statusText;
        try {
            const payload = (await response.json()) as { detail?: string };
            if (typeof payload.detail === "string" && payload.detail.trim()) {
                detail = payload.detail;
            }
        } catch {
            // Keep default status text when response body is not JSON.
        }
        throw new Error(detail || "Request failed");
    }

    if (response.status === 204) {
        return undefined as T;
    }

    return (await response.json()) as T;
}
