import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function MetaStatusCard({
    title,
    description,
    children,
}: {
    title: string;
    description?: string;
    children: React.ReactNode;
}) {
    return (
        <Card>
            <CardHeader>
                <CardTitle className="text-base">{title}</CardTitle>
                {description ? <CardDescription>{description}</CardDescription> : null}
            </CardHeader>
            <CardContent className="space-y-2">{children}</CardContent>
        </Card>
    );
}
