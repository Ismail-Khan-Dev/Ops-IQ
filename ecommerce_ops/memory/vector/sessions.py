"""
Session Management
Manages conversation sessions and context.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from ecommerce_ops.memory.vector.models import SessionContext
from ecommerce_ops.utils import utc_now

logger = logging.getLogger("ecommerce_ops.memory.vector.sessions")


class SessionManager:
    """Manages conversation sessions."""

    def __init__(self, max_session_duration_hours: int = 24):
        self.max_session_duration_hours = max_session_duration_hours
        self._sessions: Dict[str, SessionContext] = {}
        self._user_sessions: Dict[str, List[str]] = {}  # user_id -> session_ids
        self._agent_sessions: Dict[str, List[str]] = {}  # agent_name -> session_ids

    def create_session(
        self,
        user_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SessionContext:
        """Create a new session."""
        session_id = str(uuid.uuid4())

        session = SessionContext(
            session_id=session_id,
            user_id=user_id,
            agent_name=agent_name,
            metadata=metadata or {},
        )

        self._sessions[session_id] = session

        # Index by user
        if user_id:
            if user_id not in self._user_sessions:
                self._user_sessions[user_id] = []
            self._user_sessions[user_id].append(session_id)

        # Index by agent
        if agent_name:
            if agent_name not in self._agent_sessions:
                self._agent_sessions[agent_name] = []
            self._agent_sessions[agent_name].append(session_id)

        logger.info(
            "Created session %s (user=%s, agent=%s)",
            session_id,
            user_id,
            agent_name,
        )

        return session

    def get_session(self, session_id: str) -> Optional[SessionContext]:
        """Get a session by ID."""
        session = self._sessions.get(session_id)
        if session and session.is_active:
            # Check if expired
            if self._is_expired(session):
                session.is_active = False
                logger.debug("Session %s expired", session_id)
            else:
                session.last_activity = utc_now()
        return session

    def end_session(self, session_id: str) -> bool:
        """End a session."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        session.is_active = False
        session.last_activity = utc_now()
        logger.info("Ended session %s", session_id)
        return True

    def get_user_sessions(
        self,
        user_id: str,
        active_only: bool = True,
    ) -> List[SessionContext]:
        """Get all sessions for a user."""
        session_ids = self._user_sessions.get(user_id, [])
        sessions = []

        for sid in session_ids:
            session = self._sessions.get(sid)
            if session:
                if active_only and not session.is_active:
                    continue
                if active_only and self._is_expired(session):
                    continue
                sessions.append(session)

        return sessions

    def get_agent_sessions(
        self,
        agent_name: str,
        active_only: bool = True,
    ) -> List[SessionContext]:
        """Get all sessions for an agent."""
        session_ids = self._agent_sessions.get(agent_name, [])
        sessions = []

        for sid in session_ids:
            session = self._sessions.get(sid)
            if session:
                if active_only and not session.is_active:
                    continue
                if active_only and self._is_expired(session):
                    continue
                sessions.append(session)

        return sessions

    def get_active_sessions(self) -> List[SessionContext]:
        """Get all active sessions."""
        active = []
        for session in self._sessions.values():
            if session.is_active and not self._is_expired(session):
                active.append(session)
        return active

    def update_activity(
        self,
        session_id: str,
        memories_created: int = 0,
        memories_accessed: int = 0,
    ) -> bool:
        """Update session activity."""
        session = self._sessions.get(session_id)
        if not session or not session.is_active:
            return False

        session.last_activity = utc_now()
        session.conversation_turns += 1
        session.memories_created += memories_created
        session.memories_accessed += memories_accessed

        return True

    def get_session_context(
        self,
        session_id: str,
        max_turns: int = 10,
    ) -> Dict[str, Any]:
        """Get context for a session."""
        session = self._sessions.get(session_id)
        if not session:
            return {}

        return {
            "session_id": session.session_id,
            "user_id": session.user_id,
            "agent_name": session.agent_name,
            "duration_minutes": session.duration_minutes,
            "conversation_turns": session.conversation_turns,
            "memories_created": session.memories_created,
            "memories_accessed": session.memories_accessed,
            "is_active": session.is_active,
            "metadata": session.metadata,
        }

    def cleanup_expired(self) -> int:
        """Clean up expired sessions."""
        expired_ids = [sid for sid, session in self._sessions.items() if self._is_expired(session)]

        for sid in expired_ids:
            session = self._sessions[sid]
            session.is_active = False

        logger.info("Cleaned up %d expired sessions", len(expired_ids))
        return len(expired_ids)

    def get_stats(self) -> Dict[str, Any]:
        """Get session statistics."""
        active = [s for s in self._sessions.values() if s.is_active]
        total = len(self._sessions)

        durations = [s.duration_minutes for s in self._sessions.values()]
        avg_duration = sum(durations) / len(durations) if durations else 0

        turns = [s.conversation_turns for s in self._sessions.values()]
        avg_turns = sum(turns) / len(turns) if turns else 0

        return {
            "total_sessions": total,
            "active_sessions": len(active),
            "avg_duration_minutes": round(avg_duration, 2),
            "avg_turns_per_session": round(avg_turns, 2),
            "total_users": len(self._user_sessions),
            "total_agents": len(self._agent_sessions),
        }

    def _is_expired(self, session: SessionContext) -> bool:
        """Check if a session is expired."""
        if not session.is_active:
            return True

        hours_since_activity = (utc_now() - session.last_activity).total_seconds() / 3600

        return hours_since_activity > self.max_session_duration_hours


# Singleton
session_manager = SessionManager()
