#!/bin/bash
# Stop the automated scheduler for Daily Delights Inventory System

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/scheduler.pid"

echo "🛑 Stopping Daily Delights Automated Scheduler..."

# Check if PID file exists
if [ ! -f "$PID_FILE" ]; then
    echo "❌ No PID file found. Scheduler may not be running."
    echo "   PID file expected at: $PID_FILE"
    exit 1
fi

# Read the PID
PID=$(cat "$PID_FILE")

# Check if process is running
if ! ps -p "$PID" > /dev/null 2>&1; then
    echo "❌ Process with PID $PID is not running"
    echo "🧹 Removing stale PID file"
    rm -f "$PID_FILE"
    exit 1
fi

echo "📋 Found scheduler process (PID: $PID)"

# Try to stop gracefully first
echo "🤝 Sending SIGTERM to process..."
kill -TERM "$PID"

# Wait for graceful shutdown
for i in {1..10}; do
    if ! ps -p "$PID" > /dev/null 2>&1; then
        echo "✅ Scheduler stopped gracefully"
        rm -f "$PID_FILE"
        exit 0
    fi
    echo "   Waiting for graceful shutdown... ($i/10)"
    sleep 1
done

# Force stop if graceful shutdown failed
echo "⚠️  Graceful shutdown failed. Force stopping..."
kill -KILL "$PID"

# Final check
if ! ps -p "$PID" > /dev/null 2>&1; then
    echo "✅ Scheduler force stopped"
    rm -f "$PID_FILE"
else
    echo "❌ Failed to stop scheduler process"
    exit 1
fi