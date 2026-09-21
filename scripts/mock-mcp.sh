#!/bin/bash
# MCP server giả lập (dữ liệu mô phỏng) cho demo công cụ loại MCP. Mặc định cổng 8096.
cd "$(dirname "$0")/.."
export PORT="${PORT:-8096}"
echo "Mock MCP server → http://localhost:$PORT/mcp"
exec apps/api/.venv/bin/python demo-mock/mcp_server.py
