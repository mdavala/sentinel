#!/bin/bash
# Start the automated scheduler for Daily Delights Inventory System
# This script will run the scheduler in the background and create a PID file for management

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
PID_FILE="$SCRIPT_DIR/scheduler.pid"
LOG_FILE="$LOG_DIR/scheduler_startup.log"

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Check if scheduler is already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "⚠️  Scheduler is already running (PID: $PID)"
        echo "   Use './stop_scheduler.sh' to stop it first"
        exit 1
    else
        echo "🧹 Removing stale PID file"
        rm -f "$PID_FILE"
    fi
fi

echo "🚀 Starting Daily Delights Automated Scheduler..."
echo "📁 Working directory: $SCRIPT_DIR"
echo "📝 Logs will be written to: $LOG_DIR/"

# Start the scheduler in the background
cd "$SCRIPT_DIR"
nohup python3 automated_scheduler.py >> "$LOG_FILE" 2>&1 &
SCHEDULER_PID=$!

# Save the PID
echo $SCHEDULER_PID > "$PID_FILE"

echo "✅ Scheduler started successfully!"
echo "   PID: $SCHEDULER_PID"
echo "   PID file: $PID_FILE"
echo "   Startup log: $LOG_FILE"
echo ""
echo "📋 Scheduler will run daily updates at 11:00 PM IST"
echo ""
echo "Commands:"
echo "   ./stop_scheduler.sh    - Stop the scheduler"
echo "   ./status_scheduler.sh  - Check scheduler status"
echo "   tail -f $LOG_FILE - View startup logs"
echo "   tail -f $LOG_DIR/automated_scheduler.log - View scheduler logs"

# Give it a moment to start up
sleep 2

# Check if it's still running
if ps -p $SCHEDULER_PID > /dev/null 2>&1; then
    echo ""
    echo "🟢 Scheduler is running and ready!"
else
    echo ""
    echo "🔴 Scheduler failed to start. Check logs:"
    echo "   cat $LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
fi