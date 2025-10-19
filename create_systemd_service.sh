#!/bin/bash
# Create a systemd service for Daily Delights Automated Scheduler
# This allows the scheduler to start automatically on system boot

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="dailydelights-scheduler"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ This script must be run as root (use sudo)"
    echo "   sudo ./create_systemd_service.sh"
    exit 1
fi

echo "🔧 Creating systemd service for Daily Delights Scheduler..."
echo "📁 Working directory: $SCRIPT_DIR"
echo "📝 Service file: $SERVICE_FILE"

# Create the systemd service file
cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Daily Delights Automated Scheduler
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=$SUDO_USER
Group=$SUDO_USER
WorkingDirectory=$SCRIPT_DIR
Environment=PATH=/usr/local/bin:/usr/bin:/bin
ExecStart=/usr/bin/python3 $SCRIPT_DIR/automated_scheduler.py
Restart=always
RestartSec=10
StandardOutput=append:$SCRIPT_DIR/logs/systemd_service.log
StandardError=append:$SCRIPT_DIR/logs/systemd_service_error.log

[Install]
WantedBy=multi-user.target
EOF

echo "✅ Service file created at: $SERVICE_FILE"

# Create logs directory if it doesn't exist
mkdir -p "$SCRIPT_DIR/logs"
chown $SUDO_USER:$SUDO_USER "$SCRIPT_DIR/logs"

# Reload systemd and enable the service
echo "🔄 Reloading systemd daemon..."
systemctl daemon-reload

echo "⚡ Enabling service to start on boot..."
systemctl enable "$SERVICE_NAME"

echo "🚀 Starting service..."
systemctl start "$SERVICE_NAME"

# Check status
sleep 2
echo ""
echo "📊 Service Status:"
systemctl status "$SERVICE_NAME" --no-pager

echo ""
echo "✅ Daily Delights Scheduler service created successfully!"
echo ""
echo "📋 Service Management Commands:"
echo "   sudo systemctl start $SERVICE_NAME     # Start the service"
echo "   sudo systemctl stop $SERVICE_NAME      # Stop the service"
echo "   sudo systemctl restart $SERVICE_NAME   # Restart the service"
echo "   sudo systemctl status $SERVICE_NAME    # Check status"
echo "   sudo systemctl enable $SERVICE_NAME    # Enable on boot"
echo "   sudo systemctl disable $SERVICE_NAME   # Disable on boot"
echo ""
echo "📝 View Logs:"
echo "   sudo journalctl -u $SERVICE_NAME -f    # Follow live logs"
echo "   tail -f $SCRIPT_DIR/logs/systemd_service.log"