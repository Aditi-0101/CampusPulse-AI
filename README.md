# CampusPulse AI (HackCBS 9.0 - Track B: Campus Grievance Swarm)

A multi-agent campus grievance management swarm where students submit complaints, AI agents coordinate routing, triage, and follow-ups through shared memory, and human staff retain full authority over critical decisions.

---

## Phase 1 MVP Scope

- **Category**: Hostel Wi-Fi & Network Infrastructure (`HOSTEL_WIFI`).
- **Student Persona**: `student_anon_user` (Hostel 3, Floor 2 zone).
- **Staff Persona**: `staff_admin_sharma` (Campus Facilities Manager / NOC Supervisor).
- **Active Swarm Agents**:
  1. **Front Desk Agent**: Intake triage, keyword sentiment/urgency, zone normalization, and conversational traces in `cp-frontdesk`.
  2. **Dispatch Agent**: Routing assessment, heuristic SLA scoring, and human escalation gates in `cp-dispatch`.
- **Human-In-The-Loop (HITL) Gate**: Staff must explicitly approve or reject escalated dispatch recommendations before physical technician dispatch.
- **Meko MCP Integration**: Live memory recall and event capture (zero fake events).

---

## Meko Datapack Architecture & Isolation Boundary

```
[ Antigravity Coding Agent ]  <--->  [ campuspulse-build (Dev Memory) ]
           x (Strict No-Access)                    x (Strict No-Access)
[ Product Swarm Agents ]      <--->  [ cp-frontdesk & cp-dispatch (Runtime) ]
```

| Datapack Name | Datapack ID | Scope | Purpose |
| :--- | :--- | :--- | :--- |
| `campuspulse-build` | `8adfbdbc-8785-4bf0-b9dd-cd2adc8cd901` | **Coding Agent Only** | Stores codebase architecture decisions, task summaries, and dev context. |
| `cp-frontdesk` | `318fdc74-eb15-4cf4-9be5-57b5820b3264` | **Front Desk Agent** | Student intake conversations, sentiment tracking, and triage history. |
| `cp-dispatch` | `cdb3987f-b677-495f-8d87-01999c3f9b91` | **Dispatch Agent** | Staff infrastructure notes, equipment fault patterns, and escalation reasons. |

---

## Security, Privacy & Financial Safeguards

1. **Zero PII in Agent Memory**: All student records are pseudonymized (`student_anon_user`). Room-specific references are normalized to non-identifying infrastructure zones (`infra_zone_h3_fl2`).
2. **Server-Side Datapack Allowlists**: Enforced by `validate_agent_datapack` in `backend/app/core/config.py`. Product agents attempting to access `campuspulse-build` trigger an immediate `PermissionError`.
3. **No Autonomous AI Spending**: AI agents NEVER authorize spending or disburse funds (`is_spending_authorized: False`). Estimates are clearly marked as illustrative demo assumptions (`budget_currency: INR`, `budget_status: ILLUSTRATIVE_ESTIMATE`).
4. **AI Self-Approval Forbidden**: Reviewer validation rejects any AI agent identifier attempting to approve recommendations (HTTP 403 Forbidden).
5. **Conflict & Duplicate Prevention**: Once a ticket is approved or rejected, conflicting or duplicate decisions are blocked with HTTP 409 Conflict.
6. **Mandatory Rejection Justification**: Staff rejections require a non-empty explanation to maintain institutional transparency.
7. **Audit Trail**: Every genuine MCP tool call is logged to `meko_events`, and human decisions are permanently stored in `human_approvals` with recommendation snapshots.

---

## API Endpoints

### 1. Student Grievance Intake
```http
POST /api/v1/grievances
Content-Type: application/json

{
  "title": "Wi-Fi disconnecting intermittently",
  "description": "Wi-Fi signal drops every 15 minutes during evening study hours.",
  "student_anon_id": "student_anon_user",
  "location_ref": "infra_zone_h3_fl2",
  "category": "HOSTEL_WIFI"
}
```

### 2. Retrieve Pending Approvals (Staff Protected)
```http
GET /api/v1/approvals/pending
X-Staff-Token: <valid_staff_token>
```
Returns all grievances in `PENDING_APPROVAL` status with AI recommendations, heuristic SLAs, and illustrative budget estimates. Requires authenticated staff token (HTTP 401 if missing/invalid).

### 3. Human Staff Approval / Rejection Decision (Staff Protected)
```http
POST /api/v1/approvals/{ticket_number}/decision
X-Staff-Token: <valid_staff_token>
Content-Type: application/json

{
  "decision": "APPROVED",
  "reason": "Verified telemetry; authorized on-site physical technician check.",
  "assigned_technician": "tech_lead_verma"
}
```

**Rejection Example:**
```http
POST /api/v1/approvals/{ticket_number}/decision
X-Staff-Token: <valid_staff_token>
Content-Type: application/json

{
  "decision": "REJECTED",
  "reason": "Instructing remote port power cycle and switch firmware rollback first."
}
```

> **Security & Governance Invariants:**
> - **Server-Side Identity Resolution**: Reviewer identity (`reviewer_id`) and role (`reviewer_role`) are strictly resolved on the server from the authenticated `X-Staff-Token`. Request-body identity overrides are ignored to prevent impersonation.
> - **Constant-Time Verification**: Tokens are compared using constant-time digest comparison (`hmac.compare_digest`) to prevent timing side-channel attacks.
> - **Role-Based Access Control (RBAC)**: Operational decisions require authorized staff roles (`NOC_SUPERVISOR`, `CAMPUS_ADMIN`, `NETWORK_ENGINEER`, `FACILITIES_MANAGER`). Unauthorized roles (e.g. `READ_ONLY`) receive `HTTP 403 Forbidden`.
> - **AI Agent Exclusion**: Tokens or payloads representing AI agents (`dispatch`, `frontdesk`, `ai_agent`, `coding_agent`) receive `HTTP 403 Forbidden`. AI agents can NEVER self-approve recommendations.
> - **Financial Safety**: Human approval authorizes operational dispatch only. `budget_authorized` strictly remains `0.0`, and `is_spending_authorized` remains `False`.
> - **Demo Sandbox Disclaimer**: This token-based mechanism is a lightweight demo security layer for local hackathon evaluation. Production deployment requires institutional Single Sign-On (SAML/OIDC/Campus LDAP).

---

## Running Tests

Execute the complete 30-test regression suite covering Front Desk Agent, Dispatch Agent, Grievance Orchestrator, Human Approvals, and Staff Authentication:

```powershell
python -m pytest backend/tests/ -v
```

---

## Quickstart

### 1. Backend Setup
```powershell
cd backend
python -m pip install -r requirements.txt
python -m pip install greenlet
```

### 2. Launch FastAPI Server
```powershell
uvicorn backend.app.main:app --reload --port 8000
```
- Health check: `http://localhost:8000/api/v1/health`
- Live Meko audit history: `http://localhost:8000/api/v1/meko-events/history`
- Pending human approvals: `http://localhost:8000/api/v1/approvals/pending`
