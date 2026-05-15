"use client";

import React, { useState } from "react";
import { CheckCircle, XCircle, AlertTriangle, SkipForward, FileText, Download, RefreshCw } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import toast from "react-hot-toast";

import { useContactImportJobs, useContactImportJob, useContactImportErrors } from "@/hooks/use-contacts";
import { ImportProgressTracker, ImportJobsListSkeleton } from "./import-progress-tracker";
import { ImportResultsTable } from "./import-results-table";
import { Modal, ModalBody, ModalFooter, ModalHeader } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/states";

interface ImportJobsPanelProps {
    isOpen: boolean;
    onClose: () => void;
}

export function ImportJobsPanel({ isOpen, onClose }: ImportJobsPanelProps) {
    const { data: jobs = [], isLoading } = useContactImportJobs();
    const [selectedJobId, setSelectedJobId] = useState<number | null>(null);
    const [showErrorsModal, setShowErrorsModal] = useState(false);

    const { data: selectedJob, isLoading: jobLoading } = useContactImportJob(selectedJobId || 0);
    const { data: errorsData, isLoading: errorsLoading } = useContactImportErrors(selectedJobId || 0);

    const activeJob = jobs.find((j) => j.status === "queued" || j.status === "processing");

    const handleViewErrors = (jobId: number) => {
        setSelectedJobId(jobId);
        setShowErrorsModal(true);
    };

    const handleCloseErrors = () => {
        setShowErrorsModal(false);
        setSelectedJobId(null);
    };

    return (
        <>
            <Modal isOpen={isOpen} onClose={onClose} size="lg">
                <ModalHeader>
                    <div className="flex items-center gap-2">
                        <RefreshCw className="h-5 w-5" />
                        <span>Import History</span>
                    </div>
                </ModalHeader>

                <ModalBody>
                    {isLoading ? (
                        <ImportJobsListSkeleton />
                    ) : jobs.length === 0 ? (
                        <EmptyState
                            title="No imports yet"
                            description="Your CSV imports will appear here"
                            icon={FileText}
                        />
                    ) : (
                        <div className="space-y-4">
                            {activeJob && (
                                <div className="mb-4">
                                    <p className="mb-2 text-sm font-medium text-primary">Active Import</p>
                                    <ImportProgressTracker
                                        jobId={activeJob.id}
                                        status={activeJob.status as "queued" | "processing" | "completed" | "failed"}
                                        totalRows={activeJob.total_rows}
                                        processedRows={activeJob.processed_rows}
                                        insertedRows={activeJob.inserted_rows}
                                        skippedRows={activeJob.skipped_rows}
                                        failedRows={activeJob.failed_rows}
                                        errorMessage={activeJob.error_message}
                                        createdAt={activeJob.created_at}
                                        completedAt={activeJob.completed_at}
                                        onViewErrors={() => handleViewErrors(activeJob.id)}
                                    />
                                </div>
                            )}

                            <div>
                                <p className="mb-3 text-sm font-medium text-muted-foreground">Previous Imports</p>
                                <div className="space-y-2">
                                    {jobs
                                        .filter((j) => j.status !== "queued" && j.status !== "processing")
                                        .map((job) => (
                                            <div
                                                key={job.id}
                                                className="flex items-center justify-between rounded-lg border p-4 hover:bg-muted/30"
                                            >
                                                <div className="flex items-center gap-3">
                                                    <div
                                                        className={`rounded-full p-2 ${
                                                            job.status === "completed"
                                                                ? "bg-green-100 text-green-600"
                                                                : "bg-red-100 text-red-600"
                                                        }`}
                                                    >
                                                        {job.status === "completed" ? (
                                                            <CheckCircle className="h-4 w-4" />
                                                        ) : (
                                                            <XCircle className="h-4 w-4" />
                                                        )}
                                                    </div>
                                                    <div>
                                                        <div className="flex items-center gap-2">
                                                            <Badge
                                                                variant={
                                                                    job.status === "completed" ? "secondary" : "destructive"
                                                                }
                                                            >
                                                                {job.status}
                                                            </Badge>
                                                            <span className="text-xs text-muted-foreground">
                                                                {formatDistanceToNow(new Date(job.created_at), {
                                                                    addSuffix: true,
                                                                })}
                                                            </span>
                                                        </div>
                                                        <p className="mt-1 text-sm">
                                                            <span className="font-medium text-green-600">
                                                                {job.inserted_rows}
                                                            </span>{" "}
                                                            added
                                                            {job.skipped_rows > 0 && (
                                                                <>
                                                                    {" · "}
                                                                    <span className="font-medium text-amber-600">
                                                                        {job.skipped_rows}
                                                                    </span>{" "}
                                                                    skipped
                                                                </>
                                                            )}
                                                            {job.failed_rows > 0 && (
                                                                <>
                                                                    {" · "}
                                                                    <span className="font-medium text-red-600">
                                                                        {job.failed_rows}
                                                                    </span>{" "}
                                                                    failed
                                                                </>
                                                            )}
                                                        </p>
                                                    </div>
                                                </div>
                                                {job.failed_rows > 0 && (
                                                    <Button
                                                        size="sm"
                                                        variant="ghost"
                                                        onClick={() => handleViewErrors(job.id)}
                                                    >
                                                        View Errors
                                                    </Button>
                                                )}
                                            </div>
                                        ))}
                                </div>
                            </div>
                        </div>
                    )}
                </ModalBody>

                <ModalFooter>
                    <Button variant="outline" onClick={onClose}>
                        Close
                    </Button>
                </ModalFooter>
            </Modal>

            <Modal isOpen={showErrorsModal} onClose={handleCloseErrors} size="xl">
                <ModalHeader>
                    <div className="flex items-center gap-2">
                        <AlertTriangle className="h-5 w-5 text-amber-500" />
                        <span>Import Errors - Job #{selectedJobId}</span>
                    </div>
                </ModalHeader>

                <ModalBody>
                    <ImportResultsTable
                        jobId={selectedJobId || 0}
                        errors={errorsData?.errors || []}
                        isLoading={errorsLoading}
                    />
                </ModalBody>

                <ModalFooter>
                    <Button variant="outline" onClick={handleCloseErrors}>
                        Close
                    </Button>
                </ModalFooter>
            </Modal>
        </>
    );
}

interface ImportSummaryModalProps {
    job: {
        id: number;
        status: string;
        total_rows: number;
        processed_rows: number;
        inserted_rows: number;
        skipped_rows: number;
        failed_rows: number;
        error_message: string | null;
        created_at: string;
        completed_at: string | null;
    };
    isOpen: boolean;
    onClose: () => void;
}

export function ImportSummaryModal({ job, isOpen, onClose }: ImportSummaryModalProps) {
    const { data: errorsData, isLoading: errorsLoading } = useContactImportErrors(job.id);
    const [showErrors, setShowErrors] = useState(false);

    const isSuccess = job.status === "completed";
    const hasErrors = job.failed_rows > 0;

    return (
        <Modal isOpen={isOpen} onClose={onClose} size="md">
            <ModalHeader>
                <div className="flex items-center gap-2">
                    {isSuccess ? (
                        <CheckCircle className="h-5 w-5 text-green-500" />
                    ) : (
                        <XCircle className="h-5 w-5 text-red-500" />
                    )}
                    <span>{isSuccess ? "Import Successful" : "Import Failed"}</span>
                </div>
            </ModalHeader>

            <ModalBody>
                <div className="space-y-6">
                    <div className="grid grid-cols-2 gap-4">
                        <div className="rounded-lg bg-green-50 p-4 text-center">
                            <p className="text-3xl font-bold text-green-600">{job.inserted_rows}</p>
                            <p className="text-sm text-green-700">Contacts Added</p>
                        </div>
                        <div className="rounded-lg bg-amber-50 p-4 text-center">
                            <p className="text-3xl font-bold text-amber-600">{job.skipped_rows}</p>
                            <p className="text-sm text-amber-700">Duplicates Skipped</p>
                        </div>
                    </div>

                    {hasErrors && !showErrors && (
                        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                    <AlertTriangle className="h-5 w-5 text-red-500" />
                                    <div>
                                        <p className="font-medium text-red-800">
                                            {job.failed_rows} row{job.failed_rows > 1 ? "s" : ""} failed
                                        </p>
                                        <p className="text-sm text-red-700">
                                            {job.error_message || "Some rows could not be imported"}
                                        </p>
                                    </div>
                                </div>
                                <Button size="sm" variant="outline" onClick={() => setShowErrors(true)}>
                                    View Details
                                </Button>
                            </div>
                        </div>
                    )}

                    {showErrors && (
                        <ImportResultsTable
                            jobId={job.id}
                            errors={errorsData?.errors || []}
                            isLoading={errorsLoading}
                        />
                    )}
                </div>
            </ModalBody>

            <ModalFooter>
                <Button variant="outline" onClick={onClose}>
                    Close
                </Button>
            </ModalFooter>
        </Modal>
    );
}