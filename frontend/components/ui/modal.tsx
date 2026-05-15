import * as React from "react";
import { cn } from "@/lib/utils";
import { X } from "lucide-react";

export interface ModalProps {
    isOpen: boolean;
    onClose: () => void;
    children?: React.ReactNode;
    size?: "sm" | "md" | "lg" | "xl";
}

const sizes = {
    sm: "max-w-sm",
    md: "max-w-md",
    lg: "max-w-lg",
    xl: "max-w-2xl",
};

function Modal({ isOpen, onClose, children, size = "md" }: ModalProps) {
    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
            <div className="absolute inset-0 bg-black/50" onClick={onClose} />
            <div className={cn("relative w-full bg-background rounded-lg shadow-lg", sizes[size])}>
                {children}
            </div>
        </div>
    );
}

function ModalHeader({ className, children }: { className?: string; children: React.ReactNode }) {
    return (
        <div className={cn("flex items-center justify-between p-4 border-b", className)}>
            {children}
        </div>
    );
}

function ModalBody({ className, children }: { className?: string; children: React.ReactNode }) {
    return <div className={cn("p-4", className)} />;
}

function ModalFooter({ className, children }: { className?: string; children: React.ReactNode }) {
    return (
        <div className={cn("flex items-center justify-end gap-2 p-4 border-t", className)}>
            {children}
        </div>
    );
}

export { Modal, ModalHeader, ModalBody, ModalFooter };
