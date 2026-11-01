export type GrievanceCategory = "HOSTEL_WIFI" | "HOSTEL_ELECTRICITY" | "OTHER";

export type GrievanceStatus = 
  | "SUBMITTED"
  | "TRIAGED"
  | "PENDING_APPROVAL"
  | "APPROVED"
  | "REJECTED"
  | "ASSIGNED"
  | "RESOLVED"
  | "CLOSED";

export interface GrievanceCreatePayload {
  title: string;
  description: string;
  student_anon_id?: string;
  location_ref: string;
  category?: GrievanceCategory | string;
  followup_ticket_number?: string;
}

export interface FrontDeskTriageResult {
  ticket_number: string;
  category: string;
  urgency: string;
  is_duplicate: boolean;
  duplicate_ticket_ref?: string | null;
  conversation_id: string;
  meko_context_used: boolean;
  meko_context_summary?: string | null;
  student_acknowledgment: string;
}

export interface DispatchRecommendation {
  ticket_number: string;
  recommended_department: string;
  recommended_sla_hours: number;
  recommendation_reason: string;
  meko_context_retrieved: boolean;
  meko_supporting_facts: string[];
  requires_human_approval: boolean;
  escalation_reason?: string | null;
  suggested_budget: number;
  budget_currency: string;
  budget_status: string;
  is_spending_authorized: boolean;
  sla_status: string;
  pricing_disclaimer: string;
}

export interface GrievanceWorkflowResponse {
  ticket_number: string;
  status: string;
  grievance_id: number;
  triage: FrontDeskTriageResult;
  dispatch?: DispatchRecommendation | null;
  meko_context_used: boolean;
  meko_context_summary?: string | null;
  requires_human_approval: boolean;
  escalation_reason?: string | null;
  created_at: string;
  thread_id?: string;
  followup_count?: number;
  is_escalated_to_vc?: boolean;
  escalation_id?: string | null;
}

export interface StudentGrievanceTrackResponse {
  ticket_number: string;
  category: string;
  title: string;
  status: string;
  submitted_at: string;
  assigned_department?: string | null;
  latest_update: string;
  is_awaiting_approval: boolean;
  status_explanation: string;
  thread_id?: string;
  followup_count?: number;
  is_escalated_to_vc?: boolean;
  vc_escalation_status?: string | null;
}


export interface RecentTicketRecord {
  ticketNumber: string;
  title: string;
  category: string;
  locationRef: string;
  status: string;
  submittedAt: string;
  lastCheckedAt?: string;
}

export interface PendingApprovalItem {
  grievance_id: number;
  ticket_number: string;
  category: string;
  urgency: string;
  location_ref: string;
  title: string;
  description: string;
  status: string;
  recommended_department?: string | null;
  recommended_sla_hours?: number | null;
  ai_recommendation?: string | null;
  escalation_reason?: string | null;
  suggested_budget: number;
  budget_currency: string;
  budget_status: string;
  is_spending_authorized: boolean;
  meko_context_summary?: string | null;
  created_at: string;
}

export interface ApprovalDecisionPayload {
  decision: "APPROVED" | "REJECTED";
  reason?: string | null;
  assigned_technician?: string | null;
  ticket_number?: string | null;
}

export interface ApprovalDecisionResponse {
  approval_id: number;
  grievance_id: number;
  ticket_number: string;
  reviewer_id: string;
  reviewer_role: string;
  decision: string;
  reason?: string | null;
  previous_status: string;
  new_status: string;
  assigned_technician?: string | null;
  is_spending_authorized: boolean;
  financial_disclaimer: string;
  recommendation_snapshot?: string | null;
  decided_at: string;
}

