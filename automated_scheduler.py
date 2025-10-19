#!/usr/bin/env python3
"""
Automated Scheduler for Daily Delights Inventory System
Continuously monitors time and triggers daily updates at 11:00 PM IST

Features:
- Runs daily at 11:00 PM IST (23:00)
- Comprehensive logging
- Graceful error handling
- Automatic restart capability
- Manual trigger support

Usage:
    python3 automated_scheduler.py        # Start scheduler
    python3 automated_scheduler.py --now  # Run updates immediately (for testing)
"""

import schedule
import time
import sys
import logging
import argparse
import signal
import pytz
from datetime import datetime, timedelta
from pathlib import Path
import subprocess

# Setup logging
log_dir = Path(__file__).parent / "logs"
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'automated_scheduler.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class AutomatedScheduler:
    def __init__(self):
        self.base_dir = Path(__file__).parent
        self.updater_script = self.base_dir / 'daily_auto_updater.py'
        self.ist_timezone = pytz.timezone('Asia/Kolkata')
        self.running = True

        # Verify the updater script exists
        if not self.updater_script.exists():
            logger.error(f"❌ Updater script not found: {self.updater_script}")
            sys.exit(1)

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"🛑 Received signal {signum}. Shutting down scheduler...")
        self.running = False

    def get_ist_time(self):
        """Get current time in IST"""
        return datetime.now(self.ist_timezone)

    def run_daily_updates(self):
        """Execute the daily updates"""
        try:
            current_time = self.get_ist_time()
            logger.info(f"🕚 Triggered daily updates at {current_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")

            # Run the daily auto updater script
            result = subprocess.run(
                ['python3', str(self.updater_script)],
                cwd=str(self.base_dir),
                capture_output=False,  # Let it show output directly
                text=True
            )

            if result.returncode == 0:
                logger.info("✅ Daily updates completed successfully!")
            else:
                logger.error(f"❌ Daily updates failed with exit code: {result.returncode}")

        except Exception as e:
            logger.error(f"💥 Error running daily updates: {str(e)}")

    def start_scheduler(self):
        """Start the automated scheduler"""
        logger.info("="*80)
        logger.info("🚀 AUTOMATED SCHEDULER - Daily Delights Inventory System")
        logger.info("="*80)

        current_time = self.get_ist_time()
        logger.info(f"📅 Current IST Time: {current_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        logger.info(f"⏰ Scheduled to run daily at: 23:00 IST (11:00 PM)")

        # Schedule daily updates at 11:00 PM IST
        schedule.every().day.at("23:00").do(self.run_daily_updates)

        # Calculate next run time
        next_run = schedule.next_run()
        if next_run:
            # Convert to IST for display
            next_run_ist = next_run.replace(tzinfo=pytz.UTC).astimezone(self.ist_timezone)
            logger.info(f"📅 Next scheduled run: {next_run_ist.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        logger.info("🔄 Scheduler started. Waiting for scheduled time...")
        logger.info("   Press Ctrl+C to stop the scheduler")
        logger.info("-" * 80)

        # Main scheduler loop
        try:
            while self.running:
                schedule.run_pending()

                # Log status every hour
                current_minute = datetime.now().minute
                current_second = datetime.now().second

                if current_minute == 0 and current_second < 10:
                    current_ist = self.get_ist_time()
                    next_run = schedule.next_run()
                    if next_run:
                        next_run_ist = next_run.replace(tzinfo=pytz.UTC).astimezone(self.ist_timezone)
                        time_until_next = next_run_ist - current_ist
                        hours_until = time_until_next.total_seconds() / 3600
                        logger.info(f"⏳ Status: {current_ist.strftime('%H:%M IST')} - Next run in {hours_until:.1f} hours")

                time.sleep(10)  # Check every 10 seconds

        except KeyboardInterrupt:
            logger.info("⏹️  Scheduler interrupted by user")

        logger.info("🔚 Automated Scheduler stopped")

    def run_now(self):
        """Run updates immediately (for testing)"""
        logger.info("🧪 MANUAL TRIGGER - Running daily updates immediately")
        self.run_daily_updates()

def main():
    """Main function with command line argument support"""
    parser = argparse.ArgumentParser(
        description="Automated Scheduler for Daily Delights Inventory System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 automated_scheduler.py        # Start scheduler (runs daily at 11 PM IST)
  python3 automated_scheduler.py --now  # Run updates immediately (for testing)
        """
    )

    parser.add_argument(
        '--now',
        action='store_true',
        help='Run daily updates immediately instead of scheduling'
    )

    args = parser.parse_args()

    scheduler = AutomatedScheduler()

    if args.now:
        # Run updates immediately for testing
        scheduler.run_now()
    else:
        # Start the scheduler
        scheduler.start_scheduler()

if __name__ == "__main__":
    main()