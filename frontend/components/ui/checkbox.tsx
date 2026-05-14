import React from "react";
import { cn } from "@/lib/utils";

export interface CheckboxProps extends React.InputHTMLAttributes<HTMLInputElement> {
    indeterminate?: boolean;
}

const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(
    ({ className, indeterminate, ...props }, ref) => (
        <input
            type="checkbox"
            ref={ref}
            className={cn(
                "w-4 h-4 accent-blue-600 cursor-pointer rounded border border-gray-300 dark:border-gray-600",
                className
            )}
            style={{
                accentColor: "#2563eb",
            }}
            {...props}
        />
    )
);
Checkbox.displayName = "Checkbox";

export { Checkbox };
