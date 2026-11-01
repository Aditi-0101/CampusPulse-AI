import re
import logging
from typing import Optional, List, Dict, Any

from backend.app.core.config import settings, validate_agent_datapack
from backend.app.core.meko import meko_client
from backend.app.schemas.grievance import FrontDeskTriageResult, GrievanceCreate, DispatchRecommendation

logger = logging.getLogger("campuspulse.agents.dispatch")

# ==============================================================================
# DEMO ILLUSTRATIVE REPAIR CATALOG & HEURISTIC SLA POLICY (INR)
# ==============================================================================
# IMPORTANT GOVERNANCE & INTEGRITY SAFEGUARD:
# The prices, technician labor rates, and SLA commitments below are
# ILLUSTRATIVE ASSUMPTIONS for demonstration and testing purposes.
# They are NOT verified institutional price contracts, approved procurement
# schedules, or legally binding SLAs.
#
# Rules:
# 1. Currency: INR (Indian Rupee) for Indian campus deployment.
# 2. AI agents NEVER authorize spending or place orders (is_spending_authorized = False).
# 3. Any physical replacement or estimated expenditure requires formal human staff approval.
# 4. If an infrastructure incident references components without a configured institutional
#    catalog, the system returns budget_status = "UNCONFIGURED" and suggested_budget = 0.0,
#    leaving quotes strictly to human procurement.
# ==============================================================================

DEMO_ILLUSTRATIVE_REPAIR_CATALOG: Dict[str, Dict[str, Any]] = {
    "poe_injector": {
        "keywords": ["poe injector", "under-voltage", "voltage drop", "power supply"],
        "component_name": "Industrial 802.3at Gigabit PoE+ Injector (30W)",
        "is_configured": True,
        "is_verified_institutional_quote": False,
        "illustrative_hardware_cost": 2500.00,  # ₹2,500.00 INR (illustrative assumption)
        "illustrative_labor_hours": 2.0,
        "illustrative_hourly_rate": 500.00,    # ₹500.00 INR/hr technician rate (illustrative assumption)
        # Total Illustrative Budget: ₹2,500 + (2.0 * ₹500 = ₹1,000) = ₹3,500.00 INR
        "total_illustrative_budget": 3500.00,
        "heuristic_sla_hours": {"HIGH": 2, "MEDIUM": 4, "LOW": 8},
        "requires_human_approval": True,
        "justification": (
            "Illustrative assumption: PoE injector under-voltage hardware replacement requires "
            "physical NOC deployment. Actual procurement quote and budget authorization must be approved by human staff."
        ),
    },
    "access_point": {
        "keywords": ["access point", "ap replacement", "burnt", "hardware defect", "hardware failure"],
        "component_name": "Enterprise Wi-Fi 6 Ceiling Access Point",
        "is_configured": True,
        "is_verified_institutional_quote": False,
        "illustrative_hardware_cost": 8500.00,  # ₹8,500.00 INR (illustrative assumption)
        "illustrative_labor_hours": 3.0,
        "illustrative_hourly_rate": 500.00,     # ₹500.00 INR/hr (illustrative assumption)
        # Total Illustrative Budget: ₹8,500 + (3.0 * ₹500 = ₹1,500) = ₹10,000.00 INR
        "total_illustrative_budget": 10000.00,
        "heuristic_sla_hours": {"HIGH": 2, "MEDIUM": 6, "LOW": 12},
        "requires_human_approval": True,
        "justification": (
            "Illustrative assumption: Enterprise AP replacement requires inventory disbursement and controller provisioning. "
            "Spending must be approved by human staff."
        ),
    },
    "cable_run": {
        "keywords": ["cable cut", "crimping", "rj45", "patch cord"],
        "component_name": "Cat6 Plenum UTP Cable Run & Termination",
        "is_configured": True,
        "is_verified_institutional_quote": False,
        "illustrative_hardware_cost": 400.00,   # ₹400.00 INR (illustrative assumption)
        "illustrative_labor_hours": 1.0,
        "illustrative_hourly_rate": 400.00,     # ₹400.00 INR/hr (illustrative assumption)
        # Total Illustrative Budget: ₹400 + ₹400 = ₹800.00 INR
        "total_illustrative_budget": 800.00,
        "heuristic_sla_hours": {"HIGH": 4, "MEDIUM": 8, "LOW": 16},
        "requires_human_approval": True,
        "justification": (
            "Illustrative assumption: Field cable termination estimate. "
            "Official technician assignment requires staff acknowledgment."
        ),
    },
}

ROUTINE_SLA_POLICY: Dict[str, Dict[str, int]] = {
    # Heuristic target SLAs for routine operational investigation
    "MEKO_ROUTINE": {
        "HIGH": 8,
        "MEDIUM": 12,
        "LOW": 24,
    },
    # Heuristic baseline target when no prior context exists
    "BASELINE": {
        "HIGH": 8,
        "MEDIUM": 24,
        "LOW": 48,
    },
}

class DispatchAgent:
    """Dispatch Agent: Evaluates routing, searches cp-dispatch for infrastructure history, and recommends human escalation."""

    def __init__(self):
        self.role = "dispatch"
        self.datapack_id = settings.MEKO_DATAPACK_DISPATCH

    def _normalize_to_zone_reference(self, loc: str) -> str:
        """
        Normalize room-specific or granular node references to non-identifying infrastructure zones.
        Ensures room numbers (e.g. 204) are stripped from institutional Meko memories and queries.
        """
        if not loc:
            return "infra_zone_general"
        lower = loc.lower().strip()
        if lower.startswith("infra_zone_") and not re.search(r'\d{3,4}$', lower):
            return lower
        # Pattern like node_loc_h3_204 or h3_204 or hostel3_room204
        match = re.search(r'(h\d+|hostel\d+)[^\d]*(\d)(\d{2})', lower)
        if match:
            hostel = match.group(1).replace("hostel", "h")
            floor = match.group(2)
            return f"infra_zone_{hostel}_fl{floor}"
        # Strip trailing 3 or 4 digit room number if present
        sanitized = re.sub(r'[_\-\s]*\b\d{3,4}\b', '', lower)
        if not sanitized.startswith("infra_zone_"):
            sanitized = f"infra_zone_{sanitized.lstrip('_')}"
        return sanitized

    def _extract_facts_from_context(self, search_res: Dict[str, Any]) -> List[str]:
        """Extract plain text statements from Meko context_search results."""
        facts: List[str] = []
        results = search_res.get("results", {})
        
        # 1. From memory collection
        for mem in results.get("memory", []):
            text = mem.get("memory") or mem.get("data")
            if text and text not in facts:
                facts.append(text)
                
        # 2. From knowledge base collection
        for kb in results.get("knowledge_base", []):
            text = kb.get("chunk") or kb.get("text")
            if text and text not in facts:
                facts.append(text)

        # 3. From conversation hits if any
        for conv in results.get("conversation", {}).get("hits", []):
            text = conv.get("text")
            if text and text not in facts:
                facts.append(text)

        return facts

    def _evaluate_budget_and_sla(
        self,
        triage_urgency: str,
        triage_category: str,
        supporting_facts: List[str]
    ) -> Dict[str, Any]:
        """
        Evaluate recommended department, SLA hours, suggested budget, and human approval requirement
        distinguishing illustrative assumptions, unconfigured policies, and routine baselines.
        """
        urgency = triage_urgency.upper() if triage_urgency in ["HIGH", "MEDIUM", "LOW"] else "MEDIUM"
        
        # 1. Check for hardware defect signals in supporting facts
        generic_hardware_defect_triggers = [
            "defect", "broken", "faulty", "failure", "replace", "burnt",
            "poe injector", "under-voltage", "voltage drop", "cable cut", "laser", "switch"
        ]
        has_hardware_defect_signal = any(
            any(trigger in fact.lower() for trigger in generic_hardware_defect_triggers)
            for fact in supporting_facts
        )

        # 2. Match against configured illustrative catalog entries
        for item_key, catalog_entry in DEMO_ILLUSTRATIVE_REPAIR_CATALOG.items():
            for kw in catalog_entry["keywords"]:
                for fact in supporting_facts:
                    if kw in fact.lower():
                        if not catalog_entry.get("is_configured", True):
                            # Unconfigured item in catalog
                            return {
                                "matched": True,
                                "catalog_item": item_key,
                                "recommended_department": "Network Infrastructure Engineering (Specialized NOC)",
                                "recommended_sla_hours": 4 if urgency == "HIGH" else 8,
                                "sla_status": "UNCONFIGURED",
                                "suggested_budget": 0.0,
                                "budget_currency": "INR",
                                "budget_status": "UNCONFIGURED",
                                "is_spending_authorized": False,
                                "requires_human_approval": True,
                                "escalation_reason": (
                                    f"Hardware defect detected for {catalog_entry['component_name']}. "
                                    f"Status: UNCONFIGURED (No approved institutional price list available). "
                                    f"Formal quotation and procurement authorization required from human staff."
                                ),
                                "pricing_disclaimer": "Institutional price list unconfigured. Formal vendor quote required.",
                                "trigger_fact": fact[:120],
                            }
                        
                        # Configured demo item: return clearly marked illustrative estimate
                        sla = catalog_entry["heuristic_sla_hours"].get(urgency, 4)
                        budget = catalog_entry["total_illustrative_budget"]
                        return {
                            "matched": True,
                            "catalog_item": item_key,
                            "component_name": catalog_entry["component_name"],
                            "recommended_department": "Network Infrastructure Engineering (Specialized NOC)",
                            "recommended_sla_hours": sla,
                            "sla_status": "RECOMMENDED_TARGET",
                            "suggested_budget": budget,
                            "budget_currency": "INR",
                            "budget_status": "ILLUSTRATIVE_ESTIMATE",
                            "is_spending_authorized": False,  # Agent NEVER authorizes spending
                            "requires_human_approval": True,
                            "escalation_reason": (
                                f"Illustrative Estimate: Hardware replacement for {catalog_entry['component_name']} "
                                f"(~₹{budget:,.2f} INR: ₹{catalog_entry['illustrative_hardware_cost']:,.2f} unit + "
                                f"₹{catalog_entry['illustrative_labor_hours'] * catalog_entry['illustrative_hourly_rate']:,.2f} labor assumption). "
                                f"Unverified demo estimate: spending authorization and procurement quote require human staff approval."
                            ),
                            "pricing_disclaimer": (
                                "Illustrative assumption for demo purposes. Not an official institutional quote. "
                                "Formal financial expenditure requires authorized human staff approval."
                            ),
                            "trigger_fact": fact[:120],
                        }
        
        # 3. Hardware defect detected in facts, but no catalog entry exists -> UNCONFIGURED
        if has_hardware_defect_signal and supporting_facts:
            matched_fact = next((f for f in supporting_facts if any(t in f.lower() for t in generic_hardware_defect_triggers)), supporting_facts[0])
            return {
                "matched": True,
                "catalog_item": "unconfigured_hardware",
                "component_name": "Unspecified Campus Hardware",
                "recommended_department": "Network Infrastructure Engineering (Specialized NOC)",
                "recommended_sla_hours": 4 if urgency == "HIGH" else 8,
                "sla_status": "UNCONFIGURED",
                "suggested_budget": 0.0,
                "budget_currency": "INR",
                "budget_status": "UNCONFIGURED",
                "is_spending_authorized": False,
                "requires_human_approval": True,
                "escalation_reason": (
                    "Unconfigured hardware defect detected in diagnostic context. "
                    "No approved institutional pricing catalog exists; human procurement and engineering inspection required before spending."
                ),
                "pricing_disclaimer": "Institutional price list unconfigured. Formal vendor quote required.",
                "trigger_fact": matched_fact[:120],
            }

        # 4. Historical context retrieved, but routine (no physical replacement)
        if supporting_facts:
            sla = ROUTINE_SLA_POLICY["MEKO_ROUTINE"].get(urgency, 12)
            needs_approval = (urgency == "HIGH")
            return {
                "matched": False,
                "catalog_item": "routine_historical",
                "component_name": None,
                "recommended_department": "Campus IT & Network Helpdesk",
                "recommended_sla_hours": sla,
                "sla_status": "RECOMMENDED_TARGET",
                "suggested_budget": 0.0,
                "budget_currency": "INR",
                "budget_status": "NOT_APPLICABLE",
                "is_spending_authorized": False,
                "requires_human_approval": needs_approval,
                "escalation_reason": "High urgency routine issue requiring human staff acknowledgment." if needs_approval else None,
                "pricing_disclaimer": "Routine operational issue; no hardware expenditure involved.",
                "trigger_fact": None,
            }

        # 5. Deterministic baseline fallback (no historical context found in cp-dispatch)
        default_dept = "Campus IT & Network Helpdesk"
        if triage_category == "HOSTEL_ELECTRICITY":
            default_dept = "Campus Electrical Maintenance"
        elif triage_category == "OTHER":
            default_dept = "Campus General Facilities Desk"

        sla = ROUTINE_SLA_POLICY["BASELINE"].get(urgency, 24)
        needs_approval = (urgency == "HIGH")
        return {
            "matched": False,
            "catalog_item": "baseline_default",
            "component_name": None,
            "recommended_department": default_dept,
            "recommended_sla_hours": sla,
            "sla_status": "RECOMMENDED_TARGET",
            "suggested_budget": 0.0,
            "budget_currency": "INR",
            "budget_status": "NOT_APPLICABLE",
            "is_spending_authorized": False,
            "requires_human_approval": needs_approval,
            "escalation_reason": "Elevated urgency detected without matching historical precedent. Human oversight recommended." if needs_approval else None,
            "pricing_disclaimer": "Routine baseline dispatch; zero financial commitment authorized.",
            "trigger_fact": None,
        }

    async def assess_dispatch(
        self,
        triage: FrontDeskTriageResult,
        grievance_input: GrievanceCreate,
        grievance_id: Optional[int] = None,
        force_datapack_id: Optional[str] = None,  # For security/allowlist testing
    ) -> DispatchRecommendation:
        """Evaluate department, SLA, and human escalation based on actual Meko cp-dispatch context."""
        
        target_datapack = force_datapack_id or self.datapack_id
        
        # Enforce server-side allowlist: Dispatch agent MUST use cp-dispatch
        validate_agent_datapack(self.role, target_datapack)

        ticket_number = triage.ticket_number
        zone_ref = self._normalize_to_zone_reference(grievance_input.location_ref)
        ap_kw = "AP-H3" if "h3" in zone_ref.lower() or "ap-h3" in grievance_input.title.lower() or "ap-h3" in grievance_input.description.lower() else ""
        query = f"Infrastructure hardware defect {zone_ref} {triage.category} {ap_kw}".strip()
        
        meko_retrieved = False
        supporting_facts: List[str] = []
        meko_error: Optional[str] = None

        # 1. Retrieve real context from cp-dispatch
        try:
            search_res = await meko_client.context_search(
                query=query,
                agent_role=self.role,
                conversation_id=triage.conversation_id,
                datapack_id=target_datapack,
                limit=5,
                grievance_id=grievance_id,
            )
            
            if search_res.get("is_error"):
                meko_error = search_res.get("error", "Meko tool error")
            else:
                extracted = self._extract_facts_from_context(search_res)
                if extracted:
                    meko_retrieved = True
                    supporting_facts = extracted
        except Exception as exc:
            logger.warning(f"Meko cp-dispatch retrieval failed safely: {exc}")
            meko_error = str(exc)

        # 2. Evaluate SLA, Department, and Budget via explicit rule policy
        decision = self._evaluate_budget_and_sla(
            triage_urgency=triage.urgency,
            triage_category=triage.category,
            supporting_facts=supporting_facts
        )

        # 3. Formulate Recommendation based strictly on actual facts vs. baseline fallback
        if meko_retrieved and supporting_facts and decision["matched"]:
            return DispatchRecommendation(
                ticket_number=ticket_number,
                recommended_department=decision["recommended_department"],
                recommended_sla_hours=decision["recommended_sla_hours"],
                recommendation_reason=(
                    f"Meko-Augmented Recommendation: Correlated with verified hardware diagnostic record in cp-dispatch: "
                    f"'{decision['trigger_fact']}...'. Elevated from routine ticket to hardware replacement dispatch."
                ),
                meko_context_retrieved=True,
                meko_supporting_facts=supporting_facts,
                requires_human_approval=decision["requires_human_approval"],
                escalation_reason=decision["escalation_reason"],
                suggested_budget=decision["suggested_budget"],
                budget_currency=decision["budget_currency"],
                budget_status=decision["budget_status"],
                is_spending_authorized=decision["is_spending_authorized"],
                sla_status=decision["sla_status"],
                pricing_disclaimer=decision["pricing_disclaimer"],
            )
        elif meko_retrieved and supporting_facts:
            return DispatchRecommendation(
                ticket_number=ticket_number,
                recommended_department=decision["recommended_department"],
                recommended_sla_hours=decision["recommended_sla_hours"],
                recommendation_reason="Meko-Augmented Recommendation: Context matched routine historical incident.",
                meko_context_retrieved=True,
                meko_supporting_facts=supporting_facts,
                requires_human_approval=decision["requires_human_approval"],
                escalation_reason=decision["escalation_reason"],
                suggested_budget=decision["suggested_budget"],
                budget_currency=decision["budget_currency"],
                budget_status=decision["budget_status"],
                is_spending_authorized=decision["is_spending_authorized"],
                sla_status=decision["sla_status"],
                pricing_disclaimer=decision["pricing_disclaimer"],
            )

        # 4. Deterministic Baseline Fallback (Zero Hallucination / No Fabricated Meko Results)
        fallback_reason = "Deterministic Baseline: No previous infrastructure incident found in cp-dispatch."
        if meko_error:
            fallback_reason += f" (Meko lookup unfulfilled: {meko_error})"

        return DispatchRecommendation(
            ticket_number=ticket_number,
            recommended_department=decision["recommended_department"],
            recommended_sla_hours=decision["recommended_sla_hours"],
            recommendation_reason=fallback_reason,
            meko_context_retrieved=False,
            meko_supporting_facts=[],
            requires_human_approval=decision["requires_human_approval"],
            escalation_reason=decision["escalation_reason"],
            suggested_budget=decision["suggested_budget"],
            budget_currency=decision["budget_currency"],
            budget_status=decision["budget_status"],
            is_spending_authorized=decision["is_spending_authorized"],
            sla_status=decision["sla_status"],
            pricing_disclaimer=decision["pricing_disclaimer"],
        )

dispatch_agent = DispatchAgent()
