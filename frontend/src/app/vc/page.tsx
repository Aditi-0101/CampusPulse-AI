"use client";

import React, { useState, useEffect } from "react";
import {
  Landmark,
  ShieldCheck,
  CheckCircle2,
  RefreshCw,
  Loader2,
  AlertCircle,
  FileText,
  History,
  X,
} from "lucide-react";
import {
  fetchVCEscalations,
  fetchVCEscalationDetail,
  submitVCDecision,
  ApiError,
} from "@/lib/api";
import {
  VCEscalationSummary,
  VCEscalationDetail,
} from "@/types/vc";
import { RouteGuard } from "@/components/RouteGuard";
import { useAuth } from "@/context/AuthContext";

type VCDecisionType =
  | "ACKNOWLEDGED"
  | "ACTION_REQUIRED"
  | "FORWARDED_FOR_INVESTIGATION"
  | "RESOLVED"
  | "REJECTED_WITH_REASON";

export default function ViceChancellorPortalPage() {
  const { user } = useAuth();

  const [statusFilter, setStatusFilter] = useState("ALL");
  const [escalations, setEscalations] = useState<VCEscalationSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<number | null>(null);

  // Detail Modal & Decision State
  const [activeEscalationId, setActiveEscalationId] = useState<string | null>(null);
  const [activeDetail, setActiveDetail] = useState<VCEscalationDetail | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [selectedDecision, setSelectedDecision] = useState<VCDecisionType | null>(null);
  const [remarks, setRemarks] = useState("");
  const [isSubmittingDecision, setIsSubmittingDecision] = useState(false);
  const [decisionError, setDecisionError] = useState<string | null>(null);

  const handleManualRefresh = async () => {
    setIsLoading(true);
    setErrorMessage(null);
    setErrorCode(null);

    try {
      const data = await fetchVCEscalations(
        undefined,
        statusFilter === "ALL" ? undefined : statusFilter
      );
      setEscalations(data);
    } catch (err: unknown) {
      setEscalations([]);
      if (err instanceof ApiError) {
        setErrorCode(err.status);
        setErrorMessage(err.message);
      } else {
        setErrorMessage(
          err instanceof Error ? err.message : "Failed to load Vice-Chancellor escalations."
        );
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    let ignore = false;
    fetchVCEscalations(
      undefined,
      statusFilter === "ALL" ? undefined : statusFilter
    )
      .then((data) => {
        if (!ignore) {
          setEscalations(data);
          setIsLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setEscalations([]);
          if (err instanceof ApiError) {
            setErrorCode(err.status);
            setErrorMessage(err.message);
          } else {
            setErrorMessage(
              err instanceof Error ? err.message : "Failed to load Vice-Chancellor escalations."
            );
          }
          setIsLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [statusFilter]);

  // Open detail modal
  const handleOpenDetail = async (escId: string) => {
    setActiveEscalationId(escId);
    setActiveDetail(null);
    setIsLoadingDetail(true);
    setDecisionError(null);
    setSelectedDecision(null);
    setRemarks("");

    try {
      const detail = await fetchVCEscalationDetail(undefined, escId);
      setActiveDetail(detail);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setDecisionError(`Failed to load details: ${err.message}`);
      } else {
        setDecisionError("Network error loading escalation details.");
      }
    } finally {
      setIsLoadingDetail(false);
    }
  };

  // Submit decision
  const handleSubmitDecision = async () => {
    if (!activeEscalationId || !selectedDecision) return;

    if (
      selectedDecision === "REJECTED_WITH_REASON" &&
      (!remarks || remarks.trim().length < 5)
    ) {
      setDecisionError("A formal reason (at least 5 characters) is required when rejecting an escalation.");
      return;
    }

    setIsSubmittingDecision(true);
    setDecisionError(null);

    try {
      await submitVCDecision(undefined, activeEscalationId, {
        decision: selectedDecision,
        remarks: remarks.trim() || undefined,
      });

      setActiveDetail(null);
      setActiveEscalationId(null);
      handleManualRefresh();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setDecisionError(err.message);
      } else {
        setDecisionError("An unexpected error occurred while recording executive decision.");
      }
    } finally {
      setIsSubmittingDecision(false);
    }
  };

  // Summary counts
  const totalCount = escalations.length;
  const pendingCount = escalations.filter((e) => e.status === "ESCALATED_TO_VC").length;
  const actionRequiredCount = escalations.filter((e) => e.status === "ACTION_REQUIRED").length;
  const investigatedCount = escalations.filter((e) => e.status === "FORWARDED_FOR_INVESTIGATION").length;
  const resolvedCount = escalations.filter((e) => e.status === "RESOLVED").length;

  return (
    <RouteGuard allowedPortals={["vc"]} requiredRole="VICE_CHANCELLOR">
      <div className="max-w-7xl mx-auto space-y-8 pb-16">
        {/* Page Header */}
        <div className="border-b border-slate-200 pb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-amber-700">
              <Landmark className="w-4 h-4" />
              <span>Executive University Governance</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
              Vice-Chancellor Escalation Portal
            </h1>
            <p className="text-sm text-slate-600 max-w-2xl leading-relaxed">
              Automated escalation queue for repeated unresolved grievances. Senior leadership
              review for issues reaching the verified 3-strike threshold.
            </p>
          </div>

          {/* Refresh & Invariant Badge */}
          <div className="flex items-center gap-3 self-start md:self-auto">
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-amber-50 border border-amber-200 text-amber-800 text-xs font-medium">
              <ShieldCheck className="w-4 h-4 text-amber-600" />
              <span>Human In The Loop Protected</span>
            </div>
            <button
              onClick={handleManualRefresh}
              disabled={isLoading}
              className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 text-xs font-semibold shadow-2xs transition-colors"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
              <span>Refresh</span>
            </button>
          </div>
        </div>

        {/* Human Governance Invariant Alert */}
        <div className="bg-amber-50/70 border border-amber-200 rounded-2xl p-4 text-xs text-amber-950 flex items-start gap-3">
          <Landmark className="w-5 h-5 text-amber-700 shrink-0 mt-0.5" />
          <div className="space-y-1 leading-relaxed">
            <span className="font-bold text-amber-900">Executive Policy Constraint:</span>
            <p>
              The backend automatically counts and flags grievances matching the verified 3-complaint threshold.
              However, automated agents are strictly forbidden from deciding on behalf of the Vice-Chancellor.
              All determinations require binding authenticated human executive review.
            </p>
          </div>
        </div>

        {/* Executive Session Identity Card */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-5 sm:p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-amber-100 text-amber-800 flex items-center justify-center font-bold">
              <Landmark className="w-5 h-5" />
            </div>
            <div>
              <div className="text-xs font-semibold text-amber-800 uppercase tracking-wider">
                Office of the Vice-Chancellor
              </div>
              <div className="text-base font-bold text-slate-900">
                {user?.name || "Vice-Chancellor Executive"}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-mono font-semibold bg-amber-50 text-amber-800 border border-amber-200">
              Role: {user?.role}
            </span>
            <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200">
              Executive Session Active
            </span>
          </div>
        </div>

        {/* Metrics Row */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
          <div className="bg-white rounded-xl border border-slate-200 p-4 space-y-1">
            <div className="text-xs text-slate-500 font-medium">Total Escalations</div>
            <div className="text-2xl font-bold text-slate-900">{totalCount}</div>
            <div className="text-[11px] text-slate-400">All 3-strike issues</div>
          </div>
          <div className="bg-white rounded-xl border border-amber-200 bg-amber-50/30 p-4 space-y-1">
            <div className="text-xs text-amber-800 font-semibold">Pending Review</div>
            <div className="text-2xl font-bold text-amber-900">{pendingCount}</div>
            <div className="text-[11px] text-amber-700">Awaiting VC decision</div>
          </div>
          <div className="bg-white rounded-xl border border-blue-200 bg-blue-50/30 p-4 space-y-1">
            <div className="text-xs text-blue-800 font-semibold">Action Required</div>
            <div className="text-2xl font-bold text-blue-900">{actionRequiredCount}</div>
            <div className="text-[11px] text-blue-700">Directives issued</div>
          </div>
          <div className="bg-white rounded-xl border border-purple-200 bg-purple-50/30 p-4 space-y-1">
            <div className="text-xs text-purple-800 font-semibold">Under Investigation</div>
            <div className="text-2xl font-bold text-purple-900">{investigatedCount}</div>
            <div className="text-[11px] text-purple-700">Formal committee probe</div>
          </div>
          <div className="bg-white rounded-xl border border-emerald-200 bg-emerald-50/30 p-4 space-y-1">
            <div className="text-xs text-emerald-800 font-semibold">Resolved by VC</div>
            <div className="text-2xl font-bold text-emerald-900">{resolvedCount}</div>
            <div className="text-[11px] text-emerald-700">Closed under VC order</div>
          </div>
        </div>

        {/* Filter Controls & Escalation List */}
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-slate-700">Filter Status:</span>
              {["ALL", "ESCALATED_TO_VC", "ACTION_REQUIRED", "FORWARDED_FOR_INVESTIGATION", "RESOLVED"].map((st) => (
                <button
                  key={st}
                  onClick={() => setStatusFilter(st)}
                  className={`text-xs px-2.5 py-1 rounded-md font-medium transition-colors ${
                    statusFilter === st
                      ? "bg-[#0f2744] text-white"
                      : "bg-white border border-slate-300 text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  {st.replace(/_/g, " ")}
                </button>
              ))}
            </div>

            <div className="text-xs text-slate-500">
              Showing <span className="font-semibold text-slate-900">{escalations.length}</span> escalations
            </div>
          </div>

          {/* Error Notice */}
          {errorMessage && (
            <div className="bg-rose-50 border border-rose-200 rounded-xl p-4 flex items-start gap-3 text-xs text-rose-800">
              <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
              <div className="space-y-1">
                <span className="font-bold">Authorization Notice ({errorCode || "Error"}):</span>
                <p className="leading-relaxed">{errorMessage}</p>
              </div>
            </div>
          )}

          {/* Loading Indicator */}
          {isLoading && (
            <div className="py-16 text-center text-slate-500 space-y-2">
              <Loader2 className="w-6 h-6 animate-spin mx-auto text-amber-700" />
              <p className="text-xs font-medium">Fetching Vice-Chancellor escalations...</p>
            </div>
          )}

          {/* Empty State */}
          {!isLoading && escalations.length === 0 && !errorMessage && (
            <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center space-y-3">
              <CheckCircle2 className="w-8 h-8 text-emerald-600 mx-auto" />
              <h3 className="text-sm font-bold text-slate-900">No Escalations in Queue</h3>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                No student complaints currently meet the 3-strike repeated grievance criteria for this filter.
              </p>
            </div>
          )}

          {/* Escalation Cards */}
          {!isLoading && escalations.length > 0 && (
            <div className="grid grid-cols-1 gap-4">
              {escalations.map((esc) => (
                <div
                  key={esc.escalation_id}
                  className="bg-white rounded-2xl border border-slate-200/80 hover:border-slate-300 shadow-2xs p-5 transition-all space-y-4"
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-3">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="px-2 py-0.5 rounded bg-amber-100 text-amber-900 border border-amber-300 font-mono text-xs font-bold">
                        {esc.trigger_ticket_number}
                      </span>
                      <span className="text-xs font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-700">
                        {esc.category}
                      </span>
                      <span className="text-xs px-2 py-0.5 rounded bg-slate-100 font-mono text-slate-600">
                        {esc.location_ref}
                      </span>
                      <span className="px-2 py-0.5 rounded bg-rose-100 text-rose-800 text-xs font-bold">
                        {esc.complaint_count} Complaints Logged
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="text-[11px] text-slate-400">
                        Escalated: {new Date(esc.escalated_at).toLocaleString()}
                      </span>
                      <span
                        className={`text-xs px-2.5 py-0.5 rounded-full font-bold ${
                          esc.status === "ESCALATED_TO_VC"
                            ? "bg-amber-100 text-amber-800 border border-amber-300"
                            : esc.status === "ACTION_REQUIRED"
                            ? "bg-blue-100 text-blue-800"
                            : esc.status === "RESOLVED"
                            ? "bg-emerald-100 text-emerald-800"
                            : "bg-slate-100 text-slate-700"
                        }`}
                      >
                        {esc.status.replace(/_/g, " ")}
                      </span>
                    </div>
                  </div>

                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div className="space-y-1">
                      <h3 className="text-base font-bold text-slate-900">{esc.title}</h3>
                      <p className="text-xs text-slate-500 max-w-2xl line-clamp-2">
                        Responsible Department: <strong>{esc.responsible_department}</strong> • Thread: <code className="font-mono">{esc.thread_id}</code>
                      </p>
                    </div>

                    <button
                      onClick={() => handleOpenDetail(esc.escalation_id)}
                      className="self-start md:self-center px-4 py-2 rounded-lg bg-[#0f2744] hover:bg-[#163252] text-white text-xs font-semibold transition-colors flex items-center gap-1.5 shrink-0"
                    >
                      <FileText className="w-3.5 h-3.5" />
                      <span>Review & Decide</span>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Modal: Escalation Detail & Decision */}
        {activeEscalationId && (
          <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl max-w-3xl w-full max-h-[90vh] overflow-y-auto shadow-2xl p-6 sm:p-8 space-y-6">
              {/* Modal Header */}
              <div className="flex items-start justify-between border-b border-slate-200 pb-4">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold uppercase tracking-wider text-amber-700">
                      Vice-Chancellor Formal Inquiry
                    </span>
                    {activeDetail && (
                      <span className="font-mono text-xs px-2 py-0.5 rounded bg-amber-100 text-amber-900 font-bold">
                        {activeDetail.trigger_ticket_number}
                      </span>
                    )}
                  </div>
                  <h2 className="text-lg font-extrabold text-slate-900 mt-1">
                    {activeDetail?.title || "Escalation Audit Trail"}
                  </h2>
                </div>
                <button
                  onClick={() => {
                    setActiveEscalationId(null);
                    setActiveDetail(null);
                  }}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {isLoadingDetail && (
                <div className="py-16 text-center text-slate-500 space-y-2">
                  <Loader2 className="w-6 h-6 animate-spin mx-auto text-amber-700" />
                  <p className="text-xs">Loading complete audit history and timeline...</p>
                </div>
              )}

              {decisionError && (
                <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs">
                  {decisionError}
                </div>
              )}

              {activeDetail && !isLoadingDetail && (
                <div className="space-y-6 text-xs text-slate-700">
                  {/* Summary Box */}
                  <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
                    <div className="font-bold text-slate-900">Escalation Description & Rationale:</div>
                    <p className="leading-relaxed">{activeDetail.description}</p>
                    <div className="flex gap-4 pt-2 text-[11px] text-slate-500">
                      <span>Threshold: <strong>{activeDetail.complaint_count} Reports</strong></span>
                      <span>Zone: <strong>{activeDetail.location_ref}</strong></span>
                      <span>Department: <strong>{activeDetail.responsible_department}</strong></span>
                    </div>
                  </div>

                  {/* Complaint Audit Trail */}
                  <div className="space-y-2">
                    <div className="font-bold text-slate-900 flex items-center gap-1.5">
                      <History className="w-4 h-4 text-slate-600" />
                      <span>Thread History ({activeDetail.linked_grievances.length} Lodged Reports)</span>
                    </div>
                    <div className="divide-y divide-slate-100 border border-slate-200 rounded-xl overflow-hidden">
                      {activeDetail.linked_grievances.map((item) => (
                        <div key={item.ticket_number} className="p-3 bg-white hover:bg-slate-50 space-y-1">
                          <div className="flex items-center justify-between">
                            <span className="font-mono font-bold text-blue-700">{item.ticket_number}</span>
                            <span className="text-[10px] text-slate-400 font-mono">{item.created_at || "—"}</span>
                          </div>
                          <div className="font-semibold text-slate-900">{item.title}</div>
                          <p className="text-slate-600 text-[11px]">{item.description}</p>
                          <div className="text-[10px] text-slate-500">
                            Status: <span className="font-semibold text-slate-700">{item.status}</span> • Reports: {item.followup_count}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Decision Controls */}
                  <div className="space-y-3 pt-2 border-t border-slate-200">
                    <div className="font-bold text-slate-900">
                      Record Binding Vice-Chancellor Determination:
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {[
                        {
                          val: "ACTION_REQUIRED",
                          label: "Direct Immediate Action",
                          desc: "Mandate rapid physical resolution from campus supervisors",
                        },
                        {
                          val: "FORWARDED_FOR_INVESTIGATION",
                          label: "Order Formal Investigation",
                          desc: "Refer for infrastructure negligence inquiry",
                        },
                        {
                          val: "ACKNOWLEDGED",
                          label: "Acknowledge Escalation",
                          desc: "Log executive awareness and keep under continuous observation",
                        },
                        {
                          val: "RESOLVED",
                          label: "Mark Incident Resolved",
                          desc: "Confirm full operational restoration on university authority",
                        },
                        {
                          val: "REJECTED_WITH_REASON",
                          label: "Reject Escalation (Justification Required)",
                          desc: "Dismiss escalation with written administrative rationale",
                        },
                      ].map((opt) => (
                        <button
                          key={opt.val}
                          type="button"
                          onClick={() => setSelectedDecision(opt.val as VCDecisionType)}
                          className={`p-3 rounded-xl border text-left transition-all space-y-1 ${
                            selectedDecision === opt.val
                              ? "border-amber-600 bg-amber-50/60 ring-2 ring-amber-500/30"
                              : "border-slate-200 hover:border-slate-300 bg-white"
                          }`}
                        >
                          <div className="font-bold text-slate-900">{opt.label}</div>
                          <div className="text-[11px] text-slate-500 leading-tight">{opt.desc}</div>
                        </button>
                      ))}
                    </div>

                    <div className="space-y-1.5 pt-2">
                      <label className="block text-xs font-semibold text-slate-700">
                        Executive Remarks / Directives {selectedDecision === "REJECTED_WITH_REASON" && "(Required)"}
                      </label>
                      <textarea
                        rows={3}
                        value={remarks}
                        onChange={(e) => setRemarks(e.target.value)}
                        placeholder="Enter binding directives, departmental mandates, or rejection justification..."
                        className="w-full px-3 py-2 border border-slate-300 rounded-xl text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-500"
                      />
                    </div>
                  </div>
                </div>
              )}

              {/* Modal Footer */}
              <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => {
                    setActiveEscalationId(null);
                    setActiveDetail(null);
                  }}
                  className="px-4 py-2 border border-slate-300 rounded-lg text-xs font-medium text-slate-700 hover:bg-slate-100"
                >
                  Close
                </button>
                <button
                  disabled={!selectedDecision || isSubmittingDecision}
                  onClick={handleSubmitDecision}
                  className="px-5 py-2 bg-amber-700 hover:bg-amber-800 disabled:bg-slate-300 disabled:cursor-not-allowed text-white text-xs font-semibold rounded-lg shadow-xs transition-colors flex items-center gap-1.5"
                >
                  {isSubmittingDecision ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      <span>Recording...</span>
                    </>
                  ) : (
                    <span>Submit Binding Decision</span>
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
