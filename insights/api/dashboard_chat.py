# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Dashboard Chat API
API endpoints for AI-powered dashboard chat functionality
"""

import json
from typing import Any, Dict, List, Optional

import frappe
from frappe import _
from frappe.utils import now_datetime, get_datetime, time_diff_in_hours
# Note: using direct flat returns {"success": True/False, ...} instead of
# the success()/error() helpers which wrap data under {"status": ..., "data": ...}
# to match what the frontend DashboardChatButton.vue expects.

# Import agents — all agents now extend BaseIntelligenceAgent
from insights.agents import AgentRegistry
from insights.agents.query_router import route_query, get_query_router
from insights.agents.sales_agent import SalesIntelligenceAgent
from insights.agents.risk_agent import RiskIntelligenceAgent
from insights.agents.inventory_agent import InventoryIntelligenceAgent
from insights.agents.procurement_agent import ProcurementIntelligenceAgent
from insights.agents.financial_agent import FinancialIntelligenceAgent
from insights.agents.customer_agent import CustomerIntelligenceAgent
from insights.agents.general_agent import GeneralIntelligenceAgent
from insights.agents.tax_agent import TaxIntelligenceAgent
from insights.agents.hr_agent import HRIntelligenceAgent
from insights.agents.executive_agent import ExecutiveIntelligenceAgent
from insights.agents.marketing_agent import MarketingIntelligenceAgent
from insights.agents.esg_agent import ESGIntelligenceAgent


# Session timeout in hours (24 hours)
SESSION_TIMEOUT_HOURS = 24


def _safe_log_error(message: str, title: str = "Dashboard Chat"):
    """Safely log an error, truncating to avoid CharacterLengthExceededError"""
    try:
        safe_title = str(title)[:100] if title else "Dashboard Chat"
        safe_message = str(message)[:5000] if message else "No message"
        frappe.log_error(title=safe_title, message=safe_message)
    except Exception:
        print(f"[{title}] {message[:200]}..." if len(str(message)) > 200 else f"[{title}] {message}")

def _compress_context_minimal(context: Dict) -> Dict:
    """Aggressively compress context to minimal size"""
    if not context:
        return {}
    
    compressed = {}
    for key, value in context.items():
        if value is None:
            continue
        elif isinstance(value, (int, float, bool)):
            compressed[key] = value
        elif isinstance(value, str):
            compressed[key] = value[:200] if len(value) > 200 else value
        elif isinstance(value, list):
            # Only first 3 items, and simplify them
            compressed[key] = len(value)  # Just store count
        elif isinstance(value, dict):
            # Only numeric values from dict
            simple = {k: v for k, v in value.items() if isinstance(v, (int, float)) and len(str(k)) < 30}
            if simple:
                compressed[key] = dict(list(simple.items())[:5])
    
    return compressed


def get_agent_for_dashboard(dashboard_type: str):
    """Get the appropriate agent for a dashboard type.

    All agents now extend BaseIntelligenceAgent and are registered via
    @AgentRegistry.register(). The fallback dict is kept for safety in case
    the decorator hasn't run yet (e.g. module not imported).
    """
    agent = AgentRegistry.get_agent(dashboard_type)
    if agent:
        return agent

    # Fallback to direct instantiation
    agents = {
        "Sales": SalesIntelligenceAgent,
        "Risk": RiskIntelligenceAgent,
        "Inventory": InventoryIntelligenceAgent,
        "Procurement": ProcurementIntelligenceAgent,
        "Financial": FinancialIntelligenceAgent,
        "Customer": CustomerIntelligenceAgent,
        "General": GeneralIntelligenceAgent,
        "Tax": TaxIntelligenceAgent,
        "HR": HRIntelligenceAgent,
        "Executive": ExecutiveIntelligenceAgent,
        "Marketing": MarketingIntelligenceAgent,
        "ESG": ESGIntelligenceAgent,
    }

    agent_class = agents.get(dashboard_type)
    if agent_class:
        return agent_class()

    frappe.throw(_(f"No agent available for dashboard type: {dashboard_type}"))


@frappe.whitelist()
def get_recent_session(dashboard_type: str) -> Dict[str, Any]:
    """
    Get the user's most recent active session for a dashboard.
    Auto-loads the session if it's within the timeout period.
    
    Args:
        dashboard_type: Type of dashboard (Sales, Risk, etc.)
        
    Returns:
        Dict with session data or empty dict if no recent session
    """
    try:
        from insights.insights.doctype.dashboard_chat_session.dashboard_chat_session import DashboardChatSession
        
        session = DashboardChatSession.get_user_recent_session(dashboard_type)
        
        if not session:
            return {
                "has_session": False,
                "session_id": None,
                "messages": [],
                "dashboard_type": dashboard_type
            }

        # Check if session is still valid (within timeout)
        if session.last_activity:
            hours_since_activity = time_diff_in_hours(now_datetime(), session.last_activity)
            if hours_since_activity > SESSION_TIMEOUT_HOURS:
                # Session expired, mark as inactive
                session.is_active = 0
                session.save(ignore_permissions=True)
                return {
                    "has_session": False,
                    "session_id": None,
                    "messages": [],
                    "dashboard_type": dashboard_type,
                    "expired_session": session.name
                }

        return {
            "has_session": True,
            "session_id": session.name,
            "messages": session.get_messages(),
            "dashboard_type": dashboard_type,
            "last_activity": session.last_activity,
            "context": session.get_compressed_context()
        }
        
    except Exception as e:
        _safe_log_error(f"Get session: {str(e)[:200]}", "Chat API")
        return {
            "has_session": False,
            "session_id": None,
            "messages": [],
            "dashboard_type": dashboard_type,
            "error": str(e)
        }


@frappe.whitelist(allow_guest=False)
def start_new_session(dashboard_type=None):
    """Create a new chat session for a dashboard."""
    try:
        # Mark any existing sessions as inactive
        existing_sessions = frappe.get_all(
            "Dashboard Chat Session",
            filters={
                "user": frappe.session.user,
                "dashboard_type": dashboard_type,
                "is_active": 1
            },
            pluck="name"
        )
        
        for session_name in existing_sessions:
            frappe.db.set_value("Dashboard Chat Session", session_name, "is_active", 0)
        
        # Create new session - no context needed
        session = frappe.get_doc({
            "doctype": "Dashboard Chat Session",
            "dashboard_type": dashboard_type,
            "user": frappe.session.user,
            "context_snapshot": "{}",
            "compressed_context": "{}",
            "messages": "[]",
            "last_activity": now_datetime(),
            "is_active": 1
        })
        session.insert(ignore_permissions=True)
        frappe.db.commit()
        
        # Get quick actions for this dashboard
        agent = get_agent_for_dashboard(dashboard_type)
        quick_actions = agent.get_quick_actions()
        
        return {
            "success": True,
            "session_id": session.name,
            "dashboard_type": dashboard_type,
            "quick_actions": quick_actions,
            "message": f"New {dashboard_type} Intelligence chat session started"
        }
        
    except Exception as e:
        _safe_log_error(f"Start session: {str(e)[:200]}", "Chat API")
        return {
            "success": False,
            "error": str(e)
        }


@frappe.whitelist(allow_guest=False)
def send_message(session_id=None, query=None, context=None):
    """Send a message to the dashboard AI agent with dashboard context."""
    try:
        # Validate inputs
        if not session_id or not query:
            return {"success": False, "error": "Missing session_id or query"}

        # Truncate query if too long
        query = str(query)[:2000]

        # Parse context if provided (comes as JSON string from frontend)
        ctx = {}
        if context:
            try:
                if isinstance(context, str):
                    ctx = json.loads(context)
                elif isinstance(context, dict):
                    ctx = context
            except json.JSONDecodeError:
                ctx = {}

        # Get session
        if not frappe.db.exists("Dashboard Chat Session", session_id):
            return {"success": False, "error": "Session not found"}

        session = frappe.get_doc("Dashboard Chat Session", session_id)
        dashboard_type = session.dashboard_type

        # Get agent
        agent = get_agent_for_dashboard(dashboard_type)

        # Add user message
        session.add_message("user", query)

        # Get conversation history
        history = session.build_conversation_history(max_tokens=1000)

        # Execute query with context
        result = agent.execute(
            query=query,
            session_id=session_id,
            context=ctx,
            conversation_history=history
        )

        # Add AI response
        if result.get("success"):
            session.add_message("assistant", result.get("response", ""))

        # Log query for audit trail / recent-queries sidebar
        try:
            from insights.insights.doctype.insights_ai_query.insights_ai_query import InsightsAIQuery
            InsightsAIQuery.log_query(
                query=query,
                response=(result.get("response") or "")[:10000],
                model_used=result.get("model_used"),
                complexity=ctx.get("complexity"),
                processing_time=result.get("processing_time"),
                cached=result.get("cached", False),
                conversation=session_id,
                tokens_used=result.get("tokens_used"),
                source_module=dashboard_type,
            )
        except Exception:
            pass  # Non-critical — don't break the response

        return {
            "success": result.get("success", False),
            "response": result.get("response"),
            "error": result.get("error"),
            "model_used": result.get("model_used"),
            "processing_time": result.get("processing_time"),
            "cached": result.get("cached", False),
            "timestamp": result.get("timestamp"),
            "session_id": session_id,
            "dashboard_type": dashboard_type,
            "should_redirect": result.get("should_redirect"),
            "redirect_to": result.get("redirect_to"),
            "redirect_reason": result.get("redirect_reason"),
        }

    except Exception as e:
        _safe_log_error(f"Send error: {str(e)[:200]}", "Chat API")
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def get_session(session_id: str) -> Dict[str, Any]:
    """
    Get full session data including messages.
    
    Args:
        session_id: Chat session ID
        
    Returns:
        Dict with session data
    """
    try:
        if not frappe.db.exists("Dashboard Chat Session", session_id):
            return {
                "success": False,
                "error": "Session not found"
            }
        
        session = frappe.get_doc("Dashboard Chat Session", session_id)
        
        # Check ownership
        if session.user != frappe.session.user and frappe.session.user != "Administrator":
            return {
                "success": False,
                "error": "Access denied"
            }
        
        return {
            "success": True,
            "session_id": session.name,
            "dashboard_type": session.dashboard_type,
            "messages": session.get_messages(),
            "last_activity": session.last_activity,
            "is_active": session.is_active,
            "context": session.get_compressed_context()
        }
        
    except Exception as e:
        _safe_log_error(f"Get session: {str(e)[:200]}", "Chat API")
        return {
            "success": False,
            "error": str(e)
        }


@frappe.whitelist()
def list_sessions(dashboard_type: str, limit: int = 10) -> Dict[str, Any]:
    """
    List user's recent sessions for a dashboard.
    
    Args:
        dashboard_type: Type of dashboard
        limit: Maximum number of sessions to return
        
    Returns:
        Dict with list of sessions
    """
    try:
        from insights.insights.doctype.dashboard_chat_session.dashboard_chat_session import DashboardChatSession
        
        sessions = DashboardChatSession.get_user_sessions(
            dashboard_type=dashboard_type,
            user=frappe.session.user,
            limit=limit
        )
        
        # Enrich with message count
        for session in sessions:
            doc = frappe.get_doc("Dashboard Chat Session", session["name"])
            messages = doc.get_messages()
            session["message_count"] = len(messages)
            session["preview"] = messages[-1]["content"][:100] if messages else ""
            session["title"] = doc.get("session_title") or ""
        
        return {
            "success": True,
            "sessions": sessions,
            "dashboard_type": dashboard_type
        }
        
    except Exception as e:
        _safe_log_error(f"List error: {str(e)[:200]}", "Chat API")
        return {
            "success": False,
            "error": str(e),
            "sessions": []
        }


@frappe.whitelist()
def get_quick_actions(dashboard_type: str) -> Dict[str, Any]:
    """
    Get quick action buttons for a dashboard type.
    
    Args:
        dashboard_type: Type of dashboard
        
    Returns:
        Dict with quick actions list
    """
    try:
        agent = get_agent_for_dashboard(dashboard_type)
        actions = agent.get_quick_actions()
        
        return {
            "success": True,
            "quick_actions": actions,
            "dashboard_type": dashboard_type
        }
        
    except Exception as e:
        _safe_log_error(f"Actions error: {str(e)[:200]}", "Chat API")
        return {
            "success": False,
            "error": str(e),
            "quick_actions": []
        }


@frappe.whitelist()
def update_session_context(session_id: str, context: str) -> Dict[str, Any]:
    """
    Update the context for an existing session.
    Called when dashboard data changes.
    
    Args:
        session_id: Chat session ID
        context: JSON string of new dashboard context
        
    Returns:
        Dict with success status
    """
    try:
        if not frappe.db.exists("Dashboard Chat Session", session_id):
            return {
                "success": False,
                "error": "Session not found"
            }
        
        session = frappe.get_doc("Dashboard Chat Session", session_id)
        
        # Parse and compress context
        ctx = json.loads(context) if isinstance(context, str) else context
        agent = get_agent_for_dashboard(session.dashboard_type)
        compressed = agent.compress_context(ctx)
        
        session.set_context(ctx, compressed)
        
        return {
            "success": True,
            "session_id": session_id,
            "message": "Context updated"
        }
        
    except Exception as e:
        _safe_log_error(f"Context error: {str(e)[:200]}", "Chat API")
        return {
            "success": False,
            "error": str(e)
        }


@frappe.whitelist(allow_guest=False)
def delete_session(session_id: str) -> Dict[str, Any]:
    """Delete a chat session and all its data."""
    try:
        if not frappe.db.exists("Dashboard Chat Session", session_id):
            return {"success": False, "error": "Session not found"}

        session = frappe.get_doc("Dashboard Chat Session", session_id)
        if session.user != frappe.session.user and frappe.session.user != "Administrator":
            return {"success": False, "error": "Access denied"}

        frappe.delete_doc("Dashboard Chat Session", session_id, ignore_permissions=True)
        frappe.db.commit()
        return {"success": True}
    except Exception as e:
        _safe_log_error(f"Delete session: {str(e)[:200]}", "Chat API")
        return {"success": False, "error": str(e)}


@frappe.whitelist(allow_guest=False)
def rename_session(session_id: str, title: str) -> Dict[str, Any]:
    """Set a display title for a chat session."""
    try:
        if not frappe.db.exists("Dashboard Chat Session", session_id):
            return {"success": False, "error": "Session not found"}

        session = frappe.get_doc("Dashboard Chat Session", session_id)
        if session.user != frappe.session.user and frappe.session.user != "Administrator":
            return {"success": False, "error": "Access denied"}

        session.session_title = (title or "").strip()[:140]
        session.save(ignore_permissions=True)
        frappe.db.commit()
        return {"success": True, "title": session.session_title}
    except Exception as e:
        _safe_log_error(f"Rename session: {str(e)[:200]}", "Chat API")
        return {"success": False, "error": str(e)}


@frappe.whitelist(allow_guest=False)
def export_session(session_id: str, fmt: str = "markdown") -> Dict[str, Any]:
    """
    Export a chat session as markdown or plain text.

    Args:
        session_id: session to export
        fmt: 'markdown' (default) or 'text'

    Returns:
        Dict with exported content string
    """
    try:
        if not frappe.db.exists("Dashboard Chat Session", session_id):
            return {"success": False, "error": "Session not found"}

        session = frappe.get_doc("Dashboard Chat Session", session_id)
        if session.user != frappe.session.user and frappe.session.user != "Administrator":
            return {"success": False, "error": "Access denied"}

        messages = session.get_messages()
        lines = []

        if fmt == "markdown":
            lines.append("# AI Insights Conversation")
            lines.append(f"**Date:** {session.creation}")
            lines.append(f"**User:** {session.user}")
            lines.append("")
            lines.append("---")
            lines.append("")
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "user":
                    lines.append("### You")
                    lines.append(content)
                else:
                    lines.append("### AI Assistant")
                    lines.append(content)
                lines.append("")
        else:
            for msg in messages:
                role = "You" if msg.get("role") == "user" else "AI"
                lines.append(f"[{role}]: {msg.get('content', '')}")
                lines.append("")

        return {"success": True, "content": "\n".join(lines), "format": fmt}
    except Exception as e:
        _safe_log_error(f"Export session: {str(e)[:200]}", "Chat API")
        return {"success": False, "error": str(e)}


@frappe.whitelist(allow_guest=False)
def search_sessions(q: str, limit: int = 20) -> Dict[str, Any]:
    """
    Search across all of the user's chat sessions by message content.

    Args:
        q: search query string
        limit: max results

    Returns:
        Dict with matching sessions
    """
    try:
        q = (q or "").strip()
        if len(q) < 2:
            return {"success": True, "sessions": []}

        sessions = frappe.get_all(
            "Dashboard Chat Session",
            filters={"user": frappe.session.user},
            fields=["name", "dashboard_type", "messages", "last_activity", "session_title"],
            order_by="last_activity desc",
            limit=100,
        )

        results = []
        search_lower = q.lower()
        for s in sessions:
            try:
                msgs = json.loads(s.get("messages") or "[]")
            except (json.JSONDecodeError, TypeError):
                msgs = []

            for msg in msgs:
                content = (msg.get("content") or "").lower()
                if search_lower in content:
                    # Return context around match
                    idx = content.find(search_lower)
                    start = max(0, idx - 40)
                    end = min(len(content), idx + len(search_lower) + 60)
                    snippet = ("..." if start > 0 else "") + content[start:end] + ("..." if end < len(content) else "")
                    results.append({
                        "name": s.name,
                        "dashboard_type": s.dashboard_type,
                        "last_activity": s.last_activity,
                        "title": s.get("session_title") or "",
                        "snippet": snippet,
                        "message_count": len(msgs),
                    })
                    break  # one match per session
            if len(results) >= int(limit):
                break

        return {"success": True, "sessions": results}
    except Exception as e:
        _safe_log_error(f"Search sessions: {str(e)[:200]}", "Chat API")
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def get_ai_chat_status() -> Dict[str, Any]:
    """
    Get the status of AI chat functionality.
    
    Returns:
        Dict with AI status info
    """
    try:
        settings = frappe.get_single("Insights Settings")
        
        return {
            "success": True,
            "enabled": bool(settings.enable_ai_analytics),
            "configured": bool(settings.openrouter_api_key),
            "daily_quota": settings.daily_ai_quota or 100,
            "quota_used": settings.ai_quota_used or 0,
            "quota_remaining": max(0, (settings.daily_ai_quota or 100) - (settings.ai_quota_used or 0)),
            "available_dashboards": ["Sales", "Risk", "Inventory", "Procurement", "Financial", "Customer", "General",
                                     "HR", "Executive", "Marketing", "ESG"]
        }
        
    except Exception as e:
        _safe_log_error(f"Status error: {str(e)[:200]}", "Chat API")
        return {
            "enabled": False,
            "configured": False,
            "error": str(e)
        }


@frappe.whitelist(allow_guest=False)
def send_message_streaming(session_id=None, query=None, context=None):
    """
    Send a message and stream the response token-by-token via frappe.publish_realtime.
    The frontend listens on 'ai_response_token' events.
    Falls back to non-streaming send_message if streaming fails.
    """
    import time as _time

    if not session_id or not query:
        return {"success": False, "error": "Missing session_id or query"}

    query = str(query)[:2000]

    ctx = {}
    if context:
        try:
            ctx = json.loads(context) if isinstance(context, str) else (context if isinstance(context, dict) else {})
        except json.JSONDecodeError:
            ctx = {}

    if not frappe.db.exists("Dashboard Chat Session", session_id):
        return {"success": False, "error": "Session not found"}

    session = frappe.get_doc("Dashboard Chat Session", session_id)
    dashboard_type = session.dashboard_type
    agent = get_agent_for_dashboard(dashboard_type)

    session.add_message("user", query)
    history = session.build_conversation_history(max_tokens=1000)

    user = frappe.session.user
    event_channel = f"ai_stream:{session_id}"

    try:
        # Try streaming via OpenRouter directly
        from insights.ai.openrouter_client import OpenRouterClient
        client = OpenRouterClient()

        if not client.is_enabled() or not client.check_quota():
            # Fallback to non-streaming
            return send_message(session_id=session_id, query=query, context=json.dumps(ctx) if ctx else None)

        # Build messages for OpenRouter
        system_prompt = agent.build_system_prompt() if hasattr(agent, 'build_system_prompt') else (
            "You are an expert business intelligence analyst for ERPNext ERP system."
        )

        messages = [{"role": "system", "content": system_prompt}]
        if history:
            for h in history:
                messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
        messages.append({"role": "user", "content": query})

        import requests as req
        start_time = _time.time()
        response = req.post(
            f"{client.BASE_URL}/chat/completions",
            headers=client._get_headers(),
            json={
                "model": client.primary_model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 2000,
                "stream": True,
            },
            stream=True,
            timeout=90,
        )

        if response.status_code != 200:
            # Fallback
            return send_message(session_id=session_id, query=query, context=json.dumps(ctx) if ctx else None)

        full_response = []
        model_used = client.primary_model

        for line in response.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                token = delta.get("content")
                if chunk.get("model"):
                    model_used = chunk["model"]
                if token:
                    full_response.append(token)
                    frappe.publish_realtime(
                        event="ai_response_token",
                        message={"token": token, "session_id": session_id},
                        user=user,
                    )
            except json.JSONDecodeError:
                continue

        processing_time = round(_time.time() - start_time, 2)

        # Signal completion
        complete_text = "".join(full_response)
        frappe.publish_realtime(
            event="ai_response_done",
            message={
                "session_id": session_id,
                "model_used": model_used,
                "processing_time": processing_time,
            },
            user=user,
        )

        # Persist assistant message
        session.add_message("assistant", complete_text)
        client.increment_quota()

        # Log query
        try:
            from insights.insights.doctype.insights_ai_query.insights_ai_query import InsightsAIQuery
            InsightsAIQuery.log_query(
                query=query,
                response=complete_text[:10000],
                model_used=model_used,
                complexity=ctx.get("complexity"),
                processing_time=processing_time,
                cached=False,
                conversation=session_id,
                source_module=dashboard_type,
            )
        except Exception:
            pass

        return {
            "success": True,
            "streaming": True,
            "response": complete_text,
            "model_used": model_used,
            "processing_time": processing_time,
            "session_id": session_id,
        }

    except Exception as e:
        _safe_log_error(f"Streaming error: {str(e)[:200]}", "Chat API Streaming")
        # Fallback to non-streaming
        return send_message(session_id=session_id, query=query, context=json.dumps(ctx) if ctx else None)
