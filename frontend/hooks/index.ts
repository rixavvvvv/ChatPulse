import { useState, useCallback } from "react";

export function useDisclosure(initialOpen = false) {
    const [isOpen, setIsOpen] = useState(initialOpen);

    const onOpen = useCallback(() => setIsOpen(true), []);
    const onClose = useCallback(() => setIsOpen(false), []);
    const onToggle = useCallback(() => setIsOpen((v) => !v), []);

    return {
        isOpen,
        onOpen,
        onClose,
        onToggle,
    };
}

export function usePagination(initialPage = 1, pageSize = 10) {
    const [page, setPage] = useState(initialPage);

    const goToPage = useCallback((newPage: number) => {
        setPage(Math.max(1, newPage));
    }, []);

    const nextPage = useCallback(() => {
        setPage((p) => p + 1);
    }, []);

    const prevPage = useCallback(() => {
        setPage((p) => Math.max(1, p - 1));
    }, []);

    return {
        page,
        pageSize,
        goToPage,
        nextPage,
        prevPage,
    };
}

export function useSearch<T>(items: T[], searchKey: keyof T, debounceMs = 300) {
    const [query, setQuery] = useState("");
    const [results, setResults] = useState(items);
    const [isSearching, setIsSearching] = useState(false);

    const search = useCallback(
        (q: string) => {
            setQuery(q);
            setIsSearching(true);

            const filtered = items.filter((item) =>
                String(item[searchKey]).toLowerCase().includes(q.toLowerCase())
            );

            setResults(filtered);
            setIsSearching(false);
        },
        [items, searchKey]
    );

    const clear = useCallback(() => {
        setQuery("");
        setResults(items);
    }, [items]);

    return {
        query,
        results,
        isSearching,
        search,
        clear,
    };
}

export function useLocalStorage<T>(key: string, initialValue: T) {
    const [storedValue, setStoredValue] = useState<T>(() => {
        if (typeof window === "undefined") {
            return initialValue;
        }

        try {
            const item = window.localStorage.getItem(key);
            return item ? JSON.parse(item) : initialValue;
        } catch (error) {
            console.error(error);
            return initialValue;
        }
    });

    const setValue = useCallback(
        (value: T | ((v: T) => T)) => {
            try {
                const valueToStore = value instanceof Function ? value(storedValue) : value;
                setStoredValue(valueToStore);

                if (typeof window !== "undefined") {
                    window.localStorage.setItem(key, JSON.stringify(valueToStore));
                }
            } catch (error) {
                console.error(error);
            }
        },
        [key, storedValue]
    );

    return [storedValue, setValue] as const;
}
