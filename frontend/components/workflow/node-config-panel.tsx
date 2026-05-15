import React, { useEffect } from "react";
import { useForm } from "react-hook-form";
import { useWorkflowBuilderStore } from "@/stores/workflow-builder";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";

interface ConfigForm {
    name: string;
    config: Record<string, unknown>;
}

export function NodeConfigPanel() {
    const { nodes, selectedNodeId, setNodes } = useWorkflowBuilderStore();
    const selectedNode = nodes.find((node) => node.id === selectedNodeId);

    const { register, handleSubmit, reset, watch } = useForm<ConfigForm>({
        defaultValues: {
            name: selectedNode?.data?.name || "",
            config: (selectedNode?.data?.config as Record<string, unknown>) || {},
        },
    });

    useEffect(() => {
        reset({
            name: selectedNode?.data?.name || "",
            config: (selectedNode?.data?.config as Record<string, unknown>) || {},
        });
    }, [selectedNode, reset]);

    const onSubmit = (values: ConfigForm) => {
        if (!selectedNode) return;
        setNodes(
            nodes.map((node) =>
                node.id === selectedNode.id
                    ? {
                        ...node,
                        data: {
                            ...node.data,
                            name: values.name,
                            config: values.config,
                        },
                    }
                    : node
            )
        );
    };

    const config = watch("config");

    if (!selectedNode) {
        return (
            <div className="text-sm text-gray-500">
                Select a node to configure.
            </div>
        );
    }

    return (
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div>
                <label className="text-xs font-semibold text-gray-500">Node Name</label>
                <Input {...register("name")} placeholder="Node name" />
            </div>

            {selectedNode.type === "trigger" && (
                <div>
                    <label className="text-xs font-semibold text-gray-500">Trigger Type</label>
                    <Input
                        value={(config.trigger_type as string) || "manual"}
                        onChange={(e) =>
                            reset({
                                name: watch("name"),
                                config: { ...config, trigger_type: e.target.value },
                            })
                        }
                    />
                </div>
            )}

            {selectedNode.type === "condition" && (
                <div>
                    <label className="text-xs font-semibold text-gray-500">Condition Expression</label>
                    <Textarea
                        rows={3}
                        value={(config.expression as string) || ""}
                        onChange={(e) =>
                            reset({
                                name: watch("name"),
                                config: { ...config, expression: e.target.value },
                            })
                        }
                    />
                </div>
            )}

            {selectedNode.type === "delay" && (
                <div>
                    <label className="text-xs font-semibold text-gray-500">Delay (seconds)</label>
                    <Input
                        type="number"
                        value={(config.delay_seconds as number) || 60}
                        onChange={(e) =>
                            reset({
                                name: watch("name"),
                                config: { ...config, delay_seconds: Number(e.target.value) },
                            })
                        }
                    />
                </div>
            )}

            {selectedNode.type === "send_message" && (
                <div>
                    <label className="text-xs font-semibold text-gray-500">Message</label>
                    <Textarea
                        rows={4}
                        value={(config.message as string) || ""}
                        onChange={(e) =>
                            reset({
                                name: watch("name"),
                                config: { ...config, message: e.target.value },
                            })
                        }
                    />
                </div>
            )}

            {(selectedNode.type === "add_tag" || selectedNode.type === "remove_tag") && (
                <div>
                    <label className="text-xs font-semibold text-gray-500">Tag</label>
                    <Input
                        value={(config.tag as string) || ""}
                        onChange={(e) =>
                            reset({
                                name: watch("name"),
                                config: { ...config, tag: e.target.value },
                            })
                        }
                    />
                </div>
            )}

            {selectedNode.type === "branch" && (
                <div>
                    <label className="text-xs font-semibold text-gray-500">Branch Label</label>
                    <Input
                        value={(config.label as string) || ""}
                        onChange={(e) =>
                            reset({
                                name: watch("name"),
                                config: { ...config, label: e.target.value },
                            })
                        }
                    />
                </div>
            )}

            {selectedNode.type === "webhook_call" && (
                <div className="space-y-3">
                    <div>
                        <label className="text-xs font-semibold text-gray-500">Webhook URL</label>
                        <Input
                            value={(config.url as string) || ""}
                            onChange={(e) =>
                                reset({
                                    name: watch("name"),
                                    config: { ...config, url: e.target.value },
                                })
                            }
                        />
                    </div>
                    <div>
                        <label className="text-xs font-semibold text-gray-500">HTTP Method</label>
                        <Input
                            value={(config.method as string) || "POST"}
                            onChange={(e) =>
                                reset({
                                    name: watch("name"),
                                    config: { ...config, method: e.target.value },
                                })
                            }
                        />
                    </div>
                </div>
            )}

            <Button type="submit" className="w-full">
                Save Node
            </Button>
        </form>
    );
}
