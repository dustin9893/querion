#!/bin/bash
# MCP server giả lập "Kho dữ liệu báo cáo" (số liệu tổng hợp, dữ liệu mô phỏng). Mặc định cổng 8097.
cd "$(dirname "$0")/.."
export PORT="${PORT:-8097}"
echo "Mock DWH (MCP) → http://localhost:$PORT/mcp"
exec apps/api/.venv/bin/python demo-mock/dwh_mcp.py
