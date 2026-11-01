export type SwarmEventSource = "MEKO_TOOL" | "HUMAN_APPROVAL" | "GRIEVANCE";
export type SwarmActorType = "AGENT" | "HUMAN" | "SYSTEM";

export interface SwarmActivityEvent {
  event_id: string;
  source: SwarmEventSource;
  timestamp: string;
  actor_type: SwarmActorType;
  actor: string;
  event_type: string;
  tool_name?: string | null;
  datapack_id?: string | null;
  latency_ms?: number | null;
  ticket_number?: string | null;
  status: string;
  summary: string;
  is_fallback?: boolean | null;
  details?: Record<string, unknown>;
}

export interface SwarmActivityFeedResponse {
  events: SwarmActivityEvent[];
  next_cursor?: string | null;
  has_more: boolean;
  total_returned: number;
}

export interface SwarmRecentMetrics {
  window_description: string;
  tool_calls: number;
  successful_calls: number;
  failed_calls: number;
  avg_latency_ms: number;
  memory_recalls: number;
}

export interface SwarmMetricsResponse {
  total_meko_tool_calls: number;
  successful_calls: number;
  failed_calls: number;
  avg_latency_ms: number;
  context_searches_count: number;
  memory_recalls_count: number;
  human_approvals_count: number;
  human_rejections_count: number;
  active_agent_roles: string[];
  time_window: string;
  recent_metrics?: SwarmRecentMetrics | null;
}

export interface SwarmReplayResponse {
  ticket_number: string;
  current_status?: string | null;
  events: SwarmActivityEvent[];
  available_stages: string[];
  unavailable_stages: string[];
  summary: string;
}

export interface SwarmEventFilterParams {
  limit?: number;
  cursor?: string;
  ticket_number?: string;
  agent_role?: string;
  source?: string;
}
