import React from "react";
import { Clock, CheckCircle2, XCircle, AlertCircle, FileText } from "lucide-react";

interface StatusBadgeProps {
  status: string;
  size?: "sm" | "md" | "lg";
}

export function StatusBadge({ status, size = "md" }: StatusBadgeProps) {
  const normStatus = (status || "").toUpperCase();

  let colorClasses = "bg-slate-100 text-slate-700 border-slate-200";
  let label = normStatus;
  let Icon = FileText;

  switch (normStatus) {
    case "PENDING_APPROVAL":
      colorClasses = "bg-amber-50 text-amber-800 border-amber-200";
      label = "Awaiting Staff Review";
      Icon = Clock;
      break;
    case "APPROVED":
      colorClasses = "bg-emerald-50 text-emerald-800 border-emerald-200";
      label = "Approved for Dispatch";
      Icon = CheckCircle2;
      break;
    case "REJECTED":
      colorClasses = "bg-rose-50 text-rose-800 border-rose-200";
      label = "Reviewed (Alternative Remediation)";
      Icon = XCircle;
      break;
    case "TRIAGED":
      colorClasses = "bg-sky-50 text-sky-800 border-sky-200";
      label = "Triage Complete";
      Icon = CheckCircle2;
      break;
    case "SUBMITTED":
      colorClasses = "bg-blue-50 text-blue-800 border-blue-200";
      label = "Submitted";
      Icon = FileText;
      break;
    case "ASSIGNED":
      colorClasses = "bg-indigo-50 text-indigo-800 border-indigo-200";
      label = "Technician Assigned";
      Icon = AlertCircle;
      break;
    case "RESOLVED":
    case "CLOSED":
      colorClasses = "bg-teal-50 text-teal-800 border-teal-200";
      label = normStatus === "RESOLVED" ? "Resolved" : "Closed";
      Icon = CheckCircle2;
      break;
    default:
      colorClasses = "bg-slate-100 text-slate-700 border-slate-200";
      label = normStatus || "Unknown";
      Icon = FileText;
  }

  const sizeClasses = {
    sm: "px-2 py-0.5 text-xs gap-1",
    md: "px-2.5 py-1 text-xs font-medium gap-1.5",
    lg: "px-3 py-1.5 text-sm font-medium gap-2",
  }[size];

  const iconSizes = {
    sm: "w-3 h-3",
    md: "w-3.5 h-3.5",
    lg: "w-4 h-4",
  }[size];

  return (
    <span
      className={`inline-flex items-center rounded-full border ${colorClasses} ${sizeClasses}`}
    >
      <Icon className={iconSizes} />
      <span>{label}</span>
    </span>
  );
}
