"use client";

import React, { useCallback, useState } from "react";
import { Upload, FileText, CheckCircle, AlertCircle, X } from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import toast from "react-hot-toast";

import {
    parseCsvPreview,
    autoDetectMapping,
    validateCsvMapping,
    createContactImportJob,
} from "@/lib/services/contacts";
import { Modal, ModalBody, ModalFooter, ModalHeader } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";

interface CsvImportModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSuccess?: () => void;
}

type ImportStep = "upload" | "mapping" | "progress" | "complete";

interface ColumnMapping {
    name: string | null;
    phone: string | null;
    tags: string | null;
}

export function CsvImportModal({ isOpen, onClose, onSuccess }: CsvImportModalProps) {
    const [step, setStep] = useState<ImportStep>("upload");
    const [dragOver, setDragOver] = useState(false);
    const [file, setFile] = useState<File | null>(null);
    const [csvHeaders, setCsvHeaders] = useState<string[]>([]);
    const [csvRows, setCsvRows] = useState<string[][]>([]);
    const [totalRows, setTotalRows] = useState(0);
    const [mapping, setMapping] = useState<ColumnMapping>({ name: null, phone: null, tags: null });
    const [jobId, setJobId] = useState<number | null>(null);
    const [isDragDrop, setIsDragDrop] = useState(false);

    const createImportMutation = useMutation({
        mutationFn: (file: File) => createContactImportJob(file),
        onSuccess: (data) => {
            setJobId(data.job_id);
            setStep("progress");
        },
        onError: (err) => {
            toast.error(err instanceof Error ? err.message : "Import failed");
            setStep("upload");
        },
    });

    const handleDragOver = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setDragOver(true);
    }, []);

    const handleDragLeave = useCallback(() => {
        setDragOver(false);
    }, []);

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setDragOver(false);
        setIsDragDrop(true);
        const droppedFile = e.dataTransfer.files[0];
        if (droppedFile?.name.toLowerCase().endsWith(".csv")) {
            handleFileSelect(droppedFile);
        } else {
            toast.error("Please upload a CSV file");
        }
    }, []);

    const handleFileSelect = useCallback(async (selectedFile: File) => {
        setFile(selectedFile);
        try {
            const preview = await parseCsvPreview(selectedFile);
            setCsvHeaders(preview.headers);
            setCsvRows(preview.rows);
            setTotalRows(preview.totalRows);
            setMapping(autoDetectMapping(preview.headers));
            setStep("mapping");
        } catch (err) {
            toast.error(err instanceof Error ? err.message : "Failed to parse CSV");
        }
    }, []);

    const handleMappingChange = useCallback((field: keyof ColumnMapping, value: string | null) => {
        setMapping((prev) => ({ ...prev, [field]: value }));
    }, []);

    const handleStartImport = useCallback(() => {
        const validation = validateCsvMapping(csvHeaders, mapping);
        if (!validation.valid) {
            toast.error(`Missing required columns: ${validation.missing.join(", ")}`);
            return;
        }
        if (file) {
            createImportMutation.mutate(file);
        }
    }, [csvHeaders, mapping, file, createImportMutation]);

    const handleClose = useCallback(() => {
        setStep("upload");
        setFile(null);
        setCsvHeaders([]);
        setCsvRows([]);
        setMapping({ name: null, phone: null, tags: null });
        setJobId(null);
        onClose();
    }, [onClose]);

    const handleComplete = useCallback(() => {
        onSuccess?.();
        handleClose();
    }, [onSuccess, handleClose]);

    const requiredFields = ["name", "phone"] as const;

    return (
        <Modal isOpen={isOpen} onClose={handleClose} size="xl">
            <ModalHeader>
                <div className="flex items-center gap-2">
                    <Upload className="h-5 w-5" />
                    <span>Import Contacts from CSV</span>
                </div>
            </ModalHeader>

            <ModalBody>
                {step === "upload" && (
                    <div
                        className={`relative flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-12 transition-colors ${
                            dragOver
                                ? "border-primary bg-primary/5"
                                : "border-border hover:border-primary/50"
                        }`}
                        onDragOver={handleDragOver}
                        onDragLeave={handleDragLeave}
                        onDrop={handleDrop}
                    >
                        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                            <div className="mb-4 rounded-full bg-muted p-4">
                                <FileText className="h-8 w-8 text-muted-foreground" />
                            </div>
                            <p className="mb-2 text-lg font-medium">Drop your CSV file here</p>
                            <p className="mb-4 text-sm text-muted-foreground">
                                or click to browse from your computer
                            </p>
                            <input
                                type="file"
                                accept=".csv,text/csv"
                                onChange={(e) => e.target.files?.[0] && handleFileSelect(e.target.files[0])}
                                className="absolute inset-0 cursor-pointer opacity-0"
                            />
                            <Button variant="outline" className="pointer-events-auto">
                                <Upload className="mr-2 h-4 w-4" />
                                Choose File
                            </Button>
                        </div>
                    </div>
                )}

                {step === "mapping" && csvHeaders.length > 0 && (
                    <div className="space-y-6">
                        <div className="rounded-lg bg-muted/50 p-4">
                            <p className="text-sm font-medium">File: {file?.name}</p>
                            <p className="text-sm text-muted-foreground">
                                {totalRows} rows detected
                            </p>
                        </div>

                        <div>
                            <h3 className="mb-3 text-sm font-semibold">Column Mapping</h3>
                            <p className="mb-4 text-sm text-muted-foreground">
                                Map your CSV columns to contact fields
                            </p>
                            <div className="grid gap-4 md:grid-cols-3">
                                {requiredFields.map((field) => (
                                    <div key={field}>
                                        <label className="mb-1 block text-sm font-medium">
                                            {field === "name" ? "Name Column" : "Phone Column"} *
                                        </label>
                                        <DropdownMenu>
                                            <DropdownMenuTrigger asChild>
                                                <Button
                                                    variant="outline"
                                                    className="w-full justify-start"
                                                >
                                                    {mapping[field]
                                                        ? mapping[field]
                                                        : `Select ${field} column`}
                                                </Button>
                                            </DropdownMenuTrigger>
                                            <DropdownMenuContent align="start" className="w-48">
                                                {csvHeaders.map((header) => (
                                                    <DropdownMenuItem
                                                        key={header}
                                                        onClick={() => handleMappingChange(field, header)}
                                                    >
                                                        {header}
                                                    </DropdownMenuItem>
                                                ))}
                                            </DropdownMenuContent>
                                        </DropdownMenu>
                                        {mapping[field] && (
                                            <p className="mt-1 flex items-center gap-1 text-xs text-green-600">
                                                <CheckCircle className="h-3 w-3" />
                                                Mapped
                                            </p>
                                        )}
                                    </div>
                                ))}

                                <div>
                                    <label className="mb-1 block text-sm font-medium">
                                        Tags Column (optional)
                                    </label>
                                    <DropdownMenu>
                                        <DropdownMenuTrigger asChild>
                                            <Button
                                                variant="outline"
                                                className="w-full justify-start"
                                            >
                                                {mapping.tags || "Skip"}
                                            </Button>
                                        </DropdownMenuTrigger>
                                        <DropdownMenuContent align="start" className="w-48">
                                            <DropdownMenuItem onClick={() => handleMappingChange("tags", null)}>
                                                Skip
                                            </DropdownMenuItem>
                                            {csvHeaders.map((header) => (
                                                <DropdownMenuItem
                                                    key={header}
                                                    onClick={() => handleMappingChange("tags", header)}
                                                >
                                                    {header}
                                                </DropdownMenuItem>
                                            ))}
                                        </DropdownMenuContent>
                                    </DropdownMenu>
                                </div>
                            </div>
                        </div>

                        <div>
                            <h3 className="mb-3 text-sm font-semibold">Preview (first 10 rows)</h3>
                            <div className="max-h-64 overflow-auto rounded-lg border">
                                <table className="w-full text-xs">
                                    <thead className="bg-muted sticky top-0">
                                        <tr>
                                            <th className="px-3 py-2 text-left font-medium">#</th>
                                            {csvHeaders.map((header) => (
                                                <th key={header} className="px-3 py-2 text-left font-medium">
                                                    {header}
                                                </th>
                                            ))}
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {csvRows.map((row, idx) => (
                                            <tr key={idx} className="border-t hover:bg-muted/30">
                                                <td className="px-3 py-2 text-muted-foreground">{idx + 1}</td>
                                                {row.map((cell, cellIdx) => (
                                                    <td key={cellIdx} className="px-3 py-2">
                                                        {cell || "-"}
                                                    </td>
                                                ))}
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>

                        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                            <div className="flex items-start gap-2">
                                <AlertCircle className="mt-0.5 h-4 w-4 text-amber-600" />
                                <div className="text-sm">
                                    <p className="font-medium text-amber-800">Duplicate Handling</p>
                                    <p className="text-amber-700">
                                        Contacts with matching phone numbers will be skipped automatically.
                                    </p>
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {step === "progress" && (
                    <div className="space-y-6 py-8">
                        <div className="flex flex-col items-center">
                            <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-primary/10">
                                <Upload className="h-8 w-8 animate-pulse text-primary" />
                            </div>
                            <p className="text-lg font-medium">Importing contacts...</p>
                            <p className="text-sm text-muted-foreground">
                                Job #{jobId} is being processed
                            </p>
                        </div>
                        <div className="mx-auto max-w-sm space-y-2">
                            <Progress value={undefined} className="h-2 animate-pulse" />
                            <p className="text-center text-xs text-muted-foreground">
                                This may take a moment depending on file size
                            </p>
                        </div>
                    </div>
                )}
            </ModalBody>

            <ModalFooter>
                {step === "upload" && (
                    <Button variant="outline" onClick={handleClose}>
                        Cancel
                    </Button>
                )}

                {step === "mapping" && (
                    <>
                        <Button variant="outline" onClick={() => setStep("upload")}>
                            Back
                        </Button>
                        <Button
                            onClick={handleStartImport}
                            disabled={!mapping.name || !mapping.phone || createImportMutation.isPending}
                        >
                            {createImportMutation.isPending ? "Importing..." : "Start Import"}
                        </Button>
                    </>
                )}

                {step === "progress" && (
                    <Button variant="outline" onClick={handleClose}>
                        Close
                    </Button>
                )}
            </ModalFooter>
        </Modal>
    );
}