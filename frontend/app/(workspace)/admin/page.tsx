"use client";

import { SystemHealthDashboard } from "@/components/admin/system-health-dashboard";

export default function AdminPage() {
    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl font-bold">Admin Dashboard</h1>
                <p className="text-gray-500">System monitoring and health status</p>
            </div>

            <SystemHealthDashboard />
        </div>
    );
}