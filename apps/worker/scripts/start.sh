#!/bin/bash
# Start the RQ worker with macOS fork safety disabled
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
cd "$(dirname "$0")/.."

# Load .env from project root
if [ -f "../../.env" ]; then
  set -a
  source ../../.env
  set +a
fi

echo "Starting worker..."
echo "  REDIS_URL=$REDIS_URL"
echo "  OBJC_DISABLE_INITIALIZE_FORK_SAFETY=$OBJC_DISABLE_INITIALIZE_FORK_SAFETY"

python -m worker.main
