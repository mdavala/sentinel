#!/bin/bash
# Start Flask app and Telegram bot for Daily Delights Inventory System
# This script will run both services in the background and create PID files for management

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
FLASK_PID_FILE="$SCRIPT_DIR/flask.pid"
TELEGRAM_PID_FILE="$SCRIPT_DIR/telegram.pid"
FLASK_LOG="$LOG_DIR/flask.log"
TELEGRAM_LOG="$LOG_DIR/telegram.log"

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Function to check if a service is already running
check_running() {
    local service_name=$1
    local pid_file=$2

    if [ -f "$pid_file" ]; then
        PID=$(cat "$pid_file")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "⚠️  $service_name is already running (PID: $PID)"
            return 0
        else
            echo "🧹 Removing stale PID file for $service_name"
            rm -f "$pid_file"
        fi
    fi
    return 1
}

echo "🚀 Starting Daily Delights Services..."
echo "📁 Working directory: $SCRIPT_DIR"
echo "📝 Logs will be written to: $LOG_DIR/"
echo ""

# Start Flask App
echo "📊 Starting Flask App..."
if check_running "Flask app" "$FLASK_PID_FILE"; then
    echo "   Use './stop_services.sh' to stop it first"
    FLASK_STARTED=0
else
    cd "$SCRIPT_DIR"
    nohup python3 app.py >> "$FLASK_LOG" 2>&1 &
    FLASK_PID=$!
    echo $FLASK_PID > "$FLASK_PID_FILE"

    echo "✅ Flask app started successfully!"
    echo "   PID: $FLASK_PID"
    echo "   PID file: $FLASK_PID_FILE"
    echo "   Log file: $FLASK_LOG"
    echo "   Dashboard: http://localhost:5002"
    FLASK_STARTED=1
fi

echo ""

# Start Telegram Bot
echo "🤖 Starting Telegram Bot..."
if check_running "Telegram bot" "$TELEGRAM_PID_FILE"; then
    echo "   Use './stop_services.sh' to stop it first"
    TELEGRAM_STARTED=0
else
    # Load environment variables from .env if it exists
    if [ -f "$SCRIPT_DIR/.env" ]; then
        export $(grep -v '^#' "$SCRIPT_DIR/.env" | xargs)
    fi

    cd "$SCRIPT_DIR"
    nohup python3 telegramBot.py >> "$TELEGRAM_LOG" 2>&1 &
    TELEGRAM_PID=$!
    echo $TELEGRAM_PID > "$TELEGRAM_PID_FILE"

    echo "✅ Telegram bot started successfully!"
    echo "   PID: $TELEGRAM_PID"
    echo "   PID file: $TELEGRAM_PID_FILE"
    echo "   Log file: $TELEGRAM_LOG"
    TELEGRAM_STARTED=1
fi

echo ""
echo "📋 Management Commands:"
echo "   ./stop_services.sh    - Stop all services"
echo "   ./status_services.sh  - Check service status"
echo "   tail -f $FLASK_LOG    - View Flask logs"
echo "   tail -f $TELEGRAM_LOG - View Telegram bot logs"

# Give services a moment to start up
sleep 2

# Check if services are still running
echo ""
if [ "$FLASK_STARTED" -eq 1 ]; then
    if ps -p $FLASK_PID > /dev/null 2>&1; then
        echo "🟢 Flask app is running and ready!"
    else
        echo "🔴 Flask app failed to start. Check logs: tail $FLASK_LOG"
        rm -f "$FLASK_PID_FILE"
    fi
fi

if [ "$TELEGRAM_STARTED" -eq 1 ]; then
    if ps -p $TELEGRAM_PID > /dev/null 2>&1; then
        echo "🟢 Telegram bot is running and ready!"
    else
        echo "🔴 Telegram bot failed to start. Check logs: tail $TELEGRAM_LOG"
        rm -f "$TELEGRAM_PID_FILE"
    fi
fi
