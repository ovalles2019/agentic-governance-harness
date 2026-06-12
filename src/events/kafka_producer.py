"""Kafka event publisher for agent lifecycle events."""

from __future__ import annotations

import json
import time
from typing import Any

from src.config import Settings


class EventPublisher:
    """Publishes structured agent events for downstream analytics."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._producer = None
        if settings.enable_kafka and settings.kafka_bootstrap:
            try:
                from aiokafka import AIOKafkaProducer
                self._producer_cls = AIOKafkaProducer
                self._bootstrap = settings.kafka_bootstrap
            except Exception:
                self._producer_cls = None

    async def connect(self) -> None:
        if self._producer_cls and self._bootstrap:
            self._producer = self._producer_cls(
                bootstrap_servers=self._bootstrap,
                value_serializer=lambda v: json.dumps(v).encode(),
            )
            await self._producer.start()

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        event = {
            "type": event_type,
            "timestamp": time.time(),
            "payload": payload,
        }
        if self._producer:
            await self._producer.send_and_wait(self._settings.kafka_topic, event)
        else:
            # Structured log fallback for local dev without Kafka
            print(f"[event] {json.dumps(event)}")

    async def close(self) -> None:
        if self._producer:
            await self._producer.stop()

    def health(self) -> str:
        if self._producer:
            return "connected"
        if self._settings.enable_kafka:
            return "disconnected"
        return "disabled"
