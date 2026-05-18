import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Modal, ModalFooter, ModalHeader } from "@/components/ui/modal";

export function MetaVerificationModal({
    isOpen,
    onClose,
    onVerify,
    loading,
}: {
    isOpen: boolean;
    onClose: () => void;
    onVerify: (token: string) => Promise<void>;
    loading?: boolean;
}) {
    const [token, setToken] = useState("");

    return (
        <Modal isOpen={isOpen} onClose={onClose} size="sm">
            <ModalHeader>
                <h3 className="text-base font-semibold">Webhook verify token</h3>
                <button
                    onClick={onClose}
                    className="text-sm text-slate-500 hover:text-slate-900"
                >
                    Close
                </button>
            </ModalHeader>
            <div className="p-4 space-y-3">
                <p className="text-sm text-slate-600">
                    Compare the token configured in Meta against your backend configuration.
                </p>
                <Input
                    value={token}
                    onChange={(event) => setToken(event.target.value)}
                    placeholder="Enter verify token"
                />
            </div>
            <ModalFooter>
                <Button variant="outline" onClick={onClose}>
                    Cancel
                </Button>
                <Button
                    onClick={() => onVerify(token)}
                    disabled={loading || !token.trim()}
                >
                    Test token
                </Button>
            </ModalFooter>
        </Modal>
    );
}
