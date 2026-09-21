#!/bin/bash
# Serve the mock bank website (demo-site/) on its own origin so the embed allowlist is exercised for real.
#   ./scripts/demo-site.sh            → http://localhost:8090  (allow-listed by seed_demo)
#   PORT=8091 ./scripts/demo-site.sh  → http://localhost:8091  (NOT allow-listed → widget must be blocked)
cd "$(dirname "$0")/../demo-site" || exit 1
PORT="${PORT:-8090}"
if [ ! -f config.js ]; then
  echo "demo-site/config.js chưa có — chạy 'python -m app.seed_demo' trong apps/api để sinh (hoặc copy config.example.js)."
fi
echo "Demo site → http://localhost:${PORT}  (Ctrl+C để dừng)"
exec python3 -m http.server "$PORT" --bind 127.0.0.1
