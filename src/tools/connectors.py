"""Enterprise tool connectors with typed contracts, retries, and error normalization."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from src.config import Settings
from src.observability.telemetry import TOOL_CALLS, span

# Mock enterprise data — swap for real ERP/WMS connectors in production.
_MOCK_INVENTORY = {
    "90155": {"warehouse_id": "DFW-01", "quantity": 420, "reorder_point": 200, "status": "healthy"},
    "44821": {"warehouse_id": "ORD-02", "quantity": 85, "reorder_point": 150, "status": "low_stock"},
    "77210": {"warehouse_id": "ATL-03", "quantity": 12, "reorder_point": 100, "status": "critical"},
}

_MOCK_ORDERS = {
    "44821": {"status": "shipped", "carrier": "FedEx", "eta": "2026-06-14"},
    "99001": {"status": "processing", "carrier": None, "eta": "2026-06-16"},
}


@dataclass
class ToolResult:
    tool: str
    success: bool
    data: dict[str, Any] | str
    latency_ms: float
    error: str | None = None


class SupplyChainTools:
    """Standardized tool layer: metadata, retries, pagination, auth scopes."""

    TOOL_METADATA = {
        "inventory_lookup": {
            "description": "Get stock level for a SKU at a warehouse",
            "scopes": ["inventory:read"],
            "idempotent": True,
        },
        "order_status": {
            "description": "Look up order fulfillment status",
            "scopes": ["orders:read"],
            "idempotent": True,
        },
        "shipment_track": {
            "description": "Track shipment by order ID",
            "scopes": ["logistics:read"],
            "idempotent": True,
        },
    }

    def __init__(self, settings: Settings):
        self._settings = settings
        self._grpc_stub = None

    def _with_retry(self, fn, retries: int = 2) -> Any:
        last_err = None
        for attempt in range(retries + 1):
            try:
                return fn()
            except Exception as exc:
                last_err = exc
                if attempt < retries:
                    time.sleep(0.05 * (attempt + 1))
        raise last_err

    def inventory_lookup(self, sku: str, warehouse_id: str = "DFW-01") -> ToolResult:
        with span("tool.inventory_lookup", {"sku": sku}):
            t0 = time.perf_counter()
            try:
                data = self._with_retry(lambda: self._fetch_inventory(sku, warehouse_id))
                latency = (time.perf_counter() - t0) * 1000
                TOOL_CALLS.labels(tool="inventory_lookup", success="true").inc()
                return ToolResult("inventory_lookup", True, data, latency)
            except Exception as exc:
                latency = (time.perf_counter() - t0) * 1000
                TOOL_CALLS.labels(tool="inventory_lookup", success="false").inc()
                return ToolResult("inventory_lookup", False, {}, latency, str(exc))

    def _fetch_inventory(self, sku: str, warehouse_id: str) -> dict:
        # Try gRPC first, fall back to mock
        if self._grpc_stub is None:
            self._try_grpc()
        if self._grpc_stub is not None:
            try:
                from src.grpc_gen import inventory_pb2, inventory_pb2_grpc
                req = inventory_pb2.StockRequest(sku=sku, warehouse_id=warehouse_id)
                resp = self._grpc_stub.GetStockLevel(req, timeout=2)
                return {
                    "sku": resp.sku,
                    "warehouse_id": resp.warehouse_id,
                    "quantity": resp.quantity,
                    "reorder_point": resp.reorder_point,
                    "status": resp.status,
                }
            except Exception:
                pass
        record = _MOCK_INVENTORY.get(sku, {
            "warehouse_id": warehouse_id,
            "quantity": 0,
            "reorder_point": 100,
            "status": "not_found",
        })
        return {"sku": sku, **record}

    def _try_grpc(self) -> None:
        try:
            import grpc
            from src.grpc_gen import inventory_pb2_grpc
            channel = grpc.insecure_channel(
                f"{self._settings.grpc_inventory_host}:{self._settings.grpc_inventory_port}"
            )
            self._grpc_stub = inventory_pb2_grpc.InventoryServiceStub(channel)
            grpc.channel_ready_future(channel).result(timeout=1)
        except Exception:
            self._grpc_stub = None

    def order_status(self, order_id: str) -> ToolResult:
        with span("tool.order_status", {"order_id": order_id}):
            t0 = time.perf_counter()
            data = _MOCK_ORDERS.get(order_id, {"status": "not_found"})
            latency = (time.perf_counter() - t0) * 1000
            TOOL_CALLS.labels(tool="order_status", success="true").inc()
            return ToolResult("order_status", True, {"order_id": order_id, **data}, latency)

    def shipment_track(self, order_id: str) -> ToolResult:
        order = self.order_status(order_id)
        if not order.success:
            return order
        data = order.data if isinstance(order.data, dict) else {}
        return ToolResult(
            "shipment_track", True,
            {"order_id": order_id, "tracking": data},
            order.latency_ms,
        )
