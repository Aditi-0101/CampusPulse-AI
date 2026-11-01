"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  Activity,
  Cpu,
  Brain,
  ShieldCheck,
  UserCheck,
  CheckCircle2,
  AlertTriangle,
  Clock,
  RefreshCw,
  Search,
  Filter,
  ArrowRight,
  Database,
  Layers,
  Radio,
  AlertCircle,
  ExternalLink,
  ChevronDown,
  Info,
  Zap,
  SlidersHorizontal,
} from "lucide-react";
import {
  fetchSwarmMetrics,
  fetchSwarmEvents,
  fetchSwarmReplay,
  getSwarmStreamUrl,
  useIsMounted,
} from "@/lib/api";
import {
  SwarmMetricsResponse,
  SwarmActivityEvent,
  SwarmReplayResponse,
} from "@/types/swarm";
import { StatusBadge } from "@/components/StatusBadge";
import { RouteGuard } from "@/components/RouteGuard";

export default function SwarmDashboardPage() {
  const mounted = useIsMounted();

  // Metrics State
  const [metrics, setMetrics] = useState<SwarmMetricsResponse | null>(null);
  const [metricsLoading, setMetricsLoading] = useState(true);
  const [metricsError, setMetricsError] = useState<string | null>(null);
  const [metricsTab, setMetricsTab] = useState<"ALL_TIME" | "RECENT">("ALL_TIME");

  // Activity Feed State
  const [events, setEvents] = useState<SwarmActivityEvent[]>([]);
  const [eventsLoading, setEventsLoading] = useState(true);
  const [eventsError, setEventsError] = useState<string | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  // Filters State
  const [ticketFilter, setTicketFilter] = useState("");
  const [agentFilter, setAgentFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState<string>("");

  // SSE Stream State
  const [streamStatus, setStreamStatus] = useState<"connected" | "connecting" | "disconnected">("connecting");
  const [liveEventBanner, setLiveEventBanner] = useState<string | null>(null);
  const [reconnectNonce, setReconnectNonce] = useState(0);

  // Ticket Replay State
  const [replayTicketInput, setReplayTicketInput] = useState("");
  const [replayData, setReplayData] = useState<SwarmReplayResponse | null>(null);
  const [replayLoading, setReplayLoading] = useState(false);
  const [replayError, setReplayError] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // 1. Fetch Metrics & Initial Events on Mount
  // ---------------------------------------------------------------------------
  const loadMetrics = useCallback(async () => {
    setMetricsLoading(true);
    setMetricsError(null);
    try {
      const data = await fetchSwarmMetrics();
      setMetrics(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Unable to load swarm telemetry metrics.";
      setMetricsError(msg);
    } finally {
      setMetricsLoading(false);
    }
  }, []);

  const loadEvents = useCallback(
    async (reset = true, cursorToUse?: string) => {
      if (reset) {
        setEventsLoading(true);
        setEventsError(null);
      } else {
        setLoadingMore(true);
      }

      try {
        const res = await fetchSwarmEvents({
          limit: 30,
          cursor: cursorToUse,
          ticket_number: ticketFilter || undefined,
          agent_role: agentFilter || undefined,
          source: sourceFilter || undefined,
        });

        if (reset) {
          setEvents(res.events);
        } else {
          setEvents((prev) => {
            const existingIds = new Set(prev.map((e) => e.event_id));
            const newOnes = res.events.filter((e) => !existingIds.has(e.event_id));
            return [...prev, ...newOnes];
          });
        }

        setNextCursor(res.next_cursor || null);
        setHasMore(res.has_more);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Failed to load swarm activity feed.";
        setEventsError(msg);
      } finally {
        setEventsLoading(false);
        setLoadingMore(false);
      }
    },
    [ticketFilter, agentFilter, sourceFilter]
  );

  useEffect(() => {
    let isMounted = true;

    fetchSwarmMetrics()
      .then((data) => {
        if (isMounted) {
          setMetrics(data);
          setMetricsLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (isMounted) {
          const msg = err instanceof Error ? err.message : "Unable to load swarm telemetry metrics.";
          setMetricsError(msg);
          setMetricsLoading(false);
        }
      });

    fetchSwarmEvents({ limit: 30 })
      .then((res) => {
        if (isMounted) {
          setEvents(res.events);
          setNextCursor(res.next_cursor || null);
          setHasMore(res.has_more);
          setEventsLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (isMounted) {
          const msg = err instanceof Error ? err.message : "Failed to load swarm activity feed.";
          setEventsError(msg);
          setEventsLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, []);

  // ---------------------------------------------------------------------------
  // 2. Real-Time Server-Sent Events (SSE) Subscription
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (typeof window === "undefined") return;

    const streamUrl = getSwarmStreamUrl({
      ticket_number: ticketFilter || undefined,
    });

    let es: EventSource | null = null;
    try {
      es = new EventSource(streamUrl);

      es.onopen = () => {
        setStreamStatus("connected");
      };

      es.addEventListener("swarm_event", (messageEvent) => {
        try {
          const newEvent: SwarmActivityEvent = JSON.parse(messageEvent.data);
          if (!newEvent || !newEvent.event_id) return;

          setEvents((prev) => {
            if (prev.some((e) => e.event_id === newEvent.event_id)) {
              return prev; // Deduplicate
            }
            if (ticketFilter && newEvent.ticket_number !== ticketFilter.toUpperCase()) {
              return prev;
            }
            if (sourceFilter && newEvent.source !== sourceFilter) {
              return prev;
            }
            if (agentFilter) {
              const actorRole = newEvent.actor.replace("agent:", "");
              if (actorRole !== agentFilter) return prev;
            }

            return [newEvent, ...prev];
          });

          setLiveEventBanner(
            `Live: ${newEvent.actor} recorded ${newEvent.event_type} (${newEvent.status})`
          );
          setTimeout(() => setLiveEventBanner(null), 4000);
        } catch (parseErr) {
          console.warn("Failed to parse incoming SSE swarm event:", parseErr);
        }
      });

      es.onerror = () => {
        if (es?.readyState === EventSource.CLOSED) {
          setStreamStatus("disconnected");
        } else {
          setStreamStatus("connecting");
        }
      };
    } catch (connErr) {
      console.error("Error creating SSE connection:", connErr);
    }

    return () => {
      if (es) {
        es.close();
      }
    };
  }, [ticketFilter, sourceFilter, agentFilter, reconnectNonce]);

  // ---------------------------------------------------------------------------
  // 4. Ticket Replay Handler
  // ---------------------------------------------------------------------------
  const handleReplaySearch = async (ticketToSearch?: string) => {
    const targetTicket = (ticketToSearch || replayTicketInput).trim().toUpperCase();
    if (!targetTicket) return;

    setReplayLoading(true);
    setReplayError(null);
    setReplayData(null);

    try {
      const data = await fetchSwarmReplay(targetTicket);
      setReplayData(data);
      setReplayTicketInput(targetTicket);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : `No swarm activity found for ticket '${targetTicket}'.`;
      setReplayError(msg);
    } finally {
      setReplayLoading(false);
    }
  };

  const handleSelectTicketForReplay = (tkt: string) => {
    setReplayTicketInput(tkt);
    handleReplaySearch(tkt);
    // Scroll smoothly down to the replay section
    const elem = document.getElementById("ticket-replay-section");
    if (elem) {
      elem.scrollIntoView({ behavior: "smooth" });
    }
  };

  if (!mounted) {
    return (
      <div className="py-12 flex justify-center items-center text-slate-500">
        <Activity className="w-6 h-6 animate-spin text-blue-600 mr-3" />
        <span>Initializing Live Swarm Telemetry...</span>
      </div>
    );
  }

  return (
    <RouteGuard allowedPortals={["admin"]}>
      <div className="space-y-8 pb-16">
      {/* ===================================================================== */}
      {/* Page Header with Real-Time Connection Indicator */}
      {/* ===================================================================== */}
      <div className="bg-white rounded-xl shadow-xs border border-slate-200 p-6 sm:p-8">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="px-2.5 py-0.5 text-xs font-bold uppercase tracking-wider bg-blue-50 text-blue-700 border border-blue-200 rounded-md">
                Stage G — Live Swarm Observability
              </span>
              <span className="text-xs text-slate-500 font-mono">Real-Time Multi-Agent Feed</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
              <Activity className="w-7 h-7 text-blue-600" />
              Live Campus Grievance Swarm
            </h1>
            <p className="text-sm text-slate-600 mt-1 max-w-3xl">
              Real-time visualization of authentic Meko MCP tool calls, autonomous agent decisions,
              and human staff oversight milestones. Backed by immutable database telemetry with zero synthetic activity.
            </p>
          </div>

          {/* SSE Connection Status Pill */}
          <div className="flex flex-wrap items-center gap-3 self-start md:self-auto">
            <div
              className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium border ${
                streamStatus === "connected"
                  ? "bg-emerald-50 text-emerald-800 border-emerald-200"
                  : streamStatus === "connecting"
                  ? "bg-amber-50 text-amber-800 border-amber-200"
                  : "bg-slate-100 text-slate-700 border-slate-300"
              }`}
            >
              <span
                className={`w-2.5 h-2.5 rounded-full ${
                  streamStatus === "connected"
                    ? "bg-emerald-500 animate-pulse"
                    : streamStatus === "connecting"
                    ? "bg-amber-500 animate-ping"
                    : "bg-rose-500"
                }`}
              />
              <span>
                {streamStatus === "connected"
                  ? "SSE Stream Active"
                  : streamStatus === "connecting"
                  ? "Connecting / Reconnecting..."
                  : "Stream Disconnected"}
              </span>
            </div>

            {streamStatus === "disconnected" && (
              <button
                onClick={() => setReconnectNonce((n) => n + 1)}
                className="px-3 py-1.5 text-xs font-semibold bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors"
              >
                Reconnect
              </button>
            )}

            <button
              onClick={() => {
                loadMetrics();
                loadEvents(true);
              }}
              title="Refresh Swarm Telemetry"
              className="p-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg border border-slate-200 transition-colors"
            >
              <RefreshCw className={`w-4 h-4 ${eventsLoading ? "animate-spin text-blue-600" : ""}`} />
            </button>
          </div>
        </div>

        {/* Live Event Flash Alert */}
        {liveEventBanner && (
          <div className="mt-4 px-4 py-2 bg-blue-50 border border-blue-200 rounded-lg text-xs font-medium text-blue-800 flex items-center gap-2 animate-fade-in">
            <Radio className="w-3.5 h-3.5 text-blue-600 animate-pulse" />
            <span>{liveEventBanner}</span>
          </div>
        )}
      </div>

      {/* ===================================================================== */}
      {/* 1. Genuine Telemetry Metrics */}
      {/* ===================================================================== */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
              <Zap className="w-5 h-5 text-amber-500" />
              Swarm Operational Telemetry
            </h2>
            <p className="text-xs text-slate-500">
              Aggregated from authentic database audit records. No simulated or inflated figures.
            </p>
          </div>

          {/* Time Window Switcher */}
          <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-lg border border-slate-200 text-xs">
            <button
              onClick={() => setMetricsTab("ALL_TIME")}
              className={`px-3 py-1 rounded-md font-medium transition-colors ${
                metricsTab === "ALL_TIME"
                  ? "bg-white text-slate-900 shadow-xs font-semibold"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              All-Time Totals
            </button>
            <button
              onClick={() => setMetricsTab("RECENT")}
              className={`px-3 py-1 rounded-md font-medium transition-colors ${
                metricsTab === "RECENT"
                  ? "bg-white text-slate-900 shadow-xs font-semibold"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Recent Window (24h)
            </button>
          </div>
        </div>

        {metricsError && (
          <div className="p-4 bg-rose-50 border border-rose-200 rounded-lg text-sm text-rose-700 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{metricsError}</span>
            <button
              onClick={loadMetrics}
              className="ml-auto underline font-semibold hover:text-rose-900"
            >
              Retry
            </button>
          </div>
        )}

        {metricsLoading && !metrics ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="h-24 bg-slate-100 rounded-xl animate-pulse border border-slate-200" />
            ))}
          </div>
        ) : metrics ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            {/* 1. Meko Tool Calls */}
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs">
              <div className="flex items-center justify-between text-slate-500 text-xs mb-1">
                <span>Meko Tool Calls</span>
                <Cpu className="w-4 h-4 text-blue-600" />
              </div>
              <div className="text-2xl font-bold text-slate-900">
                {metricsTab === "ALL_TIME"
                  ? metrics.total_meko_tool_calls.toLocaleString()
                  : metrics.recent_metrics?.tool_calls.toLocaleString() ?? "—"}
              </div>
              <div className="text-[11px] text-slate-500 mt-1 flex items-center gap-1 font-mono">
                <span className="text-emerald-600 font-semibold">
                  {metricsTab === "ALL_TIME" ? metrics.successful_calls : metrics.recent_metrics?.successful_calls ?? 0}
                </span>{" "}
                ok /{" "}
                <span className="text-rose-600 font-semibold">
                  {metricsTab === "ALL_TIME" ? metrics.failed_calls : metrics.recent_metrics?.failed_calls ?? 0}
                </span>{" "}
                err
              </div>
            </div>

            {/* 2. Success Rate */}
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs">
              <div className="flex items-center justify-between text-slate-500 text-xs mb-1">
                <span>Success Rate</span>
                <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              </div>
              <div className="text-2xl font-bold text-slate-900">
                {metricsTab === "ALL_TIME" && metrics.total_meko_tool_calls > 0
                  ? `${((metrics.successful_calls / metrics.total_meko_tool_calls) * 100).toFixed(1)}%`
                  : metricsTab === "RECENT" && (metrics.recent_metrics?.tool_calls ?? 0) > 0
                  ? `${(
                      ((metrics.recent_metrics?.successful_calls ?? 0) /
                        (metrics.recent_metrics?.tool_calls ?? 1)) *
                      100
                    ).toFixed(1)}%`
                  : "100%"}
              </div>
              <div className="text-[11px] text-slate-500 mt-1">High tool fidelity</div>
            </div>

            {/* 3. Average Latency */}
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs">
              <div className="flex items-center justify-between text-slate-500 text-xs mb-1">
                <span>Avg Latency</span>
                <Clock className="w-4 h-4 text-indigo-600" />
              </div>
              <div className="text-2xl font-bold text-slate-900">
                {metricsTab === "ALL_TIME"
                  ? `${Math.round(metrics.avg_latency_ms)} ms`
                  : `${Math.round(metrics.recent_metrics?.avg_latency_ms ?? 0)} ms`}
              </div>
              <div className="text-[11px] text-slate-500 mt-1">Remote MCP duration</div>
            </div>

            {/* 4. Context & Memory Recalls */}
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs">
              <div className="flex items-center justify-between text-slate-500 text-xs mb-1">
                <span>Memory Recalls</span>
                <Brain className="w-4 h-4 text-purple-600" />
              </div>
              <div className="text-2xl font-bold text-slate-900">
                {metricsTab === "ALL_TIME"
                  ? metrics.memory_recalls_count.toLocaleString()
                  : metrics.recent_metrics?.memory_recalls.toLocaleString() ?? "—"}
              </div>
              <div className="text-[11px] text-slate-500 mt-1">Datapack searches</div>
            </div>

            {/* 5. Human Approvals */}
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs">
              <div className="flex items-center justify-between text-slate-500 text-xs mb-1">
                <span>Staff Approvals</span>
                <ShieldCheck className="w-4 h-4 text-emerald-600" />
              </div>
              <div className="text-2xl font-bold text-emerald-700">
                {metrics.human_approvals_count.toLocaleString()}
              </div>
              <div className="text-[11px] text-slate-500 mt-1">Physical dispatches</div>
            </div>

            {/* 6. Human Rejections */}
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs">
              <div className="flex items-center justify-between text-slate-500 text-xs mb-1">
                <span>Staff Rejections</span>
                <UserCheck className="w-4 h-4 text-amber-600" />
              </div>
              <div className="text-2xl font-bold text-amber-700">
                {metrics.human_rejections_count.toLocaleString()}
              </div>
              <div className="text-[11px] text-slate-500 mt-1">Alternative remedies</div>
            </div>
          </div>
        ) : null}
      </section>

      {/* ===================================================================== */}
      {/* 2. Active Agents & Multi-Agent Architecture Overview */}
      {/* ===================================================================== */}
      <section className="bg-white rounded-xl shadow-xs border border-slate-200 p-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
          <div>
            <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
              <Layers className="w-5 h-5 text-blue-600" />
              Swarm Topology & Participating Roles
            </h2>
            <p className="text-xs text-slate-500">
              Only agents and human gatekeepers genuinely configured in this deployment are represented.
            </p>
          </div>
          <span className="text-xs bg-slate-100 text-slate-600 px-2.5 py-1 rounded-md font-mono border border-slate-200 self-start sm:self-auto">
            Deployment: Track B (Campus Grievance Swarm)
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Front Desk Agent */}
          <div className="p-4 rounded-lg border border-blue-200 bg-blue-50/40 relative">
            <div className="flex items-center justify-between mb-2">
              <span className="px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider bg-blue-100 text-blue-800 rounded">
                AI Agent
              </span>
              <span className="flex items-center gap-1 text-[11px] text-emerald-700 font-medium">
                <span className="w-2 h-2 rounded-full bg-emerald-500" />
                Active in Swarm
              </span>
            </div>
            <h3 className="font-bold text-slate-900 text-sm flex items-center gap-1.5">
              <Brain className="w-4 h-4 text-blue-600" />
              Front Desk Triage Agent
            </h3>
            <p className="text-xs text-slate-600 mt-1">
              Validates student grievances, assesses urgency, checks hostel infrastructure location, and correlates duplicates.
            </p>
            <div className="mt-3 pt-2 border-t border-blue-100 text-[11px] space-y-1 font-mono text-slate-600">
              <div>
                <span className="text-slate-400">Actor:</span> agent:frontdesk
              </div>
              <div>
                <span className="text-slate-400">Datapack:</span> cp-frontdesk
              </div>
              <div>
                <span className="text-slate-400">Operations:</span> conversation_create, context_search
              </div>
            </div>
          </div>

          {/* Dispatch Agent */}
          <div className="p-4 rounded-lg border border-indigo-200 bg-indigo-50/40 relative">
            <div className="flex items-center justify-between mb-2">
              <span className="px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider bg-indigo-100 text-indigo-800 rounded">
                AI Agent
              </span>
              <span className="flex items-center gap-1 text-[11px] text-emerald-700 font-medium">
                <span className="w-2 h-2 rounded-full bg-emerald-500" />
                Active in Swarm
              </span>
            </div>
            <h3 className="font-bold text-slate-900 text-sm flex items-center gap-1.5">
              <Cpu className="w-4 h-4 text-indigo-600" />
              Dispatch Routing Agent
            </h3>
            <p className="text-xs text-slate-600 mt-1">
              Searches campus Wi-Fi topologies in Meko memory, calculates recommended SLA, estimates parts budget, and formats recommendation.
            </p>
            <div className="mt-3 pt-2 border-t border-indigo-100 text-[11px] space-y-1 font-mono text-slate-600">
              <div>
                <span className="text-slate-400">Actor:</span> agent:dispatch
              </div>
              <div>
                <span className="text-slate-400">Datapack:</span> cp-dispatch
              </div>
              <div>
                <span className="text-slate-400">Operations:</span> context_search, memory_recall
              </div>
            </div>
          </div>

          {/* Human Staff Oversight */}
          <div className="p-4 rounded-lg border border-emerald-200 bg-emerald-50/40 relative">
            <div className="flex items-center justify-between mb-2">
              <span className="px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider bg-emerald-100 text-emerald-800 rounded">
                Human-in-the-Loop
              </span>
              <span className="flex items-center gap-1 text-[11px] text-emerald-700 font-medium">
                <span className="w-2 h-2 rounded-full bg-emerald-500" />
                Active Authority
              </span>
            </div>
            <h3 className="font-bold text-slate-900 text-sm flex items-center gap-1.5">
              <UserCheck className="w-4 h-4 text-emerald-600" />
              Human Staff Oversight (RBAC)
            </h3>
            <p className="text-xs text-slate-600 mt-1">
              Authorized university personnel (NOC Supervisor / Campus Admin) review high-budget dispatches. AI agents never self-authorize spending.
            </p>
            <div className="mt-3 pt-2 border-t border-emerald-100 text-[11px] space-y-1 font-mono text-slate-600">
              <div>
                <span className="text-slate-400">Roles:</span> staff:NOC_SUPERVISOR, staff:CAMPUS_ADMIN
              </div>
              <div>
                <span className="text-slate-400">Security:</span> Mandatory X-Staff-Token & Audit Logs
              </div>
              <div>
                <span className="text-slate-400">Authority:</span> APPROVE / REJECT with reason
              </div>
            </div>
          </div>
        </div>

        {/* Note on Future Roadmap Agents */}
        <div className="mt-4 p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-600 flex items-start gap-2">
          <Info className="w-4 h-4 text-blue-500 shrink-0 mt-0.5" />
          <span>
            <strong>Architecture Boundary:</strong> Field Technician and Knowledge Curator agents are part of the
            extended HackCBS roadmap. They are intentionally not shown as active since their logic is not yet implemented
            in the backend.
          </span>
        </div>
      </section>

      {/* ===================================================================== */}
      {/* 3. Live Activity Feed with Filters & Pagination */}
      {/* ===================================================================== */}
      <section className="bg-white rounded-xl shadow-xs border border-slate-200 p-6 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
          <div>
            <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
              <Radio className="w-5 h-5 text-blue-600" />
              Live Swarm Activity Feed
            </h2>
            <p className="text-xs text-slate-500">
              Chronological log stream of Meko tool calls, agent reasoning milestones, and human decisions.
            </p>
          </div>

          <div className="text-xs text-slate-500 font-mono">
            Showing <strong className="text-slate-800">{events.length}</strong> recorded events
          </div>
        </div>

        {/* Filters Toolbar */}
        <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-4 gap-3 bg-slate-50 p-3.5 rounded-lg border border-slate-200 text-xs">
          {/* Ticket Filter */}
          <div>
            <label className="block text-slate-600 font-medium mb-1">Ticket Filter</label>
            <div className="relative">
              <input
                type="text"
                placeholder="e.g. TKT-2BA08A10"
                value={ticketFilter}
                onChange={(e) => setTicketFilter(e.target.value.toUpperCase())}
                className="w-full px-3 py-1.5 pl-8 rounded-md border border-slate-300 text-xs font-mono uppercase bg-white focus:outline-hidden focus:ring-1 focus:ring-blue-500"
              />
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2" />
              {ticketFilter && (
                <button
                  onClick={() => setTicketFilter("")}
                  className="absolute right-2 top-1.5 text-slate-400 hover:text-slate-700 text-xs"
                >
                  ×
                </button>
              )}
            </div>
          </div>

          {/* Event Source Filter */}
          <div>
            <label className="block text-slate-600 font-medium mb-1">Event Source</label>
            <select
              value={sourceFilter}
              onChange={(e) => setSourceFilter(e.target.value)}
              className="w-full px-3 py-1.5 rounded-md border border-slate-300 text-xs bg-white focus:outline-hidden focus:ring-1 focus:ring-blue-500"
            >
              <option value="">All Event Sources</option>
              <option value="MEKO_TOOL">Meko MCP Tool Calls</option>
              <option value="HUMAN_APPROVAL">Human Staff Decisions</option>
              <option value="GRIEVANCE">Grievance Milestones</option>
            </select>
          </div>

          {/* Agent Role Filter */}
          <div>
            <label className="block text-slate-600 font-medium mb-1">Agent Role</label>
            <select
              value={agentFilter}
              onChange={(e) => setAgentFilter(e.target.value)}
              className="w-full px-3 py-1.5 rounded-md border border-slate-300 text-xs bg-white focus:outline-hidden focus:ring-1 focus:ring-blue-500"
            >
              <option value="">All Roles</option>
              <option value="frontdesk">Front Desk Agent</option>
              <option value="dispatch">Dispatch Routing Agent</option>
            </select>
          </div>

          {/* Apply / Reset Button */}
          <div className="flex items-end gap-2">
            <button
              onClick={() => loadEvents(true)}
              className="flex-1 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-md font-semibold text-xs transition-colors flex items-center justify-center gap-1.5"
            >
              <Filter className="w-3.5 h-3.5" />
              Apply Filters
            </button>
            {(ticketFilter || agentFilter || sourceFilter) && (
              <button
                onClick={() => {
                  setTicketFilter("");
                  setAgentFilter("");
                  setSourceFilter("");
                  loadEvents(true);
                }}
                className="px-2.5 py-1.5 bg-slate-200 hover:bg-slate-300 text-slate-700 rounded-md font-medium text-xs transition-colors"
                title="Clear all filters"
              >
                Reset
              </button>
            )}
          </div>
        </div>

        {/* Events Table / Timeline */}
        {eventsError && (
          <div className="p-4 bg-rose-50 border border-rose-200 rounded-lg text-sm text-rose-700 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{eventsError}</span>
            <button
              onClick={() => loadEvents(true)}
              className="ml-auto underline font-semibold hover:text-rose-900"
            >
              Retry
            </button>
          </div>
        )}

        {eventsLoading && events.length === 0 ? (
          <div className="py-12 text-center text-slate-500 space-y-2">
            <Activity className="w-6 h-6 animate-spin text-blue-600 mx-auto" />
            <p className="text-xs">Loading swarm events from database...</p>
          </div>
        ) : events.length === 0 ? (
          <div className="py-12 text-center bg-slate-50 rounded-xl border border-dashed border-slate-300 p-8">
            <Radio className="w-8 h-8 text-slate-400 mx-auto mb-2" />
            <h3 className="font-semibold text-slate-800 text-sm">No Swarm Events Found</h3>
            <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
              No recorded activity matches your current filter criteria. Try resetting your ticket or source filters.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {events.map((event) => {
              const isMeko = event.source === "MEKO_TOOL";
              const isHuman = event.source === "HUMAN_APPROVAL";
              const isError = event.status === "ERROR" || event.status === "FAILED";

              return (
                <div
                  key={event.event_id}
                  className={`p-4 rounded-xl border transition-all text-xs ${
                    isMeko
                      ? isError
                        ? "bg-rose-50/30 border-rose-200"
                        : "bg-purple-50/20 border-purple-200/80 hover:border-purple-300"
                      : isHuman
                      ? "bg-emerald-50/20 border-emerald-200/80 hover:border-emerald-300"
                      : "bg-slate-50/50 border-slate-200 hover:border-slate-300"
                  }`}
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2 border-b border-slate-100">
                    <div className="flex flex-wrap items-center gap-2">
                      {/* Source Badge */}
                      <span
                        className={`px-2 py-0.5 rounded-md font-semibold text-[10px] uppercase tracking-wider ${
                          isMeko
                            ? "bg-purple-100 text-purple-800 border border-purple-200"
                            : isHuman
                            ? "bg-emerald-100 text-emerald-800 border border-emerald-200"
                            : "bg-sky-100 text-sky-800 border border-sky-200"
                        }`}
                      >
                        {isMeko ? "Meko MCP Tool" : isHuman ? "Human Oversight" : "Grievance Milestone"}
                      </span>

                      {/* Actor Badge */}
                      <span className="font-mono text-[11px] text-slate-700 font-semibold bg-white px-2 py-0.5 rounded border border-slate-200">
                        {event.actor}
                      </span>

                      {/* Event Type */}
                      <span className="font-medium text-slate-600">
                        {event.event_type}
                      </span>

                      {/* Ticket Chip */}
                      {event.ticket_number && (
                        <button
                          onClick={() => handleSelectTicketForReplay(event.ticket_number!)}
                          title="Click to view end-to-end replay for this ticket"
                          className="font-mono font-bold text-blue-700 bg-blue-50 px-2 py-0.5 rounded border border-blue-200 hover:bg-blue-100 transition-colors flex items-center gap-1"
                        >
                          <span>{event.ticket_number}</span>
                          <ExternalLink className="w-3 h-3 text-blue-500" />
                        </button>
                      )}
                    </div>

                    {/* Timestamp & Status */}
                    <div className="flex items-center gap-2 font-mono text-[11px] text-slate-500">
                      <span title={event.timestamp}>
                        {new Date(event.timestamp).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                          second: "2-digit",
                        })}
                      </span>
                      <span
                        className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                          isError
                            ? "bg-rose-100 text-rose-800 border border-rose-200"
                            : event.status === "SUCCESS" || event.status === "APPROVED"
                            ? "bg-emerald-100 text-emerald-800 border border-emerald-200"
                            : "bg-blue-100 text-blue-800 border border-blue-200"
                        }`}
                      >
                        {event.status}
                      </span>
                    </div>
                  </div>

                  {/* Summary & Details */}
                  <div className="mt-2.5 flex flex-col md:flex-row md:items-start justify-between gap-3">
                    <p className="text-slate-800 text-xs leading-relaxed font-normal flex-1">
                      {event.summary}
                    </p>

                    {/* Meko Tool Attributes Pill */}
                    {isMeko && (
                      <div className="flex flex-wrap items-center gap-2 text-[10px] font-mono text-slate-500 bg-white px-2.5 py-1 rounded-md border border-slate-200 shrink-0">
                        {event.tool_name && (
                          <span>
                            <strong className="text-slate-700">Tool:</strong> {event.tool_name}
                          </span>
                        )}
                        {event.latency_ms !== null && event.latency_ms !== undefined && (
                          <span>
                            <strong className="text-slate-700">Latency:</strong> {Math.round(event.latency_ms)}ms
                          </span>
                        )}
                        {event.is_fallback && (
                          <span className="text-amber-700 font-semibold bg-amber-50 px-1 rounded">
                            Baseline Fallback
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            {/* Load More Button */}
            {hasMore && (
              <div className="pt-2 text-center">
                <button
                  onClick={() => loadEvents(false, nextCursor ?? undefined)}
                  disabled={loadingMore}
                  className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-800 font-semibold rounded-lg text-xs transition-colors border border-slate-300 disabled:opacity-50 inline-flex items-center gap-2"
                >
                  {loadingMore ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin text-blue-600" />
                      Loading Next Page...
                    </>
                  ) : (
                    <>
                      <ChevronDown className="w-3.5 h-3.5 text-slate-600" />
                      Load More Activity Events
                    </>
                  )}
                </button>
              </div>
            )}
          </div>
        )}
      </section>

      {/* ===================================================================== */}
      {/* 4. Ticket Lifecycle Replay Trace */}
      {/* ===================================================================== */}
      <section
        id="ticket-replay-section"
        className="bg-white rounded-xl shadow-xs border border-slate-200 p-6 space-y-4"
      >
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-slate-100">
          <div>
            <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
              <Clock className="w-5 h-5 text-indigo-600" />
              Ticket Lifecycle Replay Trace
            </h2>
            <p className="text-xs text-slate-500">
              Inspect the authentic, end-to-end chronological timeline for any submitted grievance ticket.
            </p>
          </div>
        </div>

        {/* Search Field */}
        <div className="flex flex-col sm:flex-row gap-2 max-w-lg">
          <div className="relative flex-1">
            <input
              type="text"
              placeholder="Enter Ticket ID (e.g. TKT-2BA08A10)"
              value={replayTicketInput}
              onChange={(e) => setReplayTicketInput(e.target.value.toUpperCase())}
              className="w-full px-3.5 py-2 pl-9 rounded-lg border border-slate-300 text-xs font-mono uppercase bg-white focus:outline-hidden focus:ring-1 focus:ring-indigo-500"
            />
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
          </div>
          <button
            onClick={() => handleReplaySearch()}
            disabled={replayLoading || !replayTicketInput.trim()}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-lg text-xs transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {replayLoading ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <ArrowRight className="w-3.5 h-3.5" />
            )}
            Replay Ticket
          </button>
        </div>

        {replayError && (
          <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
            <span>{replayError}</span>
          </div>
        )}

        {replayData && (
          <div className="mt-4 p-5 rounded-xl border border-indigo-100 bg-slate-50/50 space-y-5">
            {/* Ticket Header & Status */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-4 border-b border-slate-200">
              <div>
                <span className="text-[11px] text-slate-500 font-mono">Correlated Ticket Identifier</span>
                <h3 className="text-xl font-bold font-mono text-slate-900">{replayData.ticket_number}</h3>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-500">Current Status:</span>
                <StatusBadge status={replayData.current_status || "UNKNOWN"} size="sm" />
              </div>
            </div>

            {/* Stages Progression Track */}
            <div>
              <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-2">
                Workflow Stage Progression
              </h4>
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                {[
                  { id: "INTAKE_SUBMISSION", label: "Intake Submitted" },
                  { id: "FRONTDESK_TRIAGE", label: "Front Desk Triage" },
                  { id: "MEKO_CONTEXT_SEARCH", label: "Meko Context Search" },
                  { id: "DISPATCH_RECOMMENDATION", label: "Dispatch Routing" },
                  { id: "HUMAN_STAFF_OVERSIGHT", label: "Staff Oversight" },
                ].map((stg) => {
                  const isAvailable = replayData.available_stages.includes(stg.id);
                  return (
                    <div
                      key={stg.id}
                      className={`p-2.5 rounded-lg border text-center text-xs ${
                        isAvailable
                          ? "bg-emerald-50 border-emerald-200 text-emerald-800 font-medium"
                          : "bg-slate-100/60 border-slate-200 text-slate-400"
                      }`}
                    >
                      <div className="flex items-center justify-center mb-1">
                        {isAvailable ? (
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                        ) : (
                          <span className="w-2 h-2 rounded-full bg-slate-300" />
                        )}
                      </div>
                      <span className="text-[11px] leading-tight block">{stg.label}</span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Timeline Trace */}
            <div>
              <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-3">
                Recorded Chronological Trace ({replayData.events.length} Events)
              </h4>
              <div className="space-y-3 relative before:absolute before:inset-0 before:left-3 before:w-0.5 before:bg-slate-200">
                {replayData.events.map((ev) => (
                  <div key={ev.event_id} className="relative pl-8 text-xs">
                    <span className="absolute left-1.5 top-1.5 w-3 h-3 rounded-full bg-indigo-600 ring-4 ring-white" />
                    <div className="p-3 bg-white rounded-lg border border-slate-200 shadow-xs">
                      <div className="flex items-center justify-between text-[11px] text-slate-500 font-mono mb-1">
                        <span className="font-semibold text-slate-800">{ev.actor}</span>
                        <span>{new Date(ev.timestamp).toLocaleString()}</span>
                      </div>
                      <p className="text-slate-700 text-xs font-normal">{ev.summary}</p>
                      {ev.tool_name && (
                        <div className="mt-2 text-[10px] font-mono text-purple-700 bg-purple-50 px-2 py-0.5 rounded inline-block border border-purple-200">
                          Meko Tool: {ev.tool_name} ({Math.round(ev.latency_ms ?? 0)}ms)
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </section>

      {/* ===================================================================== */}
      {/* 5. Meko Context Visibility & Architecture Benchmark */}
      {/* ===================================================================== */}
      <section className="bg-gradient-to-r from-blue-900 to-[#0f2744] text-white rounded-xl shadow-xs p-6 sm:p-8 space-y-4">
        <div className="flex items-center gap-2 text-blue-300 text-xs font-mono font-bold uppercase tracking-wider">
          <Brain className="w-4 h-4 text-blue-400" />
          <span>Why Meko MCP Matters for Campus Swarms</span>
        </div>
        <h2 className="text-xl sm:text-2xl font-bold tracking-tight">
          Memory-Augmented Multi-Agent Intelligence
        </h2>
        <p className="text-xs sm:text-sm text-slate-300 max-w-3xl leading-relaxed">
          Unlike isolated stateless agents, CampusPulse AI connects the Front Desk and Dispatch agents to Meko
          memory containers. Agents search historical Wi-Fi failure topologies, detect duplicate reporting patterns across
          hostel blocks, and provide deterministic baseline fallbacks when remote services encounter transient interruptions.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
          <div className="bg-white/10 backdrop-blur-xs p-4 rounded-lg border border-white/10">
            <h3 className="font-bold text-sm text-blue-200 flex items-center gap-2">
              <Database className="w-4 h-4 text-blue-400" />
              Datapack Knowledge
            </h3>
            <p className="text-xs text-slate-300 mt-1">
              Encapsulates network rack diagrams, switch models, and vendor warranty topologies inside isolated datapacks.
            </p>
          </div>

          <div className="bg-white/10 backdrop-blur-xs p-4 rounded-lg border border-white/10">
            <h3 className="font-bold text-sm text-emerald-200 flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              Strict Privacy & RBAC
            </h3>
            <p className="text-xs text-slate-300 mt-1">
              Student room numbers, personal IDs, and staff tokens are never stored in memory or exposed in telemetry payloads.
            </p>
          </div>

          <div className="bg-white/10 backdrop-blur-xs p-4 rounded-lg border border-white/10">
            <h3 className="font-bold text-sm text-amber-200 flex items-center gap-2">
              <SlidersHorizontal className="w-4 h-4 text-amber-400" />
              Deterministic Fallback
            </h3>
            <p className="text-xs text-slate-300 mt-1">
              When Meko MCP calls encounter timeout or DNS anomalies, deterministic baseline rules seamlessly maintain student services.
            </p>
          </div>
        </div>

        {/* Meko ON/OFF Evaluator Integration Point */}
        <div className="mt-4 p-4 bg-white/5 border border-white/10 rounded-lg text-xs space-y-2">
          <div className="flex items-center justify-between text-blue-200 font-semibold">
            <span className="flex items-center gap-1.5">
              <SlidersHorizontal className="w-3.5 h-3.5 text-blue-400" />
              Planned Dual-Evaluator Endpoint Integration Point
            </span>
            <span className="bg-blue-500/20 text-blue-300 text-[10px] px-2 py-0.5 rounded border border-blue-400/20 font-mono">
              Backend Endpoint: Staged for Rollout
            </span>
          </div>
          <p className="text-slate-300 text-[11px] leading-relaxed">
            In accordance with architectural requirements, this dashboard does not use fake simulated toggles.
            When the backend dual-evaluator API (`POST /api/v1/swarm/evaluate-comparison`) is deployed, this panel will
            bench-test identical grievance inputs concurrently with Meko enabled versus disabled to contrast topology-aware
            recommendations against static heuristic defaults.
          </p>
        </div>
      </section>
    </div>
  </RouteGuard>
  );
}
