#!/bin/bash
# Hệ thống lõi giả lập cho demo tool (dữ liệu mô phỏng). Mặc định cổng 8099.
cd "$(dirname "$0")/.."
PORT="${PORT:-8095}"
echo "Mock core API → http://localhost:$PORT  (docs: /docs)"
exec apps/api/.venv/bin/uvicorn core_api:app --app-dir demo-mock --host 127.0.0.1 --port "$PORT"
