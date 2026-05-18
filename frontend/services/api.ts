import axios, { AxiosInstance } from "axios";
import { clearSession, getSession } from "@/lib/session";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export const apiClient: AxiosInstance = axios.create({
    baseURL: API_URL,
    timeout: 30000,
    headers: {
        "Content-Type": "application/json",
    },
});

// Add request interceptor to include auth token
apiClient.interceptors.request.use(
    (config) => {
        const session = getSession();
        if (session?.access_token) {
            config.headers.Authorization = `Bearer ${session.access_token}`;
        }
        return config;
    },
    (error) => Promise.reject(error)
);

// Add response interceptor for error handling
apiClient.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error.response?.status === 401) {
            // Token expired, clear and redirect to login
            clearSession();
            window.location.href = "/login";
        }
        return Promise.reject(error);
    }
);
