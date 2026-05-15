"use client";

import React, { useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";

import { PageLayout } from "@/components/layout/page-layout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { NodeSidebar } from "@/components/workflow/node-sidebar";
import { BuilderCanvas } from "@/components/workflow/builder-canvas";
import { NodeConfigPanel } from "@/components/workflow/node-config-panel";
import { ValidationPanel } from "@/components/workflow/validation-panel";
import { ExecutionPanel } from "@/components/workflow/execution-panel";
import { WorkflowToolbar } from "@/components/workflow/workflow-toolbar";
import { useWorkflowBuilder } from "@/hooks/workflow/useWorkflowBuilder";
import { useWorkflowAutosave } from "@/hooks/workflow/useWorkflowAutosave";
import { useWorkflowValidation } from "@/hooks/workflow/useWorkflowValidation";
import { useWorkflowExecution } from "@/hooks/workflow/useWorkflowExecution";
import { useWorkflowDefinition, useTriggerWorkflow } from "@/hooks/workflow/useWorkflowRuntime";
import { useWorkflowBuilderStore } from "@/stores/workflow-builder";

interface WorkflowMetaForm {
    name: string;
    description: string;
}

export default function WorkflowBuilderPage() {
    const searchParams = useSearchParams();
    const workflowIdParam = searchParams.get("workflowId");
    const workflowId = workflowIdParam ? Number(workflowIdParam) : undefined;

    const { handleLoadDefinition, nodes, edges } = useWorkflowBuilder();
    const {
        name,
        description,
        setWorkflowMeta,
        setValidationErrors,
        validationErrors,
        isSaving,
        lastSavedAt,
        execution,
        setExecution,
        setExecutionStatus,
    } = useWorkflowBuilderStore();

    const { register, watch, setValue } = useForm<WorkflowMetaForm>({
        defaultValues: {
            name,
            description,
        },
    });

    const workflowDefinitionQuery = useWorkflowDefinition(workflowId);
    const triggerWorkflow = useTriggerWorkflow();

    useEffect(() => {
        if (workflowDefinitionQuery.data?.data) {
            handleLoadDefinition(workflowDefinitionQuery.data.data);
            setValue("name", workflowDefinitionQuery.data.data.name);
            setValue("description", workflowDefinitionQuery.data.data.description || "");
        }
    }, [workflowDefinitionQuery.data, handleLoadDefinition, setValue]);

    const formName = watch("name");
    const formDescription = watch("description");

    useEffect(() => {
        setWorkflowMeta(formName, formDescription);
    }, [formName, formDescription, setWorkflowMeta]);

    const validation = useWorkflowValidation(nodes, edges);

    useEffect(() => {
        setValidationErrors(validation);
    }, [validation, setValidationErrors]);

    useWorkflowAutosave();

    useWorkflowExecution(execution?.execution_id || undefined);

    return (
        <PageLayout
            title="Workflow Builder"
            description="Design automated workflows with triggers and actions."
        >
            <div className="space-y-4">
                <WorkflowToolbar
                    name={name}
                    description={description}
                    isSaving={isSaving}
                    lastSavedAt={lastSavedAt}
                    onRun={() => {
                        if (!workflowId) return;
                        triggerWorkflow.mutate(
                            { workflowId, triggerData: {} },
                            {
                                onSuccess: (response) => {
                                    if (!response?.data) return;
                                    setExecution(response.data);
                                    setExecutionStatus(response.data.status);
                                },
                            }
                        );
                    }}
                />

                <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr_320px] gap-4">
                    <NodeSidebar />

                    <Card className="h-[720px]">
                        <BuilderCanvas />
                    </Card>

                    <div className="space-y-4">
                        <Card>
                            <CardHeader>
                                <CardTitle>Workflow Details</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-3">
                                <div>
                                    <label className="text-xs font-semibold text-gray-500">Name</label>
                                    <Input {...register("name")} placeholder="Workflow name" />
                                </div>
                                <div>
                                    <label className="text-xs font-semibold text-gray-500">Description</label>
                                    <Textarea rows={3} {...register("description")} placeholder="Describe this workflow" />
                                </div>
                            </CardContent>
                        </Card>

                        <Card>
                            <CardHeader>
                                <CardTitle>Node Configuration</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <NodeConfigPanel />
                            </CardContent>
                        </Card>

                        <Card>
                            <CardHeader>
                                <CardTitle>Validation</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <ValidationPanel errors={validationErrors} />
                            </CardContent>
                        </Card>

                        <Card>
                            <CardHeader>
                                <CardTitle>Execution State</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <ExecutionPanel execution={execution} />
                            </CardContent>
                        </Card>
                    </div>
                </div>
            </div>
        </PageLayout>
    );
}
