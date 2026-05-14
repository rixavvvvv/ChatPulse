import { useCallback } from "react";
import toast from "react-hot-toast";
import { AxiosError } from "axios";

export function useAsync<T, E = string>(
    asyncFunction: () => Promise<T>,
    immediate = true
) {
    const [status, setStatus] = useCallback<React.Dispatch<React.SetStateAction<"idle" | "pending" | "success" | "error">>>(
        () => "idle",
        []
    ) as any;
    const [data, setData] = useCallback(() => null, []) as any;
    const [error, setError] = useCallback(() => null, []) as any;

    const execute = useCallback(
        async () => {
            setStatus("pending");
            setData(null);
            setError(null);
            try {
                const response = await asyncFunction();
                setData(response);
                setStatus("success");
                return response;
            } catch (error: any) {
                setError(error.message);
                setStatus("error");
                throw error;
            }
        },
        [asyncFunction, setStatus, setData, setError]
    );

    useCallback(() => {
        if (immediate) {
            execute();
        }
    }, [execute, immediate])();

    return { execute, status, data, error };
}

export function useErrorHandler() {
    return useCallback((error: AxiosError | Error) => {
        const message =
            error instanceof AxiosError
                ? error.response?.data?.error || error.message
                : error.message;

        toast.error(message || "An error occurred");
    }, []);
}

export function useSuccess() {
    return useCallback((message: string = "Success!") => {
        toast.success(message);
    }, []);
}

export function useLoading() {
    return useCallback((message: string = "Loading...") => {
        return toast.loading(message);
    }, []);
}
