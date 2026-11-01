"use client";

import React, { useState, useEffect } from "react";
import {
  ShieldAlert,
  ShieldCheck,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  RefreshCw,
  UserCheck,
  Loader2,
} from "lucide-react";
import {
  fetchPendingApprovals,
  submitApprovalDecision,
  ApiError,
} from "@/lib/api";
import {
  PendingApprovalItem,
  ApprovalDecisionResponse,
} from "@/types/grievance";
import { StatusBadge } from "@/components/StatusBadge";
import { RouteGuard } from "@/components/RouteGuard";
import { useAuth } from "@/context/AuthContext";

export default function AdminPortalPage() {
  const { user } = useAuth();

  const [pendingItems, setPendingItems] = useState<PendingApprovalItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<number | null>(null);

  // Decision Modal State
  const [activeItem, setActiveItem] = useState<PendingApprovalItem | null>(null);
  const [decisionType, setDecisionType] = useState<"APPROVED" | "REJECTED" | null>(null);
  const [rejectionReason, setRejectionReason] = useState("");
  const [assignedTechnician, setAssignedTechnician] = useState("");
  const [isSubmittingDecision, setIsSubmittingDecision] = useState(false);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [recentDecisions, setRecentDecisions] = useState<ApprovalDecisionResponse[]>([]);

  const handleRefreshQueue = async () => {
    setIsLoading(true);
    setErrorMessage(null);
    setErrorCode(null);

    try {
      const items = await fetchPendingApprovals();
      setPendingItems(items);
    } catch (err: unknown) {
      setPendingItems([]);
      if (err instanceof ApiError) {
        setErrorCode(err.status);
        setErrorMessage(err.message);
      } else {
        setErrorCode(0);
        setErrorMessage(
          err instanceof Error ? err.message : "Failed to communicate with approval service."
        );
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    let ignore = false;
    fetchPendingApprovals()
      .then((items) => {
        if (!ignore) {
          setPendingItems(items);
          setIsLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setPendingItems([]);
          if (err instanceof ApiError) {
            setErrorCode(err.status);
            setErrorMessage(err.message);
          } else {
            setErrorCode(0);
            setErrorMessage(
              err instanceof Error ? err.message : "Failed to communicate with approval service."
            );
          }
          setIsLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, []);

  // Open modal for decision
  const handleOpenDecisionModal = (
    item: PendingApprovalItem,
    type: "APPROVED" | "REJECTED"
  ) => {
    setActiveItem(item);
    setDecisionType(type);
    setRejectionReason("");
    setAssignedTechnician("");
    setDecisionError(null);
  };

  const handleCloseModal = () => {
    setActiveItem(null);
    setDecisionType(null);
    setRejectionReason("");
    setAssignedTechnician("");
    setDecisionError(null);
    setIsSubmittingDecision(false);
  };

  // Submit approval or rejection
  const handleSubmitDecision = async () => {
    if (!activeItem || !decisionType) return;

    if (decisionType === "REJECTED" && (!rejectionReason || rejectionReason.trim().length < 3)) {
      setDecisionError("A justification reason (at least 3 characters) is required when rejecting.");
      return;
    }

    setIsSubmittingDecision(true);
    setDecisionError(null);

    try {
      const response = await submitApprovalDecision(
        activeItem.ticket_number,
        {
          decision: decisionType,
          reason: decisionType === "REJECTED" ? rejectionReason.trim() : rejectionReason.trim() || null,
          assigned_technician: assignedTechnician.trim() || null,
        }
      );

      // Successfully processed: update UI
      setRecentDecisions((prev) => [response, ...prev]);
      setPendingItems((prev) => prev.filter((p) => p.ticket_number !== activeItem.ticket_number));
      handleCloseModal();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setDecisionError(err.message);
      } else {
        setDecisionError(
          err instanceof Error ? err.message : "Decision failed due to an unexpected error."
        );
      }
    } finally {
      setIsSubmittingDecision(false);
    }
  };

  const isReadOnly = user?.role === "READ_ONLY";

  return (
    <RouteGuard allowedPortals={["admin"]}>
      <div className="space-y-8 pb-12">
        {/* 1. Header Banner */}
        <section className="bg-gradient-to-r from-[#0f2744] via-[#16355d] to-[#1e4577] text-white rounded-2xl p-6 sm:p-8 shadow-sm border border-[#1e3a5f]">
          <div className="max-w-4xl space-y-3">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-500/20 text-amber-300 border border-amber-400/20 text-xs font-semibold">
              <ShieldAlert className="w-3.5 h-3.5" />
              <span>Human-in-the-Loop Operational Oversight</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight">
              CampusPulse AI — Staff Admin Portal
            </h1>
            <p className="text-sm sm:text-base text-slate-200 leading-relaxed font-normal">
              Review complaints escalated by the autonomous AI swarm. Authorize technician
              dispatches or mandate alternative remediations with strict role-based access control.
            </p>
          </div>
        </section>

        {/* 2. Staff Session Profile Bar */}
        <section className="bg-white rounded-2xl border border-slate-200 shadow-xs p-5 sm:p-6 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4">
            <div className="space-y-0.5">
              <div className="flex items-center gap-2">
                <UserCheck className="w-4 h-4 text-blue-700" />
                <h2 className="text-sm font-bold text-slate-900">
                  Staff Authentication Session
                </h2>
              </div>
              <p className="text-xs text-slate-500">
                Identity and RBAC permissions are strictly resolved server-side from your authenticated session.
              </p>
            </div>

            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-200">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
                <div className="text-xs">
                  <span className="font-bold text-slate-900">{user?.name || "Staff Member"}</span>
                  <span className="text-slate-400 mx-1.5">•</span>
                  <span className="font-mono text-blue-700 font-semibold">{user?.role}</span>
                </div>
              </div>

              <button
                type="button"
                onClick={handleRefreshQueue}
                disabled={isLoading}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
                <span>Refresh Queue</span>
              </button>
            </div>
          </div>

          {/* Role Status Note */}
          {isReadOnly ? (
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-3.5 flex items-start gap-3 text-xs text-amber-900">
              <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
              <div className="space-y-0.5 leading-relaxed">
                <span className="font-bold">Read-Only Auditor Mode:</span>
                <p>
                  You are authenticated with READ_ONLY role. You can inspect pending approvals and swarm telemetry, but submitting approval decisions is blocked by backend RBAC.
                </p>
              </div>
            </div>
          ) : (
            <div className="bg-emerald-50/70 border border-emerald-200 rounded-xl p-3 flex items-center justify-between text-xs text-emerald-900">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-emerald-600" />
                <span>Full Human-in-the-Loop decision authority enabled for your role ({user?.role}).</span>
              </div>
              <span className="font-mono text-[11px] text-emerald-700">RBAC: Enforced</span>
            </div>
          )}
        </section>

        {/* 3. Pending Approvals Queue */}
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold text-slate-900">Pending Review Queue</h2>
              <p className="text-xs text-slate-500">
                Grievances awaiting human approval before technician dispatch.
              </p>
            </div>
            <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-blue-50 text-blue-700 border border-blue-200">
              {pendingItems.length} awaiting decision
            </span>
          </div>

          {/* Loading State */}
          {isLoading && (
            <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center space-y-3">
              <Loader2 className="w-8 h-8 text-blue-600 animate-spin mx-auto" />
              <p className="text-sm font-semibold text-slate-700">
                Retrieving pending approvals from backend...
              </p>
            </div>
          )}

          {/* Error Message */}
          {errorMessage && !isLoading && (
            <div className="bg-rose-50 border border-rose-200 rounded-2xl p-6 text-center space-y-2">
              <AlertTriangle className="w-8 h-8 text-rose-600 mx-auto" />
              <h3 className="text-sm font-bold text-rose-900">
                {errorCode === 403 ? "Authorization Restricted (403)" : "Queue Retrieval Error"}
              </h3>
              <p className="text-xs text-rose-700 max-w-md mx-auto">{errorMessage}</p>
              <button
                type="button"
                onClick={handleRefreshQueue}
                className="mt-3 px-4 py-2 bg-rose-100 hover:bg-rose-200 text-rose-800 rounded-lg text-xs font-semibold"
              >
                Retry
              </button>
            </div>
          )}

          {/* Empty State */}
          {!isLoading && !errorMessage && pendingItems.length === 0 && (
            <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center space-y-4 shadow-xs">
              <div className="w-12 h-12 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center mx-auto">
                <CheckCircle2 className="w-6 h-6" />
              </div>
              <div className="max-w-md mx-auto space-y-1">
                <h3 className="text-base font-bold text-slate-900">
                  Queue Clear — No Pending Approvals
                </h3>
                <p className="text-xs text-slate-500 leading-relaxed">
                  All campus grievances have been triaged and resolved by supervisors. New escalated complaints
                  will automatically appear here when lodged by students.
                </p>
              </div>
            </div>
          )}

          {/* List of Pending Grievances */}
          {!isLoading && pendingItems.length > 0 && (
            <div className="space-y-4">
              {pendingItems.map((item) => (
                <div
                  key={item.ticket_number}
                  className="bg-white rounded-2xl border border-slate-200 shadow-xs hover:border-slate-300 transition-colors p-6 space-y-5"
                >
                  {/* Header row */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono text-xs font-bold text-blue-800 bg-blue-50 px-2.5 py-1 rounded border border-blue-200">
                          {item.ticket_number}
                        </span>
                        <StatusBadge status={item.status} size="sm" />
                        <span className="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-600 font-medium">
                          Zone: <code className="font-mono">{item.location_ref}</code>
                        </span>
                        <span
                          className={`text-xs px-2 py-0.5 rounded font-semibold uppercase ${
                            item.urgency === "HIGH" || item.urgency === "CRITICAL"
                              ? "bg-rose-100 text-rose-800"
                              : "bg-blue-50 text-blue-700"
                          }`}
                        >
                          Urgency: {item.urgency}
                        </span>
                      </div>
                      <h3 className="text-base font-bold text-slate-900 pt-1">
                        {item.title}
                      </h3>
                    </div>

                    {/* Action buttons */}
                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        type="button"
                        onClick={() => handleOpenDecisionModal(item, "APPROVED")}
                        className="inline-flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold shadow-xs transition-colors"
                      >
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span>Authorize Dispatch</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => handleOpenDecisionModal(item, "REJECTED")}
                        className="inline-flex items-center gap-1.5 px-4 py-2 bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 rounded-lg text-xs font-semibold transition-colors"
                      >
                        <XCircle className="w-3.5 h-3.5" />
                        <span>Reject</span>
                      </button>
                    </div>
                  </div>

                  {/* Recommendation Details */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                    <div className="bg-slate-50 rounded-xl p-3.5 border border-slate-100 space-y-1.5">
                      <span className="font-semibold text-slate-500 uppercase tracking-wider text-[10px]">
                        AI Swarm Recommendation
                      </span>
                      <p className="font-medium text-slate-900 leading-relaxed">
                        {item.ai_recommendation || "Standard technician dispatch required."}
                      </p>
                      {item.recommended_department && (
                        <p className="text-slate-600">
                          Recommended Department: <strong className="text-slate-900">{item.recommended_department}</strong>
                        </p>
                      )}
                    </div>

                    <div className="bg-slate-50 rounded-xl p-3.5 border border-slate-100 space-y-1.5">
                      <span className="font-semibold text-slate-500 uppercase tracking-wider text-[10px]">
                        Meko Swarm Context
                      </span>
                      <p className="text-slate-700 leading-relaxed">
                        {item.meko_context_summary || "Autonomous knowledge base verification completed."}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* 4. Recent Decisions History */}
        {recentDecisions.length > 0 && (
          <section className="bg-white rounded-2xl border border-slate-200 shadow-xs p-6 space-y-4">
            <h2 className="text-base font-bold text-slate-900">
              Decisions Recorded in this Session
            </h2>
            <div className="divide-y divide-slate-100 text-xs">
              {recentDecisions.map((dec, idx) => (
                <div key={idx} className="py-3 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold text-slate-800">
                      {dec.ticket_number}
                    </span>
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        dec.decision === "APPROVED"
                          ? "bg-emerald-100 text-emerald-800"
                          : "bg-rose-100 text-rose-800"
                      }`}
                    >
                      {dec.decision}
                    </span>
                    <span className="text-slate-500">
                      by {dec.reviewer_id} ({dec.reviewer_role})
                    </span>
                  </div>
                  <span className="text-slate-400 font-mono text-[11px]">
                    {new Date(dec.decided_at).toLocaleTimeString()}
                  </span>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Decision Modal */}
        {activeItem && decisionType && (
          <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-xl space-y-4 animate-in fade-in zoom-in-95">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                <div className="flex items-center gap-2">
                  {decisionType === "APPROVED" ? (
                    <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
                      <CheckCircle2 className="w-5 h-5" />
                    </div>
                  ) : (
                    <div className="w-8 h-8 rounded-lg bg-rose-50 text-rose-600 flex items-center justify-center">
                      <XCircle className="w-5 h-5" />
                    </div>
                  )}
                  <div>
                    <h3 className="text-sm font-bold text-slate-900">
                      {decisionType === "APPROVED" ? "Authorize Dispatch" : "Reject Recommendation"}
                    </h3>
                    <p className="text-xs text-slate-500 font-mono">{activeItem.ticket_number}</p>
                  </div>
                </div>
                <button
                  onClick={handleCloseModal}
                  className="text-slate-400 hover:text-slate-600 text-sm font-bold"
                >
                  ✕
                </button>
              </div>

              {decisionError && (
                <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs">
                  {decisionError}
                </div>
              )}

              {decisionType === "APPROVED" ? (
                <div className="space-y-3">
                  <p className="text-xs text-slate-600">
                    Confirm authorizing field technician dispatch for <strong>{activeItem.title}</strong>.
                  </p>
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">
                      Assigned Technician (Optional)
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. Ramesh Kumar (NetOps)"
                      value={assignedTechnician}
                      onChange={(e) => setAssignedTechnician(e.target.value)}
                      className="w-full px-3 py-2 border border-slate-300 rounded-lg text-xs"
                    />
                  </div>
                </div>
              ) : (
                <div className="space-y-3">
                  <p className="text-xs text-slate-600">
                    Mandate a justification for rejecting the swarm triage recommendation.
                  </p>
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">
                      Rejection Reason (Required)
                    </label>
                    <textarea
                      rows={3}
                      placeholder="Explain why technician dispatch is rejected or alternative resolution steps required..."
                      value={rejectionReason}
                      onChange={(e) => setRejectionReason(e.target.value)}
                      className="w-full px-3 py-2 border border-slate-300 rounded-lg text-xs focus:ring-2 focus:ring-blue-500"
                    />
                  </div>
                </div>
              )}

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={handleCloseModal}
                  disabled={isSubmittingDecision}
                  className="px-4 py-2 rounded-lg border border-slate-300 text-xs font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleSubmitDecision}
                  disabled={isSubmittingDecision}
                  className={`px-4 py-2 rounded-lg text-xs font-semibold text-white transition-colors ${
                    decisionType === "APPROVED"
                      ? "bg-emerald-600 hover:bg-emerald-700"
                      : "bg-rose-600 hover:bg-rose-700"
                  }`}
                >
                  {isSubmittingDecision ? (
                    <span className="flex items-center gap-1.5">
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      <span>Recording...</span>
                    </span>
                  ) : decisionType === "APPROVED" ? (
                    "Confirm Dispatch"
                  ) : (
                    "Confirm Rejection"
                  )}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </RouteGuard>
  );
}
