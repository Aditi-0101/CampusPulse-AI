"use client";

import React, { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  Search,
  Clock,
  AlertCircle,
  Copy,
  Check,
  Building,
  Calendar,
  ArrowRight,
  ShieldCheck,
  Loader2,
  FileQuestion,
  HelpCircle,
  Landmark,
} from "lucide-react";
import { trackGrievance, useRecentTickets, ApiError } from "@/lib/api";
import { StudentGrievanceTrackResponse } from "@/types/grievance";
import { StatusBadge } from "@/components/StatusBadge";
import { RouteGuard } from "@/components/RouteGuard";


function TrackContent() {
  const searchParams = useSearchParams();
  const initialTicket = searchParams.get("ticket") || "";

  const [ticketInput, setTicketInput] = useState(initialTicket);
  const [activeTicket, setActiveTicket] = useState<string | null>(initialTicket || null);
  const [trackingData, setTrackingData] = useState<StudentGrievanceTrackResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [is404, setIs404] = useState(false);
  const [copied, setCopied] = useState(false);
  const recentTickets = useRecentTickets();

  const executeTrack = async (ticketToFetch: string) => {
    const clean = ticketToFetch.trim();
    if (!clean) return;

    setIsLoading(true);
    setErrorMessage(null);
    setIs404(false);
    setActiveTicket(clean);

    try {
      const data = await trackGrievance(clean);
      setTrackingData(data);
    } catch (err: unknown) {
      setTrackingData(null);
      if (err instanceof ApiError) {
        if (err.status === 404) {
          setIs404(true);
          setErrorMessage(err.message || `No grievance ticket found for "${clean}".`);
        } else if (err.status === 403) {
          setErrorMessage("Access Restricted: You are only authorized to track complaints that you own.");
        } else {
          setErrorMessage(err.message);
        }
      } else {
        setErrorMessage(
          err instanceof Error ? err.message : "Failed to connect to campus network service."
        );
      }
    } finally {
      setIsLoading(false);
    }
  };

  // Auto-fetch if ticket param was provided in URL
  useEffect(() => {
    if (initialTicket) {
      let isMounted = true;
      trackGrievance(initialTicket.trim())
        .then((data) => {
          if (isMounted) {
            setTrackingData(data);
            setActiveTicket(initialTicket.trim());
          }
        })
        .catch((err: unknown) => {
          if (isMounted) {
            setTrackingData(null);
            setActiveTicket(initialTicket.trim());
            if (err instanceof ApiError && err.status === 404) {
              setIs404(true);
              setErrorMessage(err.message || `No grievance ticket found for "${initialTicket.trim()}".`);
            } else {
              setErrorMessage(
                err instanceof Error ? err.message : "Failed to connect to campus network service."
              );
            }
          }
        });
      return () => {
        isMounted = false;
      };
    }
  }, [initialTicket]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    executeTrack(ticketInput);
  };

  const handleCopyTicket = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Timeline stage calculation
  const getTimelineSteps = (status: string) => {
    const s = (status || "").toUpperCase();

    // 1: Submitted, 2: Triaged, 3: Operational Plan, 4: Approved/Rejected/Resolved
    let currentStep = 1;

    if (s === "SUBMITTED") {
      currentStep = 1;
    } else if (s === "TRIAGED") {
      currentStep = 2;
    } else if (s === "PENDING_APPROVAL") {
      currentStep = 3;
    } else if (["APPROVED", "ASSIGNED", "RESOLVED", "CLOSED", "REJECTED"].includes(s)) {
      currentStep = 4;
    }

    const steps = [
      {
        id: 1,
        title: "Intake Received",
        description: "Recorded in CampusPulse intake queue",
      },
      {
        id: 2,
        title: "Swarm Triage",
        description: "Front Desk agent assessed urgency & checked past incidents",
      },
      {
        id: 3,
        title: "Operational Review",
        description: "Dispatch agent formulated repair plan & estimated SLA",
      },
      {
        id: 4,
        title:
          s === "REJECTED"
            ? "Reviewed (Alternative Remediation)"
            : s === "APPROVED" || s === "ASSIGNED" || s === "RESOLVED"
            ? "Approved for Dispatch"
            : "Supervisor Authorization",
        description:
          s === "REJECTED"
            ? "Supervisor reviewed; re-routed to alternative remediation"
            : s === "APPROVED" || s === "ASSIGNED" || s === "RESOLVED"
            ? "Authorized by campus supervisor; work order released"
            : "Awaiting staff authorization for dispatch",
      },
    ];

    return { currentStep, steps };
  };

  const timelineInfo = trackingData ? getTimelineSteps(trackingData.status) : null;

  return (
    <div className="max-w-4xl mx-auto space-y-6 pb-12">
      {/* Header */}
      <div className="space-y-1.5 border-b border-slate-200 pb-4">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-blue-700">
          <Search className="w-4 h-4" />
          <span>Real-Time Grievance Tracking</span>
        </div>
        <h1 className="text-2xl font-bold text-slate-900">
          Track Grievance Status
        </h1>
        <p className="text-sm text-slate-600">
          Enter your ticket number to view the live multi-agent swarm status and supervisor approval timeline.
        </p>
      </div>

      {/* Ticket Lookup Form */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-5 sm:p-6 space-y-4">
        <form onSubmit={handleSearchSubmit} className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              type="text"
              required
              placeholder="e.g. CP-HOSTEL_WIFI-20261101-ABCD"
              value={ticketInput}
              onChange={(e) => setTicketInput(e.target.value.toUpperCase())}
              className="w-full pl-10 pr-4 py-2.5 bg-slate-50 border border-slate-300 rounded-lg text-sm font-mono text-slate-900 placeholder:font-sans placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 focus:bg-white uppercase tracking-wider"
            />
          </div>
          <button
            type="submit"
            disabled={isLoading || !ticketInput.trim()}
            className="inline-flex items-center justify-center gap-2 px-6 py-2.5 rounded-lg bg-blue-700 hover:bg-blue-800 disabled:bg-slate-300 disabled:cursor-not-allowed text-white font-semibold text-sm transition-colors shadow-xs shrink-0"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Tracking...</span>
              </>
            ) : (
              <>
                <Search className="w-4 h-4" />
                <span>Track Ticket</span>
              </>
            )}
          </button>
        </form>

        {/* Quick select chips from recent tickets */}
        {recentTickets.length > 0 && (
          <div className="pt-2 border-t border-slate-100 flex items-center gap-2 flex-wrap">
            <span className="text-xs text-slate-400 font-medium">Recently on this device:</span>
            {recentTickets.slice(0, 3).map((item) => (
              <button
                key={item.ticketNumber}
                type="button"
                onClick={() => {
                  setTicketInput(item.ticketNumber);
                  executeTrack(item.ticketNumber);
                }}
                className="text-xs font-mono px-2.5 py-1 bg-slate-100 hover:bg-blue-50 hover:text-blue-700 text-slate-700 rounded border border-slate-200 transition-colors"
              >
                {item.ticketNumber}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* 404 Error State */}
      {is404 && (
        <div className="bg-white rounded-2xl border border-slate-200 p-8 text-center space-y-4 shadow-xs">
          <div className="w-12 h-12 rounded-full bg-amber-50 text-amber-600 flex items-center justify-center mx-auto">
            <FileQuestion className="w-6 h-6" />
          </div>
          <div className="max-w-md mx-auto space-y-1">
            <h3 className="text-base font-bold text-slate-900">
              Ticket Not Found
            </h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              We couldn&apos;t locate any grievance record for{" "}
              <code className="text-blue-800 font-mono font-semibold bg-slate-100 px-1 py-0.5 rounded">
                {activeTicket}
              </code>
              . Please verify the ticket code format or submit a new grievance report.
            </p>
          </div>
          <div className="pt-2 flex justify-center gap-3">
            <Link
              href="/submit"
              className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-blue-700 hover:bg-blue-800 rounded-lg shadow-xs transition-colors"
            >
              <span>Submit New Grievance</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>
      )}

      {/* Other Error State (e.g. Network Failure) */}
      {!is404 && errorMessage && (
        <div className="bg-rose-50 border border-rose-200 rounded-2xl p-6 flex items-start gap-3 text-xs text-rose-800">
          <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <span className="font-bold text-sm">Tracking Service Alert:</span>
            <p className="leading-relaxed">{errorMessage}</p>
            <p className="text-slate-500 pt-1">
              Ensure the FastAPI backend is running on{" "}
              <code className="font-mono text-slate-700">http://localhost:8000</code>.
            </p>
          </div>
        </div>
      )}

      {/* Successful Tracking Details View */}
      {trackingData && (
        <div className="space-y-6">
          {/* Main Card */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-6 sm:p-8 space-y-6">
            {/* Ticket Header & Status */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-5">
              <div className="space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono text-xs font-bold text-blue-800 bg-blue-50 px-2.5 py-1 rounded border border-blue-200">
                    {trackingData.ticket_number}
                  </span>
                  <button
                    onClick={() => handleCopyTicket(trackingData.ticket_number)}
                    className="p-1 text-slate-400 hover:text-slate-600 rounded hover:bg-slate-100 transition-colors"
                    title="Copy Ticket ID"
                  >
                    {copied ? (
                      <Check className="w-3.5 h-3.5 text-emerald-600" />
                    ) : (
                      <Copy className="w-3.5 h-3.5" />
                    )}
                  </button>
                  <span className="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-600 font-medium">
                    {trackingData.category === "HOSTEL_WIFI" ? "Hostel Wi-Fi" : trackingData.category}
                  </span>
                </div>
                <h2 className="text-xl font-bold text-slate-900 pt-1">
                  {trackingData.title}
                </h2>
              </div>
              <div className="self-start sm:self-center shrink-0">
                <StatusBadge status={trackingData.status} size="lg" />
              </div>
            </div>

            {/* Vice-Chancellor Escalation Banner */}
            {(trackingData.is_escalated_to_vc || trackingData.latest_update?.toLowerCase().includes("vice-chancellor") || trackingData.status_explanation?.toLowerCase().includes("vice-chancellor")) && (
              <div className="bg-amber-50 border-2 border-amber-300 rounded-xl p-4 flex items-start gap-3.5 text-amber-950">
                <div className="w-8 h-8 rounded-lg bg-amber-200 text-amber-800 flex items-center justify-center shrink-0 mt-0.5">
                  <Landmark className="w-4 h-4" />
                </div>
                <div className="space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-[11px] font-extrabold uppercase tracking-wider bg-amber-200 text-amber-900 px-2 py-0.5 rounded">
                      Vice-Chancellor Review Queue Active
                    </span>
                    {trackingData.vc_escalation_status && (
                      <span className="text-xs font-semibold text-amber-800">
                        Status: {trackingData.vc_escalation_status}
                      </span>
                    )}
                    {trackingData.followup_count && trackingData.followup_count > 1 && (
                      <span className="text-[11px] font-mono text-amber-700">
                        (Report #{trackingData.followup_count} in thread)
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-amber-800 leading-relaxed">
                    This complaint thread has reached the 3-unresolved-complaints threshold and has been automatically escalated to senior university administration.
                  </p>
                </div>
              </div>
            )}

            {/* Status Timeline */}
            {timelineInfo && (
              <div className="space-y-3 pt-2">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                  Swarm Resolution Timeline
                </h3>

                <div className="grid grid-cols-1 md:grid-cols-4 gap-4 relative">
                  {timelineInfo.steps.map((step) => {
                    const isPassed = step.id < timelineInfo.currentStep;
                    const isCurrent = step.id === timelineInfo.currentStep;

                    return (
                      <div
                        key={step.id}
                        className={`rounded-xl p-4 border transition-colors ${
                          isCurrent
                            ? "bg-blue-50/70 border-blue-300 ring-1 ring-blue-300"
                            : isPassed
                            ? "bg-slate-50 border-slate-200"
                            : "bg-white border-slate-200 opacity-60"
                        }`}
                      >
                        <div className="flex items-center gap-2 mb-2">
                          <div
                            className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                              isPassed
                                ? "bg-emerald-600 text-white"
                                : isCurrent
                                ? "bg-blue-700 text-white"
                                : "bg-slate-200 text-slate-500"
                            }`}
                          >
                            {isPassed ? (
                              <Check className="w-3.5 h-3.5" />
                            ) : (
                              step.id
                            )}
                          </div>
                          <span
                            className={`text-xs font-bold truncate ${
                              isCurrent ? "text-blue-900" : "text-slate-800"
                            }`}
                          >
                            {step.title}
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-600 leading-snug">
                          {step.description}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Operational Update & Status Explanation */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
              {/* Latest Update */}
              <div className="bg-slate-50 rounded-xl p-4 border border-slate-200/80 space-y-1.5">
                <div className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-slate-600">
                  <Clock className="w-3.5 h-3.5 text-blue-600" />
                  <span>Latest Operational Update</span>
                </div>
                <p className="text-xs text-slate-800 font-medium leading-relaxed">
                  {trackingData.latest_update}
                </p>
              </div>

              {/* Status Explanation */}
              <div className="bg-slate-50 rounded-xl p-4 border border-slate-200/80 space-y-1.5">
                <div className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-slate-600">
                  <HelpCircle className="w-3.5 h-3.5 text-indigo-600" />
                  <span>Status Explanation</span>
                </div>
                <p className="text-xs text-slate-700 leading-relaxed">
                  {trackingData.status_explanation}
                </p>
              </div>
            </div>

            {/* Meta details footer */}
            <div className="pt-4 border-t border-slate-100 flex flex-wrap items-center justify-between text-xs text-slate-500 gap-4">
              <div className="flex items-center gap-2">
                <Building className="w-3.5 h-3.5 text-slate-400" />
                <span>
                  Assigned:{" "}
                  <strong className="text-slate-800">
                    {trackingData.assigned_department || "Pending Swarm Triage"}
                  </strong>
                </span>
              </div>
              <div className="flex items-center gap-2">
                <Calendar className="w-3.5 h-3.5 text-slate-400" />
                <span>
                  Logged:{" "}
                  <strong className="text-slate-800">
                    {new Date(trackingData.submitted_at).toLocaleDateString(undefined, {
                      year: "numeric",
                      month: "short",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </strong>
                </span>
              </div>
            </div>
          </div>

          {/* Privacy Note */}
          <div className="bg-white rounded-xl border border-slate-200 p-4 flex items-center justify-between text-xs text-slate-500">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-emerald-600" />
              <span>
                Zero-PII Student Portal: No student IDs, room numbers, or internal staff authorization secrets are exposed.
              </span>
            </div>
            <Link href="/submit" className="text-blue-700 hover:underline font-medium">
              Submit Another Report →
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}

export default function TrackComplaintPage() {
  return (
    <RouteGuard allowedPortals={["student"]}>
      <Suspense
        fallback={
          <div className="max-w-4xl mx-auto py-12 text-center text-slate-500 text-sm">
            <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2 text-blue-600" />
            <span>Loading grievance tracker...</span>
          </div>
        }
      >
        <TrackContent />
      </Suspense>
    </RouteGuard>
  );
}
