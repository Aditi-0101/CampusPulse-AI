"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  Wifi,
  Send,
  AlertCircle,
  CheckCircle2,
  Copy,
  Check,
  ArrowRight,
  ShieldAlert,
  Info,
  Loader2,
  RefreshCw,
  UserCheck,
  Landmark,
  Layers,
  History,
} from "lucide-react";
import { submitGrievance, ApiError } from "@/lib/api";
import { GrievanceCategory, GrievanceWorkflowResponse } from "@/types/grievance";

const INFRA_ZONES = [
  { value: "infra_zone_h3_fl2", label: "Hostel 3 — Floor 2 (Corridor / Common Area)" },
  { value: "infra_zone_h3_fl1", label: "Hostel 3 — Floor 1 (West Wing)" },
  { value: "infra_zone_h3_fl3", label: "Hostel 3 — Floor 3 (East Wing)" },
  { value: "infra_zone_h2_fl1", label: "Hostel 2 — Floor 1 (General Wing)" },
  { value: "infra_zone_h1_fl2", label: "Hostel 1 — Floor 2 (North Wing)" },
  { value: "infra_zone_library_fl1", label: "Central Library — Floor 1 (Reading Hall)" },
  { value: "CUSTOM", label: "Enter Custom Infrastructure Zone Code..." },
];

import { useAuth } from "@/context/AuthContext";
import { RouteGuard } from "@/components/RouteGuard";

export default function SubmitComplaintPage() {
  const { user } = useAuth();
  const [submissionMode, setSubmissionMode] = useState<"NEW" | "FOLLOWUP">("NEW");
  const [followupTicket, setFollowupTicket] = useState("");

  const [category, setCategory] = useState<GrievanceCategory>("HOSTEL_WIFI");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [zoneSelect, setZoneSelect] = useState("infra_zone_h3_fl2");
  const [customZone, setCustomZone] = useState("");

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successResult, setSuccessResult] = useState<GrievanceWorkflowResponse | null>(null);
  const [copied, setCopied] = useState(false);

  // Derived effective values
  const effectiveZone = zoneSelect === "CUSTOM" ? customZone.trim() : zoneSelect;

  // Validation
  const isTitleValid = title.trim().length >= 3;
  const isDescValid = description.trim().length >= 5;
  const isZoneValid = effectiveZone.length >= 2;
  const isFollowupValid =
    submissionMode === "NEW" || (submissionMode === "FOLLOWUP" && followupTicket.trim().length >= 5);
  const isFormValid = isTitleValid && isDescValid && isZoneValid && isFollowupValid;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isFormValid || isSubmitting) return;

    // Check for room number red flags
    const roomPattern = /\b(room\s*no|room\s*\d+|rm\s*\d+)\b/i;
    if (roomPattern.test(effectiveZone)) {
      setErrorMessage(
        "Privacy policy violation: Please do not submit room numbers. Use general wing or floor zones (e.g. infra_zone_h3_fl2)."
      );
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      const studentAnonId = `student_anon_${Math.random().toString(36).substring(2, 9)}`;

      const response = await submitGrievance({
        title: title.trim(),
        description: description.trim(),
        location_ref: effectiveZone,
        category,
        student_anon_id: studentAnonId,
        followup_ticket_number:
          submissionMode === "FOLLOWUP" ? followupTicket.trim() : undefined,
      });

      setSuccessResult(response);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage(
          err instanceof Error ? err.message : "Failed to communicate with CampusPulse AI backend."
        );
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCopyTicket = () => {
    if (!successResult) return;
    navigator.clipboard.writeText(successResult.ticket_number);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleReset = () => {
    setTitle("");
    setDescription("");
    setZoneSelect("infra_zone_h3_fl2");
    setCustomZone("");
    setSubmissionMode("NEW");
    setFollowupTicket("");
    setErrorMessage(null);
    setSuccessResult(null);
  };

  return (
    <RouteGuard allowedPortals={["student"]}>
      <div className="max-w-3xl mx-auto space-y-6 pb-12">
      {/* Header */}
      <div className="space-y-1.5 border-b border-slate-200 pb-4">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-blue-700">
          <Wifi className="w-4 h-4" />
          <span>Hostel Infrastructure Grievance Intake</span>
        </div>
        <h1 className="text-2xl font-bold text-slate-900">
          Submit Campus Infrastructure Complaint
        </h1>
        <p className="text-sm text-slate-600">
          Lodge an issue for automated swarm triage. Repeated unresolved complaints by verified students
          automatically escalate to the Vice-Chancellor.
        </p>
      </div>

      {/* Success State View */}
      {successResult ? (
        <div className="bg-white rounded-2xl border border-emerald-200 shadow-sm p-6 sm:p-8 space-y-6">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-xl bg-emerald-100 text-emerald-700 flex items-center justify-center shrink-0">
              <CheckCircle2 className="w-6 h-6" />
            </div>
            <div className="space-y-1">
              <span className="text-xs font-semibold uppercase tracking-wider text-emerald-700">
                Grievance Successfully Lodged
              </span>
              <h2 className="text-xl font-bold text-slate-900">
                Ticket Created & Triaged
              </h2>
              <p className="text-sm text-slate-600">
                Your issue has been recorded in the campus swarm queue. Keep your ticket number
                to monitor live status updates.
              </p>
            </div>
          </div>

          {/* Automatic Vice-Chancellor Escalation Alert */}
          {successResult.is_escalated_to_vc && (
            <div className="bg-amber-50 border-2 border-amber-300 rounded-xl p-5 flex items-start gap-3.5 text-amber-950 shadow-xs">
              <div className="w-9 h-9 rounded-lg bg-amber-200 text-amber-800 flex items-center justify-center shrink-0 mt-0.5">
                <Landmark className="w-5 h-5" />
              </div>
              <div className="space-y-1 leading-relaxed">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-extrabold uppercase tracking-wider bg-amber-200 text-amber-900 px-2 py-0.5 rounded">
                    Stage H: Auto-Escalated to Vice-Chancellor
                  </span>
                  {successResult.escalation_id && (
                    <span className="font-mono text-xs font-bold text-amber-800">
                      ID: {successResult.escalation_id}
                    </span>
                  )}
                </div>
                <p className="text-sm font-semibold text-amber-900">
                  3rd Unresolved Complaint Threshold Reached
                </p>
                <p className="text-xs text-amber-800">
                  Because this is your 3rd report for this unresolved issue thread, the complaint has been
                  automatically placed in the dedicated Vice-Chancellor review queue for senior administrative oversight.
                </p>
              </div>
            </div>
          )}

          {/* Ticket Display Card */}
          <div className="bg-slate-50 border border-slate-200 rounded-xl p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-500 font-medium uppercase tracking-wider">
                  Official Ticket Identifier
                </span>
                {successResult.followup_count && successResult.followup_count > 1 && (
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-blue-100 text-blue-800">
                    Report #{successResult.followup_count} in Thread
                  </span>
                )}
              </div>
              <div className="font-mono text-xl sm:text-2xl font-bold text-blue-800 tracking-tight mt-0.5">
                {successResult.ticket_number}
              </div>
              {successResult.thread_id && (
                <div className="text-[11px] font-mono text-slate-500 mt-0.5">
                  Thread: {successResult.thread_id}
                </div>
              )}
            </div>
            <button
              onClick={handleCopyTicket}
              className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-white hover:bg-slate-100 text-slate-700 border border-slate-300 rounded-lg text-sm font-medium transition-colors shadow-2xs self-start sm:self-auto"
            >
              {copied ? (
                <>
                  <Check className="w-4 h-4 text-emerald-600" />
                  <span className="text-emerald-700">Copied!</span>
                </>
              ) : (
                <>
                  <Copy className="w-4 h-4 text-slate-500" />
                  <span>Copy Ticket</span>
                </>
              )}
            </button>
          </div>

          {/* Swarm Triage Summary */}
          {successResult.triage && (
            <div className="bg-blue-50/50 border border-blue-100 rounded-xl p-4 text-xs space-y-2">
              <div className="flex items-center gap-1.5 font-semibold text-blue-900">
                <Info className="w-4 h-4 text-blue-600" />
                <span>Automated Front Desk Agent Assessment</span>
              </div>
              <p className="text-slate-700 leading-relaxed">
                {successResult.triage.student_acknowledgment ||
                  "Your grievance has been acknowledged and routed to campus operations."}
              </p>
              <div className="flex flex-wrap gap-4 pt-1 text-slate-600">
                <span>
                  Initial Urgency:{" "}
                  <strong className="text-slate-900 uppercase">
                    {successResult.triage.urgency}
                  </strong>
                </span>
                <span>•</span>
                <span>
                  Status:{" "}
                  <strong className="text-slate-900">
                    {successResult.status}
                  </strong>
                </span>
              </div>
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex flex-wrap items-center gap-3 pt-2">
            <Link
              href={`/track?ticket=${encodeURIComponent(successResult.ticket_number)}`}
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-blue-700 hover:bg-blue-800 text-white rounded-lg text-sm font-semibold shadow-xs transition-colors"
            >
              <span>Track Live Status</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
            <button
              onClick={handleReset}
              className="inline-flex items-center gap-2 px-4 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-sm font-medium transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              <span>Submit Another Complaint</span>
            </button>
          </div>
        </div>
      ) : (
        /* Form View */
        <form
          onSubmit={handleSubmit}
          className="bg-white rounded-2xl border border-slate-200 shadow-xs p-6 sm:p-8 space-y-6"
        >
          {/* Privacy Reminder Card */}
          <div className="bg-sky-50/70 border border-sky-200 rounded-xl p-4 flex items-start gap-3 text-xs text-sky-900">
            <ShieldAlert className="w-5 h-5 text-sky-600 shrink-0 mt-0.5" />
            <div className="space-y-1 leading-relaxed">
              <span className="font-bold text-sky-950">Student Privacy Protected:</span>
              <p>
                Do not enter room numbers, student registration numbers, or personal phone numbers.
                Please refer exclusively to general campus zones (e.g. Floor 2 corridor, Hostel 3 wing).
              </p>
            </div>
          </div>

          {/* Error Message Alert */}
          {errorMessage && (
            <div className="bg-rose-50 border border-rose-200 rounded-xl p-4 flex items-start gap-3 text-xs text-rose-800">
              <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
              <div className="space-y-1">
                <span className="font-bold">Submission Error:</span>
                <p className="leading-relaxed">{errorMessage}</p>
              </div>
            </div>
          )}

          {/* Authenticated Student Identity Card */}
          <div className="p-4 bg-blue-50/60 border border-blue-200/80 rounded-xl flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-blue-600 text-white flex items-center justify-center">
                <UserCheck className="w-5 h-5" />
              </div>
              <div>
                <div className="text-xs text-blue-900 font-semibold uppercase tracking-wider">
                  Verified Student Identity
                </div>
                <div className="text-sm font-bold text-slate-900">
                  {user?.name || "Verified Student"}
                </div>
              </div>
            </div>
            <div className="text-right">
              <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
                Authenticated
              </span>
            </div>
          </div>

          {/* Submission Mode: New vs Follow-up */}
          <div className="space-y-2">
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700">
              Complaint Type
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setSubmissionMode("NEW")}
                className={`p-3.5 rounded-xl border text-left transition-all flex items-start gap-3 ${
                  submissionMode === "NEW"
                    ? "border-blue-600 bg-blue-50/60 ring-2 ring-blue-500/20"
                    : "border-slate-200 hover:border-slate-300 bg-white"
                }`}
              >
                <Layers className={`w-5 h-5 shrink-0 mt-0.5 ${submissionMode === "NEW" ? "text-blue-700" : "text-slate-400"}`} />
                <div>
                  <div className="font-semibold text-xs text-slate-900">Report a New Issue</div>
                  <div className="text-[11px] text-slate-500">First-time incident report for an infrastructure problem</div>
                </div>
              </button>

              <button
                type="button"
                onClick={() => setSubmissionMode("FOLLOWUP")}
                className={`p-3.5 rounded-xl border text-left transition-all flex items-start gap-3 ${
                  submissionMode === "FOLLOWUP"
                    ? "border-amber-600 bg-amber-50/60 ring-2 ring-amber-500/20"
                    : "border-slate-200 hover:border-slate-300 bg-white"
                }`}
              >
                <History className={`w-5 h-5 shrink-0 mt-0.5 ${submissionMode === "FOLLOWUP" ? "text-amber-700" : "text-slate-400"}`} />
                <div>
                  <div className="font-semibold text-xs text-slate-900">Follow Up on Unresolved Issue</div>
                  <div className="text-[11px] text-slate-500">Link into existing thread (Escalates to VC on 3rd report)</div>
                </div>
              </button>
            </div>
          </div>

          {/* Follow-up Ticket Input */}
          {submissionMode === "FOLLOWUP" && (
            <div className="p-4 bg-amber-50/70 border border-amber-200 rounded-xl space-y-2">
              <label htmlFor="followupTicket" className="block text-xs font-bold uppercase tracking-wider text-amber-900">
                Previous Ticket Identifier <span className="text-rose-500">*</span>
              </label>
              <input
                id="followupTicket"
                type="text"
                required
                placeholder="e.g. TKT-B1C2D3E4"
                value={followupTicket}
                onChange={(e) => setFollowupTicket(e.target.value.toUpperCase())}
                className="w-full px-3.5 py-2.5 bg-white border border-amber-300 rounded-lg text-sm font-mono font-semibold text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-amber-500"
              />
              <p className="text-[11px] text-amber-800 leading-relaxed">
                The backend verifies that this ticket belongs to your student identity and remains unresolved.
                When you submit the 3rd unresolved complaint in the thread, the Vice-Chancellor escalation triggers automatically.
              </p>
            </div>
          )}

          {/* 1. Category */}
          <div className="space-y-1.5">
            <label
              htmlFor="category"
              className="block text-xs font-bold uppercase tracking-wider text-slate-700"
            >
              Grievance Category <span className="text-rose-500">*</span>
            </label>
            <select
              id="category"
              value={category}
              onChange={(e) => setCategory(e.target.value as GrievanceCategory)}
              className="w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-lg text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-medium"
            >
              <option value="HOSTEL_WIFI">Hostel Wi-Fi</option>
              <option value="HOSTEL_ELECTRICITY">Hostel Electricity & Power</option>
              <option value="CAMPUS_SECURITY">Campus Security & Gate Access</option>
              <option value="ACADEMIC_FACILITIES">Academic Facilities & Labs</option>
              <option value="OTHER">Other Campus Infrastructure</option>
            </select>
            <p className="text-xs text-slate-500">
              Select the primary department category for immediate triage.
            </p>
          </div>

          {/* 2. Infrastructure Zone Reference */}
          <div className="space-y-1.5">
            <label
              htmlFor="zoneSelect"
              className="block text-xs font-bold uppercase tracking-wider text-slate-700"
            >
              Infrastructure Zone Reference <span className="text-rose-500">*</span>
            </label>
            <select
              id="zoneSelect"
              value={zoneSelect}
              onChange={(e) => setZoneSelect(e.target.value)}
              className="w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-lg text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-xs"
            >
              {INFRA_ZONES.map((zone) => (
                <option key={zone.value} value={zone.value}>
                  {zone.label}
                </option>
              ))}
            </select>

            {zoneSelect === "CUSTOM" && (
              <div className="pt-2">
                <input
                  type="text"
                  placeholder="e.g. infra_zone_h4_fl1_corridor"
                  value={customZone}
                  onChange={(e) => setCustomZone(e.target.value)}
                  className="w-full px-3.5 py-2 bg-white border border-slate-300 rounded-lg text-xs font-mono text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            )}
            <p className="text-xs text-slate-500">
              Campus hardware zones identify which network access points (e.g. AP-H3-F2) serve your area.
            </p>
          </div>

          {/* 3. Complaint Title */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label
                htmlFor="title"
                className="block text-xs font-bold uppercase tracking-wider text-slate-700"
              >
                Complaint Title <span className="text-rose-500">*</span>
              </label>
              <span className="text-xs text-slate-400">
                {title.length}/200
              </span>
            </div>
            <input
              id="title"
              type="text"
              required
              maxLength={200}
              placeholder="e.g. Hostel 3 2nd floor Wi-Fi unreachable after 8 PM"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-lg text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
            {title.length > 0 && title.trim().length < 3 && (
              <p className="text-xs text-amber-600">
                Title must be at least 3 characters.
              </p>
            )}
          </div>

          {/* 4. Description */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label
                htmlFor="description"
                className="block text-xs font-bold uppercase tracking-wider text-slate-700"
              >
                Detailed Symptoms <span className="text-rose-500">*</span>
              </label>
              <span className="text-xs text-slate-400">
                {description.length}/2000
              </span>
            </div>
            <textarea
              id="description"
              rows={4}
              required
              maxLength={2000}
              placeholder="Describe the failure symptoms (e.g., Campus_WiFi SSID drops every 5 minutes, 80% packet loss on gateway, AP LED blinking red). No room numbers."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-lg text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
            {description.length > 0 && description.trim().length < 5 && (
              <p className="text-xs text-amber-600">
                Description must be at least 5 characters.
              </p>
            )}
          </div>

          {/* Submit Button */}
          <div className="pt-2 flex items-center justify-end gap-3">
            <Link
              href="/"
              className="px-4 py-2.5 rounded-lg border border-slate-300 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors"
            >
              Cancel
            </Link>
            <button
              type="submit"
              disabled={!isFormValid || isSubmitting}
              className="inline-flex items-center gap-2 px-6 py-2.5 rounded-lg bg-blue-700 hover:bg-blue-800 disabled:bg-slate-300 disabled:cursor-not-allowed text-white font-semibold text-sm shadow-xs transition-colors"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Submitting to Swarm...</span>
                </>
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  <span>{submissionMode === "FOLLOWUP" ? "Submit Follow-Up" : "Submit Complaint"}</span>
                </>
              )}
            </button>
          </div>
        </form>
      )}
    </div>
  </RouteGuard>
  );
}
