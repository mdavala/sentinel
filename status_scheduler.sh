#!/bin/bash
# Check the status of the automated scheduler for Daily Delights Inventory System

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/scheduler.pid"
LOG_DIR="$SCRIPT_DIR/logs"

echo "📊 Daily Delights Automated Scheduler Status"
echo "=" * 50

# Check if PID file exists
if [ ! -f "$PID_FILE" ]; then
    echo "🔴 Status: NOT RUNNING"
    echo "   No PID file found at: $PID_FILE"
    echo ""
    echo "💡 To start the scheduler:"
    echo "   ./start_scheduler.sh"
    exit 0
fi

# Read the PID
PID=$(cat "$PID_FILE")

# Check if process is running
if ps -p "$PID" > /dev/null 2>&1; then
    echo "🟢 Status: RUNNING"
    echo "   PID: $PID"

    # Get process info
    if command -v ps >/dev/null 2>&1; then
        echo "   Started: $(ps -p $PID -o lstart= 2>/dev/null | xargs)"
        echo "   CPU/Memory: $(ps -p $PID -o %cpu,%mem,time= 2>/dev/null | xargs)"
    fi

    echo ""
    echo "📁 Files:"
    echo "   PID file: $PID_FILE"

    if [ -d "$LOG_DIR" ]; then
        echo "   Log directory: $LOG_DIR/"
        echo ""
        echo "📝 Recent log files:"
        ls -la "$LOG_DIR"/*.log 2>/dev/null | tail -5 | while read line; do
            echo "     $line"
        done
    fi

    echo ""
    echo "💡 Commands:"
    echo "   ./stop_scheduler.sh                        - Stop the scheduler"
    echo "   tail -f $LOG_DIR/automated_scheduler.log   - View live scheduler logs"
    echo "   tail -f $LOG_DIR/daily_auto_updater.log    - View live update logs"

else
    echo "🔴 Status: STOPPED (stale PID file)"
    echo "   PID file exists but process $PID is not running"
    echo "   PID file: $PID_FILE"
    echo ""
    echo "🧹 Cleaning up stale PID file..."
    rm -f "$PID_FILE"
    echo "   Removed stale PID file"
    echo ""
    echo "💡 To start the scheduler:"
    echo "   ./start_scheduler.sh"
fi

# Show next scheduled time (if we can determine it)
echo ""
echo "⏰ Next scheduled run: 11:00 PM IST (23:00) daily"

# Check if timezone info is available
if command -v python3 >/dev/null 2>&1; then
    python3 -c "
import pytz
from datetime import datetime, time, timedelta
try:
    ist = pytz.timezone('Asia/Kolkata')
    now_ist = datetime.now(ist)

    # Calculate next 11 PM IST
    today_11pm = now_ist.replace(hour=23, minute=0, second=0, microsecond=0)
    if now_ist >= today_11pm:
        next_run = today_11pm + timedelta(days=1)
    else:
        next_run = today_11pm

    print(f'   Current IST time: {now_ist.strftime(\"%Y-%m-%d %H:%M:%S %Z\")}')
    print(f'   Next run time: {next_run.strftime(\"%Y-%m-%d %H:%M:%S %Z\")}')

    time_until = next_run - now_ist
    hours_until = time_until.total_seconds() / 3600
    print(f'   Time until next run: {hours_until:.1f} hours')
except:
    pass
" 2>/dev/null
fi