# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import json
from datetime import datetime
from typing import Dict, List, Optional

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class DashboardChatSession(Document):
    # begin: auto-generated types
    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        dashboard_type: DF.Literal["", "Sales", "Risk", "Inventory", "Procurement", "Financial", "Customer", "General"]
        user: DF.Link
        last_activity: DF.Datetime | None
        is_active: DF.Check
        messages: DF.JSON | None
        context_snapshot: DF.JSON | None
        compressed_context: DF.JSON | None
    # end: auto-generated types

    def before_insert(self):
        """Set defaults before creating new session"""
        if not self.user:
            self.user = frappe.session.user
        if not self.last_activity:
            self.last_activity = now_datetime()
        if not self.messages:
            self.messages = json.dumps([])

    def validate(self):
        """Validate session data"""
        valid_types = [
            "Sales", "Risk", "Inventory", "Procurement", "Financial",
            "Customer", "General", "HR", "Executive", "Tax",
            "Marketing", "ESG", "Budget Variance"
        ]
        if self.dashboard_type not in valid_types:
            frappe.throw("Invalid dashboard type")

    def add_message(self, role: str, content: str, metadata: Optional[Dict] = None) -> Dict:
        """Add a message to the session"""
        messages = self.get_messages()
        
        # Truncate content if too long
        if content and len(content) > 5000:
            content = content[:5000] + "..."
        
        message = {
            "id": len(messages) + 1,
            "role": role,  # 'user' or 'assistant'
            "content": content,
            "timestamp": now_datetime().isoformat(),
            "metadata": {}  # Don't store metadata to save space
        }
        
        messages.append(message)
        
        # Keep only last 20 messages to prevent overflow
        if len(messages) > 20:
            messages = messages[-20:]
        
        self.messages = json.dumps(messages)
        self.last_activity = now_datetime()
        self.save(ignore_permissions=True)
        
        return message

    def get_messages(self) -> List[Dict]:
        """Get all messages in the session"""
        if not self.messages:
            return []
        if isinstance(self.messages, str):
            return json.loads(self.messages)
        return self.messages

    def get_recent_messages(self, limit: int = 10) -> List[Dict]:
        """Get recent messages for context window"""
        messages = self.get_messages()
        return messages[-limit:] if len(messages) > limit else messages

    def set_context(self, context: Dict, compressed: Optional[Dict] = None):
        """Set the dashboard context for this session"""
        # Truncate context to prevent database field overflow
        context_str = json.dumps(context)
        if len(context_str) > 60000:  # Limit to ~60KB
            # Only store compressed context if full context is too large
            self.context_snapshot = json.dumps({"truncated": True, "reason": "Context too large"})
        else:
            self.context_snapshot = context_str
        
        if compressed:
            compressed_str = json.dumps(compressed)
            if len(compressed_str) > 60000:
                # Further truncate compressed context if needed
                compressed = self._truncate_context(compressed)
            self.compressed_context = json.dumps(compressed)
        self.save(ignore_permissions=True)

    def _truncate_context(self, context: Dict) -> Dict:
        """Truncate context to fit within limits"""
        truncated = {}
        for key, value in context.items():
            if isinstance(value, list) and len(value) > 10:
                truncated[key] = value[:10]  # Limit lists to 10 items
            elif isinstance(value, str) and len(value) > 1000:
                truncated[key] = value[:1000] + "..."
            elif isinstance(value, dict):
                # Recursively truncate nested dicts
                truncated[key] = {k: v for k, v in list(value.items())[:20]}
            else:
                truncated[key] = value
        return truncated

    def get_context(self) -> Dict:
        """Get the stored context"""
        if not self.context_snapshot:
            return {}
        if isinstance(self.context_snapshot, str):
            return json.loads(self.context_snapshot)
        return self.context_snapshot

    def get_compressed_context(self) -> Dict:
        """Get the compressed context for AI prompts"""
        if not self.compressed_context:
            return self.get_context()
        if isinstance(self.compressed_context, str):
            return json.loads(self.compressed_context)
        return self.compressed_context

    def build_conversation_history(self, max_tokens: int = 2000) -> List[Dict]:
        """Build conversation history for AI context, respecting token limits"""
        messages = self.get_messages()
        history = []
        estimated_tokens = 0
        
        # Process messages in reverse order to get most recent first
        for msg in reversed(messages):
            # Rough token estimation: 1 token ≈ 4 characters
            msg_tokens = len(msg.get("content", "")) // 4
            
            if estimated_tokens + msg_tokens > max_tokens:
                break
            
            history.insert(0, {
                "role": msg["role"],
                "content": msg["content"]
            })
            estimated_tokens += msg_tokens
        
        return history

    @staticmethod
    def get_user_recent_session(dashboard_type: str, user: str = None) -> Optional["DashboardChatSession"]:
        """Get the most recent active session for a user on a dashboard"""
        if not user:
            user = frappe.session.user
        
        sessions = frappe.get_all(
            "Dashboard Chat Session",
            filters={
                "user": user,
                "dashboard_type": dashboard_type,
                "is_active": 1
            },
            fields=["name"],
            order_by="last_activity desc",
            limit=1
        )
        
        if sessions:
            return frappe.get_doc("Dashboard Chat Session", sessions[0].name)
        return None

    @staticmethod
    def get_user_sessions(dashboard_type: str, user: str = None, limit: int = 10) -> List[Dict]:
        """Get list of user's sessions for a dashboard"""
        if not user:
            user = frappe.session.user
        
        return frappe.get_all(
            "Dashboard Chat Session",
            filters={
                "user": user,
                "dashboard_type": dashboard_type
            },
            fields=["name", "last_activity", "is_active"],
            order_by="last_activity desc",
            limit=limit
        )
