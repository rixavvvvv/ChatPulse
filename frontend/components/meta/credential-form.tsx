import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { MetaCredentialPayload } from "@/lib/services/meta";

type Props = {
    initialValues?: Partial<MetaCredentialPayload>;
    onValidate: (payload: MetaCredentialPayload) => Promise<void>;
    onSubmit: (payload: MetaCredentialPayload) => Promise<void>;
    loading?: boolean;
};

export function MetaCredentialForm({ initialValues, onValidate, onSubmit, loading }: Props) {
    const [phoneNumberId, setPhoneNumberId] = useState(initialValues?.phone_number_id ?? "");
    const [businessAccountId, setBusinessAccountId] = useState(initialValues?.business_account_id ?? "");
    const [accessToken, setAccessToken] = useState("");
    const [appSecret, setAppSecret] = useState("");
    const [verifyToken, setVerifyToken] = useState("");

    const payload: MetaCredentialPayload = {
        phone_number_id: phoneNumberId.trim(),
        business_account_id: businessAccountId.trim(),
        access_token: accessToken.trim(),
        app_secret: appSecret.trim() || undefined,
        webhook_verify_token: verifyToken.trim() || undefined,
    };

    return (
        <Card>
            <CardHeader>
                <CardTitle>Connect WhatsApp Business</CardTitle>
                <CardDescription>
                    Save Meta credentials for this workspace. Use permanent access tokens for production.
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="space-y-2">
                    <label className="text-sm font-medium">Business Account ID (WABA)</label>
                    <Input
                        value={businessAccountId}
                        onChange={(event) => setBusinessAccountId(event.target.value)}
                        placeholder="123456789012345"
                    />
                </div>
                <div className="space-y-2">
                    <label className="text-sm font-medium">Phone Number ID</label>
                    <Input
                        value={phoneNumberId}
                        onChange={(event) => setPhoneNumberId(event.target.value)}
                        placeholder="123456789012345"
                    />
                </div>
                <div className="space-y-2">
                    <label className="text-sm font-medium">Permanent Access Token</label>
                    <Input
                        type="password"
                        value={accessToken}
                        onChange={(event) => setAccessToken(event.target.value)}
                        placeholder="EAAG..."
                    />
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-2">
                        <label className="text-sm font-medium">App Secret (optional)</label>
                        <Input
                            type="password"
                            value={appSecret}
                            onChange={(event) => setAppSecret(event.target.value)}
                            placeholder="Meta app secret"
                        />
                    </div>
                    <div className="space-y-2">
                        <label className="text-sm font-medium">Webhook Verify Token (optional)</label>
                        <Input
                            value={verifyToken}
                            onChange={(event) => setVerifyToken(event.target.value)}
                            placeholder="Verify token"
                        />
                    </div>
                </div>
                <div className="flex flex-wrap gap-2">
                    <Button
                        variant="outline"
                        onClick={() => onValidate(payload)}
                        disabled={loading || !payload.phone_number_id || !payload.business_account_id || !payload.access_token}
                    >
                        Validate
                    </Button>
                    <Button
                        onClick={() => onSubmit(payload)}
                        disabled={loading || !payload.phone_number_id || !payload.business_account_id || !payload.access_token}
                    >
                        Save Connection
                    </Button>
                </div>
            </CardContent>
        </Card>
    );
}
