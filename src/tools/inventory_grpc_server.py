"""gRPC inventory microservice — high-throughput enterprise connector."""

from __future__ import annotations

import logging
from concurrent import futures

import grpc

from src.grpc_gen import inventory_pb2, inventory_pb2_grpc

logger = logging.getLogger(__name__)

_MOCK = {
    "90155": {"quantity": 420, "reorder_point": 200, "status": "healthy"},
    "44821": {"quantity": 85, "reorder_point": 150, "status": "low_stock"},
    "77210": {"quantity": 12, "reorder_point": 100, "status": "critical"},
}


class InventoryServicer(inventory_pb2_grpc.InventoryServiceServicer):
    def GetStockLevel(self, request, context):
        record = _MOCK.get(request.sku, {"quantity": 0, "reorder_point": 100, "status": "not_found"})
        return inventory_pb2.StockResponse(
            sku=request.sku,
            warehouse_id=request.warehouse_id or "DFW-01",
            quantity=record["quantity"],
            reorder_point=record["reorder_point"],
            status=record["status"],
        )

    def ListLowStock(self, request, context):
        for sku, record in _MOCK.items():
            if record["quantity"] < request.threshold_units:
                yield inventory_pb2.StockResponse(
                    sku=sku,
                    warehouse_id=request.warehouse_id,
                    quantity=record["quantity"],
                    reorder_point=record["reorder_point"],
                    status=record["status"],
                )


def serve(port: int = 50051) -> None:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    inventory_pb2_grpc.add_InventoryServiceServicer_to_server(InventoryServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    logger.info("Inventory gRPC service listening on :%d", port)
    server.wait_for_termination()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    serve()
