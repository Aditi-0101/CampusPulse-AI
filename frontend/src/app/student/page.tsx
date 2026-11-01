"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  PlusCircle,
  Search,
  Clock,
  CheckCircle2,
  AlertCircle,
  Wifi,
  RefreshCw,
  ArrowRight,
  ShieldAlert,
  FileText,
  Loader2,
} from "lucide-react";
import { RouteGuard } from "@/components/RouteGuard";
import { useAuth } from "@/context/AuthContext";
import { fetchStudentGrievances, StudentGrievanceItem } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

export default function StudentDashboardPage() {
  const { user } = useAuth();
  const [grievances, setGrievances] = useState<StudentGrievanceItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleRefresh = async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const data = await fetchStudentGrievances();
      setGrievances(data);
    } catch (err: unknown) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to load your complaints."
      );
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    let ignore = false;
    fetchStudentGrievances()
      .then((data) => {
        if (!ignore) {
          setGrievances(data);
          setIsLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setErrorMessage(
            err instanceof Error ? err.message : "Failed to load your complaints."
          );
          setIsLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, []);

  // Compute metrics from actual student records
  const totalCount = grievances.length;
  const inProgressCount = grievances.filter(
    (g) =>
      g.status === "SUBMITTED" ||
      g.status === "TRIAGED" ||
      g.status === "PENDING_APPROVAL"
  ).length;
  const resolvedCount = grievances.filter(
    (g) => g.status === "APPROVED" || g.status === "ASSIGNED" || g.status === "RESOLVED"
  ).length;
  const escalatedCount = grievances.filter((g) => g.is_escalated_to_vc).length;

  return (
    <RouteGuard allowedPortals={["student"]}>
      <div className="space-y-8 pb-12">
        {/* Welcome Hero Section */}
        <section className="bg-gradient-to-r from-[#0f2744] via-[#16355d] to-[#1e4577] text-white rounded-2xl p-6 sm:p-8 shadow-sm border border-[#1e3a5f] relative overflow-hidden">
          <div className="relative z-10 max-w-3xl space-y-4">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/20 text-blue-200 border border-blue-400/20 text-xs font-semibold">
              <Wifi className="w-3.5 h-3.5 text-blue-300" />
              <span>Hostel Infrastructure Operations</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-white">
              Student Grievance Dashboard
            </h1>
            <p className="text-sm sm:text-base text-slate-200 leading-relaxed font-normal">
              Welcome back, <span className="font-semibold text-white">{user?.name || "Student"}</span>.
              Report Wi-Fi outages, track automated swarm diagnostics, and submit verified follow-ups on unresolved hostel infrastructure issues.
            </p>

            <div className="flex flex-wrap items-center gap-3 pt-2">
              <Link
                href="/submit"
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-medium text-sm shadow-sm transition-all hover:shadow"
              >
                <PlusCircle className="w-4 h-4" />
                <span>Submit a Complaint</span>
              </Link>
              <Link
                href="/track"
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-white/10 hover:bg-white/20 text-white font-medium text-sm border border-white/20 transition-all"
              >
                <Search className="w-4 h-4" />
                <span>Track Complaint Status</span>
              </Link>
            </div>
          </div>

          <div className="absolute -right-8 -bottom-8 opacity-10 pointer-events-none select-none">
            <Wifi className="w-64 h-64 text-white" />
          </div>
        </section>

        {/* Real Metrics Cards */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-bold text-slate-800">
              Your Complaints Overview
            </h2>
            <button
              onClick={handleRefresh}
              disabled={isLoading}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-600 bg-white border border-slate-200 hover:bg-slate-50 transition-colors"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
              <span>Refresh</span>
            </button>
          </div>

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Total */}
            <div className="bg-white rounded-xl p-5 border border-slate-200/80 shadow-xs">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                  Total Filed
                </span>
                <div className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
                  <FileText className="w-4 h-4" />
                </div>
              </div>
              <div className="text-2xl font-bold text-slate-900">{totalCount}</div>
              <p className="text-xs text-slate-500 mt-1">Verified student grievances</p>
            </div>

            {/* In Progress */}
            <div className="bg-white rounded-xl p-5 border border-slate-200/80 shadow-xs">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold text-amber-700 uppercase tracking-wider">
                  In Triage / Review
                </span>
                <div className="w-8 h-8 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center">
                  <Clock className="w-4 h-4" />
                </div>
              </div>
              <div className="text-2xl font-bold text-amber-600">{inProgressCount}</div>
              <p className="text-xs text-slate-500 mt-1">Awaiting staff resolution</p>
            </div>

            {/* Approved / Active */}
            <div className="bg-white rounded-xl p-5 border border-slate-200/80 shadow-xs">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold text-emerald-700 uppercase tracking-wider">
                  Approved / Dispatched
                </span>
                <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
                  <CheckCircle2 className="w-4 h-4" />
                </div>
              </div>
              <div className="text-2xl font-bold text-emerald-600">{resolvedCount}</div>
              <p className="text-xs text-slate-500 mt-1">Technicians authorized</p>
            </div>

            {/* Escalated to VC */}
            <div className="bg-white rounded-xl p-5 border border-slate-200/80 shadow-xs">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold text-purple-700 uppercase tracking-wider">
                  VC Escalations
                </span>
                <div className="w-8 h-8 rounded-lg bg-purple-50 text-purple-600 flex items-center justify-center">
                  <ShieldAlert className="w-4 h-4" />
                </div>
              </div>
              <div className="text-2xl font-bold text-purple-700">{escalatedCount}</div>
              <p className="text-xs text-slate-500 mt-1">Automatic 3-strike escalation</p>
            </div>
          </div>
        </section>

        {/* Complaints List Table */}
        <section className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-200/80 flex items-center justify-between">
            <div>
              <h2 className="text-base font-bold text-slate-900">Your Filed Complaints</h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Strict student privacy: Only complaints submitted by your verified identity are shown.
              </p>
            </div>
            <Link
              href="/submit"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-50 text-blue-700 hover:bg-blue-100 transition-colors"
            >
              <PlusCircle className="w-3.5 h-3.5" />
              <span>New Complaint</span>
            </Link>
          </div>

          {isLoading ? (
            <div className="py-16 text-center">
              <Loader2 className="w-8 h-8 text-blue-600 animate-spin mx-auto mb-2" />
              <p className="text-sm text-slate-500">Loading your complaints...</p>
            </div>
          ) : errorMessage ? (
            <div className="p-8 text-center">
              <AlertCircle className="w-8 h-8 text-rose-500 mx-auto mb-2" />
              <p className="text-sm font-medium text-slate-800">{errorMessage}</p>
              <button
                onClick={handleRefresh}
                className="mt-3 px-4 py-2 text-xs font-semibold bg-slate-100 hover:bg-slate-200 rounded-lg text-slate-700"
              >
                Retry
              </button>
            </div>
          ) : grievances.length === 0 ? (
            <div className="py-16 text-center px-4">
              <div className="w-12 h-12 rounded-full bg-slate-100 text-slate-400 mx-auto flex items-center justify-center mb-3">
                <FileText className="w-6 h-6" />
              </div>
              <h3 className="text-sm font-semibold text-slate-800">No complaints filed yet</h3>
              <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1 mb-4">
                If you are experiencing hostel Wi-Fi, electricity, or maintenance issues, submit a complaint for immediate swarm triage.
              </p>
              <Link
                href="/submit"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold bg-blue-600 text-white hover:bg-blue-500 transition-colors"
              >
                <PlusCircle className="w-3.5 h-3.5" />
                <span>Submit Complaint</span>
              </Link>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm text-slate-600">
                <thead className="bg-slate-50 text-slate-700 text-xs uppercase font-semibold border-b border-slate-200">
                  <tr>
                    <th scope="col" className="px-6 py-3">Ticket Number</th>
                    <th scope="col" className="px-6 py-3">Title & Category</th>
                    <th scope="col" className="px-6 py-3">Status</th>
                    <th scope="col" className="px-6 py-3">Follow-ups</th>
                    <th scope="col" className="px-6 py-3">Submitted</th>
                    <th scope="col" className="px-6 py-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {grievances.map((item) => (
                    <tr key={item.id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="px-6 py-4 font-mono font-semibold text-slate-900">
                        {item.ticket_number}
                        {item.is_escalated_to_vc && (
                          <span className="ml-2 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-purple-100 text-purple-700 border border-purple-200">
                            VC Escalated
                          </span>
                        )}
                      </td>
                      <td className="px-6 py-4">
                        <div className="font-semibold text-slate-900">{item.title}</div>
                        <div className="text-xs text-slate-400 mt-0.5">{item.category}</div>
                      </td>
                      <td className="px-6 py-4">
                        <StatusBadge status={item.status} />
                      </td>
                      <td className="px-6 py-4">
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700">
                          {item.followup_count} {item.followup_count === 1 ? "report" : "reports"}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-xs text-slate-500 whitespace-nowrap">
                        {item.created_at ? new Date(item.created_at).toLocaleDateString() : "—"}
                      </td>
                      <td className="px-6 py-4 text-right whitespace-nowrap">
                        <Link
                          href={`/track?ticket=${encodeURIComponent(item.ticket_number)}`}
                          className="inline-flex items-center gap-1 text-xs font-semibold text-blue-600 hover:text-blue-800"
                        >
                          <span>Track</span>
                          <ArrowRight className="w-3.5 h-3.5" />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </RouteGuard>
  );
}
