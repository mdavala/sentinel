#!/bin/bash
# Stop Flask app and Telegram bot for Daily Delights Inventory System

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLASK_PID_FILE="$SCRIPT_DIR/flask.pid"
TELEGRAM_PID_FILE="$SCRIPT_DIR/telegram.pid"

# Function to stop a service
stop_service() {
    local service_name=$1
    local pid_file=$2

    if [ ! -f "$pid_file" ]; then
        echo "⚠️  $service_name: No PID file found (not running)"
        return 1
    fi

    PID=$(cat "$pid_file")

    if ps -p "$PID" > /dev/null 2>&1; then
        echo "🛑 Stopping $service_name (PID: $PID)..."
        kill "$PID"

        # Wait for graceful shutdown (max 10 seconds)
        local count=0
        while ps -p "$PID" > /dev/null 2>&1 && [ $count -lt 10 ]; do
            sleep 1
            count=$((count + 1))
        done

        # Force kill if still running
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "   Force stopping..."
            kill -9 "$PID"
            sleep 1
        fi

        # Verify stopped
        if ! ps -p "$PID" > /dev/null 2>&1; then
            echo "✅ $service_name stopped successfully"
            rm -f "$pid_file"
            return 0
        else
            echo "❌ Failed to stop $service_name"
            return 1
        fi
    else
        echo "⚠️  $service_name: Process not running (cleaning up PID file)"
        rm -f "$pid_file"
        return 1
    fi
}

echo "🛑 Stopping Daily Delights Services..."
echo ""

# Stop Flask app
stop_service "Flask app" "$FLASK_PID_FILE"

echo ""

# Stop Telegram bot
stop_service "Telegram bot" "$TELEGRAM_PID_FILE"

echo ""
echo "✅ All services stopped"
