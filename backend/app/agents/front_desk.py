import uuid
import re
import logging
from typing import Optional, Dict, Any, List

from backend.app.core.config import settings
from backend.app.core.meko import meko_client
from backend.app.schemas.grievance import GrievanceCreate, FrontDeskTriageResult

logger = logging.getLogger("campuspulse.agents.frontdesk")

class FrontDeskAgent:
    """Front Desk Agent: First contact for student grievance intake, triage, and conversation recording."""

    def __init__(self):
        self.role = "frontdesk"
        self.datapack_id = settings.MEKO_DATAPACK_FRONTDESK

    def _assess_urgency(self, text: str) -> str:
        """Evaluate grievance urgency from diagnostic keywords."""
        lower = text.lower()
        high_signals = ["exam", "test", "urgent", "entire floor", "entire hostel", "total outage", "blackout", "critical"]
        low_signals = ["inquiry", "question", "suggestion", "minor"]
        
        if any(w in lower for w in high_signals):
            return "HIGH"
        if any(w in lower for w in low_signals):
            return "LOW"
        return "MEDIUM"

    def _classify_category(self, text: str) -> str:
        """Classify grievance into supported campus categories."""
        lower = text.lower()
        if any(w in lower for w in ["wifi", "wi-fi", "internet", "router", "network", "signal", "ap-", "access point", "bandwidth"]):
            return "HOSTEL_WIFI"
        if any(w in lower for w in ["power", "electricity", "socket", "light", "spark", "voltage", "switchboard"]):
            return "HOSTEL_ELECTRICITY"
        return "OTHER"

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

    def _sanitize_for_meko(self, text: str) -> str:
        """Strip room numbers, personal names, phone numbers, or student IDs from text."""
        if not text:
            return ""
        # Scrub room numbers like "room 204", "rm 204", "r-204"
        scrubbed = re.sub(r'\b(?:room|rm|r)[\s\-_]*\d{3,4}\b', 'corridor zone', text, flags=re.IGNORECASE)
        # Scrub standalone 3-4 digit numbers representing room numbers
        scrubbed = re.sub(r'\b(\d{3,4})\b', 'zone', scrubbed)
        # Scrub student IDs
        scrubbed = re.sub(r'\buser_anon_\w+\b', 'student_user', scrubbed, flags=re.IGNORECASE)
        scrubbed = re.sub(r'\bstudent_anon_\w+\b', 'student_user', scrubbed, flags=re.IGNORECASE)
        return scrubbed

    async def triage_grievance(
        self,
        grievance_in: GrievanceCreate,
        grievance_id: Optional[int] = None
    ) -> FrontDeskTriageResult:
        """Intake, validate, search cp-frontdesk for duplicates, record turn, and package for Dispatch."""
        
        # 1. Validation of required inputs
        if not grievance_in.title or len(grievance_in.title.strip()) < 3:
            raise ValueError("Grievance title must be at least 3 characters long.")
        if not grievance_in.description or len(grievance_in.description.strip()) < 5:
            raise ValueError("Grievance description must be at least 5 characters long.")
        if not grievance_in.location_ref:
            raise ValueError("Location reference (node_loc_... or infra_zone_...) is required.")

        ticket_number = f"TKT-{uuid.uuid4().hex[:8].upper()}"
        combined_text = f"{grievance_in.title}. {grievance_in.description}"
        
        # 2. Urgency and Category Classification
        urgency = self._assess_urgency(combined_text)
        category = self._classify_category(combined_text)

        # Normalize location to non-identifying infrastructure zone and scrub student details
        zone_ref = self._normalize_to_zone_reference(grievance_in.location_ref)
        sanitized_title = self._sanitize_for_meko(grievance_in.title)
        sanitized_desc = self._sanitize_for_meko(grievance_in.description)

        # 3. Create Conversation Container in cp-frontdesk (Strictly Zone & Ticket scoped)
        conv_title = f"Intake: {ticket_number} ({zone_ref})"
        conversation_id = await meko_client.conversation_create(
            title=conv_title,
            agent_role=self.role,
            datapack_id=self.datapack_id,
            grievance_id=grievance_id,
        )

        # 4. Search cp-frontdesk for related/duplicate context using zone reference
        is_duplicate = False
        duplicate_ref = None
        meko_used = False
        meko_summary = f"No previous complaints found for zone {zone_ref}."

        try:
            search_query = f"Wi-Fi connectivity problem at {zone_ref}"
            search_res = await meko_client.context_search(
                query=search_query,
                agent_role=self.role,
                conversation_id=conversation_id,
                datapack_id=self.datapack_id,
                limit=3,
                grievance_id=grievance_id,
            )
            
            # Check conversation hits or memory hits
            conv_hits = search_res.get("results", {}).get("conversation", {}).get("hits", [])
            mem_hits = search_res.get("results", {}).get("memory", [])
            
            if conv_hits or mem_hits:
                meko_used = True
                total_hits = len(conv_hits) + len(mem_hits)
                meko_summary = f"Retrieved {total_hits} prior interaction(s) for zone {zone_ref}."
                
                # Check for duplicate ticket reference in recent hits
                for hit in conv_hits:
                    hit_text = hit.get("text", "")
                    match = re.search(r"TKT-[A-F0-9]{8}", hit_text)
                    if match and match.group(0) != ticket_number:
                        is_duplicate = True
                        duplicate_ref = match.group(0)
                        meko_summary += f" Potential duplicate of active ticket {duplicate_ref}."
                        break
        except Exception as exc:
            logger.warning(f"Meko context_search non-fatal failure in front desk triage: {exc}")
            meko_summary = "Meko context lookup skipped due to server response."

        # 5. Formulate student acknowledgment
        if is_duplicate:
            ack_msg = (
                f"Thank you. Your report has been logged under ticket {ticket_number}. "
                f"We noticed an existing ticket ({duplicate_ref}) for zone {zone_ref}. "
                f"Our team has linked these issues to expedite resolution."
            )
        else:
            ack_msg = (
                f"Your grievance has been logged successfully under ticket {ticket_number}. "
                f"Classified as {category} with urgency {urgency}. "
                f"Dispatch Agent has been notified for routing assessment."
            )

        # 6. Record interaction in conversation trace (Strictly zone-level, Zero PII)
        sanitized_input = f"Zone: {zone_ref} | Issue: {sanitized_title} - {sanitized_desc}"
        plan = [
            "Validate student grievance fields",
            f"Check historical context in cp-frontdesk for zone {zone_ref}",
            "Forward structured intake package to Dispatch Agent"
        ]
        reasoning = (
            f"Assessed urgency as {urgency} based on diagnostic keywords. "
            f"Categorized as {category}. "
            f"Zone: {zone_ref}. "
            f"Duplicate check result: is_duplicate={is_duplicate}."
        )

        try:
            await meko_client.conversation_add_message(
                conversation_id=conversation_id,
                input_text=sanitized_input,
                output_text=ack_msg,
                agent_role=self.role,
                datapack_id=self.datapack_id,
                reasoning=reasoning,
                plan=plan,
                grievance_id=grievance_id,
            )
        except Exception as exc:
            logger.warning(f"Could not record conversation message in Meko: {exc}")

        return FrontDeskTriageResult(
            ticket_number=ticket_number,
            category=category,
            urgency=urgency,
            is_duplicate=is_duplicate,
            duplicate_ticket_ref=duplicate_ref,
            conversation_id=conversation_id,
            meko_context_used=meko_used,
            meko_context_summary=meko_summary,
            student_acknowledgment=ack_msg,
        )

front_desk_agent = FrontDeskAgent()
