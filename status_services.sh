#!/bin/bash
# Check status of Flask app and Telegram bot for Daily Delights Inventory System

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
FLASK_PID_FILE="$SCRIPT_DIR/flask.pid"
TELEGRAM_PID_FILE="$SCRIPT_DIR/telegram.pid"
FLASK_LOG="$LOG_DIR/flask.log"
TELEGRAM_LOG="$LOG_DIR/telegram.log"

# Function to check service status
check_status() {
    local service_name=$1
    local pid_file=$2
    local log_file=$3
    local port=$4

    if [ -f "$pid_file" ]; then
        PID=$(cat "$pid_file")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "✅ $service_name: Running (PID: $PID)"

            # Get process info
            local cpu_mem=$(ps -p "$PID" -o %cpu,%mem | tail -n 1)
            echo "   CPU/MEM: $cpu_mem"

            # Get uptime
            local start_time=$(ps -p "$PID" -o lstart= 2>/dev/null)
            if [ -n "$start_time" ]; then
                echo "   Started: $start_time"
            fi

            # Check port if specified
            if [ -n "$port" ]; then
                if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
                    echo "   Port $port: Listening ✅"
                    echo "   URL: http://localhost:$port"
                fi
            fi

            # Show last log lines if available
            if [ -f "$log_file" ]; then
                echo "   Log: $log_file"
                echo "   Last 3 lines:"
                tail -n 3 "$log_file" 2>/dev/null | sed 's/^/     /'
            fi

            return 0
        else
            echo "❌ $service_name: Not running (stale PID file)"
            rm -f "$pid_file"
            return 1
        fi
    else
        echo "❌ $service_name: Not running (no PID file)"
        return 1
    fi
}

echo "================================================"
echo "  Daily Delights - Service Status"
echo "================================================"
echo ""

# Check Flask app
check_status "Flask app" "$FLASK_PID_FILE" "$FLASK_LOG" "5002"
FLASK_RUNNING=$?

echo ""

# Check Telegram bot
check_status "Telegram bot" "$TELEGRAM_PID_FILE" "$TELEGRAM_LOG"
TELEGRAM_RUNNING=$?

echo ""
echo "================================================"
echo "  Quick Actions"
echo "================================================"

if [ $FLASK_RUNNING -ne 0 ] || [ $TELEGRAM_RUNNING -ne 0 ]; then
    echo "To start services: ./start_services.sh"
fi

if [ $FLASK_RUNNING -eq 0 ] || [ $TELEGRAM_RUNNING -eq 0 ]; then
    echo "To stop services: ./stop_services.sh"
    echo "To view Flask logs: tail -f $FLASK_LOG"
    echo "To view Telegram logs: tail -f $TELEGRAM_LOG"
fi

echo "================================================"

# Return appropriate exit code
if [ $FLASK_RUNNING -eq 0 ] && [ $TELEGRAM_RUNNING -eq 0 ]; then
    exit 0
else
    exit 1
fi
