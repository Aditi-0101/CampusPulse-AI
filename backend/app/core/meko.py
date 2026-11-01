import json
import time
from datetime import datetime
import logging
from typing import Dict, Any, Optional
import httpx

from backend.app.core.config import settings, validate_agent_datapack, redact_sensitive_data
from backend.app.core.database import AsyncSessionLocal
from backend.app.models.meko_event import MekoEvent

logger = logging.getLogger("campuspulse.meko")

class MekoMCPClient:
    """Independent async client for Meko MCP Server with server-side allowlists and audit logging."""

    def __init__(self, server_url: Optional[str] = None, api_key: Optional[str] = None):
        self.server_url = server_url or settings.MEKO_SERVER_URL
        self.api_key = api_key or settings.MEKO_API_KEY
        self._req_id = 0

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "campuspulse-backend/1.0",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        agent_role: str,
        grievance_id: Optional[int] = None,
        event_type: str = "TOOL_CALL",
    ) -> Dict[str, Any]:
        """Execute a genuine Meko MCP tool call over JSON-RPC 2.0 with audit logging."""
        
        # Enforce server-side datapack allowlist
        datapack_id = arguments.get("datapack_id")
        if datapack_id:
            validate_agent_datapack(agent_role, datapack_id)

        # Redact any secrets before storing event
        safe_args = redact_sensitive_data(arguments)
        
        # 1. Log start in DB
        event_id = None
        try:
            async with AsyncSessionLocal() as session:
                event = MekoEvent(
                    grievance_id=grievance_id,
                    agent_role=agent_role,
                    datapack_id=datapack_id or "system",
                    tool_name=tool_name,
                    event_type=event_type,
                    status="PENDING",
                    arguments_json=json.dumps(safe_args),
                    timestamp=datetime.utcnow()
                )
                session.add(event)
                await session.commit()
                await session.refresh(event)
                event_id = event.id
        except Exception as e:
            logger.warning(f"Could not write initial MekoEvent to DB: {e}")

        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }

        start_time = time.perf_counter()
        parsed_result = {}
        status = "SUCCESS"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.server_url,
                    headers=self._get_headers(),
                    json=payload,
                )
                response.raise_for_status()
                raw_text = response.text

                # Parse SSE or direct JSON response
                # Format: "event: message\ndata: {jsonrpc...}"
                data_line = None
                for line in raw_text.splitlines():
                    if line.startswith("data:"):
                        data_line = line[len("data:"):].strip()
                        break
                
                if data_line:
                    res_json = json.loads(data_line)
                else:
                    res_json = json.loads(raw_text)

                # Extract tool call response content
                if "result" in res_json:
                    result_obj = res_json["result"]
                    is_error = result_obj.get("isError", False)
                    content_list = result_obj.get("content", [])

                    if content_list and content_list[0].get("type") == "text":
                        text_content = content_list[0].get("text", "{}")
                        try:
                            parsed_result = json.loads(text_content)
                        except json.JSONDecodeError:
                            parsed_result = {"raw_output": text_content}
                    else:
                        parsed_result = result_obj

                    if is_error:
                        status = "ERROR"
                        parsed_result["is_error"] = True
                        if "error" not in parsed_result:
                            parsed_result["error"] = parsed_result.get("raw_output", "MCP tool reported an error")
                elif "error" in res_json:
                    status = "ERROR"
                    parsed_result = res_json["error"]
                    parsed_result["is_error"] = True
                else:
                    parsed_result = res_json

        except Exception as exc:
            status = "ERROR"
            parsed_result = {"error": str(exc)}
            logger.error(f"Meko MCP tool call failed: {exc}")

        latency_ms = (time.perf_counter() - start_time) * 1000

        # 2. Update DB event
        if event_id:
            try:
                async with AsyncSessionLocal() as session:
                    db_event = await session.get(MekoEvent, event_id)
                    if db_event:
                        db_event.status = status
                        db_event.response_json = json.dumps(parsed_result)
                        db_event.latency_ms = round(latency_ms, 2)
                        await session.commit()
                        await session.refresh(db_event)
                        try:
                            from backend.app.services.swarm_service import swarm_service
                            norm_event = swarm_service.normalize_meko_event(db_event)
                            swarm_service.broadcast_event(norm_event)
                        except Exception:
                            pass
            except Exception as e:
                logger.warning(f"Could not update MekoEvent in DB: {e}")

        return parsed_result

    async def context_search(
        self,
        query: str,
        agent_role: str,
        conversation_id: str,
        datapack_id: str,
        limit: int = 5,
        grievance_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Run context_search across memory and knowledgebase in the agent's datapack."""
        args = {
            "query": query,
            "conversation_id": conversation_id,
            "datapack_id": datapack_id,
            "limit": limit,
        }
        return await self.call_tool(
            tool_name="context_search",
            arguments=args,
            agent_role=agent_role,
            grievance_id=grievance_id,
            event_type="MEMORY_RECALLED",
        )

    async def memory_add(
        self,
        text: str,
        agent_role: str,
        conversation_id: str,
        datapack_id: str,
        grievance_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Store an episodic memory/fact into the agent's datapack."""
        args = {
            "text": text,
            "conversation_id": conversation_id,
            "datapack_id": datapack_id,
            "agent_id": f"product_agent:{agent_role}",
        }
        return await self.call_tool(
            tool_name="memory_add",
            arguments=args,
            agent_role=agent_role,
            grievance_id=grievance_id,
            event_type="MEMORY_WRITTEN",
        )

    async def conversation_create(
        self,
        title: str,
        agent_role: str,
        datapack_id: str,
        grievance_id: Optional[int] = None,
    ) -> str:
        """Create a new conversation trace container."""
        args = {
            "title": title,
            "agent_id": f"product_agent:{agent_role}",
            "datapack_id": datapack_id,
        }
        res = await self.call_tool(
            tool_name="conversation_create",
            arguments=args,
            agent_role=agent_role,
            grievance_id=grievance_id,
            event_type="CONVERSATION_INIT",
        )
        return res.get("id", "")

    async def conversation_add_message(
        self,
        conversation_id: str,
        input_text: str,
        output_text: str,
        agent_role: str,
        datapack_id: str,
        reasoning: Optional[str] = None,
        plan: Optional[list] = None,
        grievance_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Record an interaction turn (user input + agent response) in the conversation trace."""
        args = {
            "conversation_id": conversation_id,
            "input": input_text,
            "output": output_text,
            "agent_id": f"product_agent:{agent_role}",
            "datapack_id": datapack_id,
        }
        if reasoning:
            args["reasoning"] = reasoning
        if plan:
            args["plan"] = plan

        return await self.call_tool(
            tool_name="conversation_add_message",
            arguments=args,
            agent_role=agent_role,
            grievance_id=grievance_id,
            event_type="CONVERSATION_SAVED",
        )

# Global singleton client instance for backend use
meko_client = MekoMCPClient()
