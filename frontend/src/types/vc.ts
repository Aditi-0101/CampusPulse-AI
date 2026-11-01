export interface LinkedGrievanceAudit {
  ticket_number: string;
  status: string;
  category: string;
  title: string;
  description: string;
  created_at: string | null;
  recommended_department?: string | null;
  followup_count: number;
  location_ref?: string | null;
}

export interface PreviousAuthorityDecision {
  ticket_number: string;
  decision: string;
  reason?: string | null;
  reviewer_role: string;
  decided_at?: string | null;
}

export interface VCEscalationSummary {
  escalation_id: string;
  thread_id: string;
  complaint_count: number;
  category: string;
  title: string;
  location_ref: string;
  responsible_department: string;
  status: string;
  trigger_ticket_number: string;
  related_tickets: string[];
  escalated_at: string;
  vc_decision?: string | null;
  decided_at?: string | null;
}

export interface VCEscalationDetail extends VCEscalationSummary {
  description: string;
  previous_authority_decisions: PreviousAuthorityDecision[];
  vc_reviewer_id?: string | null;
  vc_remarks?: string | null;
  linked_grievances: LinkedGrievanceAudit[];
}

export interface VCDecisionPayload {
  decision: 'ACKNOWLEDGED' | 'ACTION_REQUIRED' | 'FORWARDED_FOR_INVESTIGATION' | 'RESOLVED' | 'REJECTED_WITH_REASON';
  remarks?: string;
}

export interface VCDecisionResponse {
  escalation_id: string;
  status: string;
  vc_decision: string;
  vc_reviewer_id: string;
  vc_remarks?: string | null;
  decided_at: string;
  message: string;
}
