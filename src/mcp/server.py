"""MCP server exposing supply-chain enterprise tools.

Run standalone:  python -m src.mcp.server
Connect from Cursor/Claude Desktop via mcp.json.
"""

from __future__ import annotations

import json
from typing import Any

from src.config import get_settings
from src.tools.connectors import SupplyChainTools

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    FastMCP = None  # type: ignore


def create_mcp_server() -> Any:
    if FastMCP is None:
        raise RuntimeError("mcp package not installed")

    mcp = FastMCP("supply-chain-tools", version="1.0.0")
    settings = get_settings()
    tools = SupplyChainTools(settings)

    @mcp.tool()
    def inventory_lookup(sku: str, warehouse_id: str = "DFW-01") -> str:
        """Get current stock level for a SKU at a warehouse. Requires inventory:read scope."""
        result = tools.inventory_lookup(sku, warehouse_id)
        return json.dumps({
            "success": result.success,
            "data": result.data,
            "latency_ms": result.latency_ms,
            "error": result.error,
        })

    @mcp.tool()
    def order_status(order_id: str) -> str:
        """Look up fulfillment status for an order. Requires orders:read scope."""
        result = tools.order_status(order_id)
        return json.dumps({
            "success": result.success,
            "data": result.data,
            "latency_ms": result.latency_ms,
        })

    @mcp.tool()
    def shipment_track(order_id: str) -> str:
        """Track shipment for an order. Requires logistics:read scope."""
        result = tools.shipment_track(order_id)
        return json.dumps({
            "success": result.success,
            "data": result.data,
            "latency_ms": result.latency_ms,
        })

    @mcp.tool()
    def list_tool_metadata() -> str:
        """Return standardized tool metadata (scopes, idempotency, descriptions)."""
        return json.dumps(SupplyChainTools.TOOL_METADATA, indent=2)

    return mcp


def main() -> None:
    server = create_mcp_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
