.PHONY: install grpc infra api grpc-server mcp test eval demo serve run clean docker

PYTHON ?= python3
PIP ?= pip3

install:
	$(PIP) install -r requirements.txt

grpc:
	$(PYTHON) -m grpc_tools.protoc -I proto \
		--python_out=src/grpc_gen \
		--grpc_python_out=src/grpc_gen \
		proto/inventory.proto

infra:
	docker compose up -d redis chroma kafka mlflow prometheus grafana otel-collector

infra-down:
	docker compose down

api:
	$(PYTHON) -m uvicorn src.api.main:app --host 0.0.0.0 --port 8080 --reload

grpc-server:
	$(PYTHON) -m src.tools.inventory_grpc_server

mcp:
	$(PYTHON) -m src.mcp.server

test:
	$(PYTHON) -m pytest tests/ -v

eval:
	$(PYTHON) -m harness.runner

eval-gates:
	curl -s -X POST http://localhost:8080/v1/eval/run \
		-H 'Content-Type: application/json' \
		-d '{"judge_threshold": 0.6, "judge_seed": 7}' | $(PYTHON) -m json.tool

demo:
	@echo "Governance interactive demo: http://localhost:8000"
	$(PYTHON) app.py

serve: eval
	@echo "Static dashboard: http://localhost:8000/dashboard.html"
	$(PYTHON) -m http.server 8000

run: eval

docker-build:
	docker build -t supply-chain-agent .

docker-run:
	docker run -p 8080:8080 -p 50051:50051 supply-chain-agent

clean:
	rm -f results/results.json results/results.csv
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
