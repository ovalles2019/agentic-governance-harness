"""Agentic memory layer — Redis-backed session memory (MEM0-style pattern)."""

from __future__ import annotations

import json
import time
from typing import Any

from src.config import Settings


class AgentMemory:
    """Session-scoped memory with TTL. Falls back to in-process dict when Redis unavailable."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._local: dict[str, list[dict]] = {}
        self._redis = None
        if settings.redis_url:
            try:
                import redis
                self._redis = redis.from_url(settings.redis_url, decode_responses=True)
                self._redis.ping()
            except Exception:
                self._redis = None

    def _key(self, session_id: str) -> str:
        return f"agent:memory:{session_id}"

    def append(self, session_id: str, role: str, content: str, metadata: dict | None = None) -> None:
        entry = {
            "role": role,
            "content": content,
            "metadata": metadata or {},
            "ts": time.time(),
        }
        if self._redis:
            self._redis.rpush(self._key(session_id), json.dumps(entry))
            self._redis.expire(self._key(session_id), 86400)
        else:
            self._local.setdefault(session_id, []).append(entry)

    def get_history(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        if self._redis:
            raw = self._redis.lrange(self._key(session_id), -limit, -1)
            return [json.loads(r) for r in raw]
        return self._local.get(session_id, [])[-limit:]

    def summarize_context(self, session_id: str) -> str:
        history = self.get_history(session_id, limit=6)
        if not history:
            return ""
        lines = [f"{h['role']}: {h['content'][:200]}" for h in history]
        return "Prior conversation:\n" + "\n".join(lines)

    def health(self) -> str:
        if self._redis:
            try:
                self._redis.ping()
                return "connected"
            except Exception:
                return "error"
        return "in_memory_fallback"
