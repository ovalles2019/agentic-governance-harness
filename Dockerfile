FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Generate gRPC stubs at build time
RUN python -m grpc_tools.protoc \
    -I proto \
    --python_out=src/grpc_gen \
    --grpc_python_out=src/grpc_gen \
    proto/inventory.proto

ENV PYTHONPATH=/app
EXPOSE 8080 50051

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
