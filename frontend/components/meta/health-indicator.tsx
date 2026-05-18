import { cn } from "@/lib/utils";

const statusStyles: Record<string, string> = {
    healthy: "bg-emerald-500",
    degraded: "bg-amber-500",
    unhealthy: "bg-rose-500",
    disconnected: "bg-slate-400",
};

export function MetaHealthIndicator({ status }: { status: string }) {
    const color = statusStyles[status] ?? "bg-slate-400";
    return (
        <span className={cn("inline-flex items-center gap-2 rounded-full px-2.5 py-1 text-xs font-semibold text-white", color)}>
            <span className="h-2 w-2 rounded-full bg-white/80" />
            {status}
        </span>
    );
}
