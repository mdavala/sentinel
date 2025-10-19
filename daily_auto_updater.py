#!/usr/bin/env python3
"""
Daily Auto Updater - Automated Daily Updates for Daily Delights Inventory System
Runs every day at 11:00 PM IST to update:
- Payments (UOB email processing)
- Daily Book Closing (Google Drive sales reports)
- Invoices (Google Drive invoice processing)
"""

import subprocess
import os
import sys
import logging
import pytz
from datetime import datetime, time
from pathlib import Path

# Setup logging
log_dir = Path(__file__).parent / "logs"
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'daily_auto_updater.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class DailyAutoUpdater:
    def __init__(self):
        self.base_dir = Path(__file__).parent
        self.scripts = {
            'payments': 'uob_payment_emails.py',
            'daily_book_closing': 'dailyBookClosing.py',
            'invoices': 'stockSentinel.py'
        }

    def run_script(self, script_name, script_file, timeout=600):
        """Run a processing script with proper error handling"""
        try:
            script_path = self.base_dir / script_file

            if not script_path.exists():
                logger.error(f"❌ Script not found: {script_path}")
                return False

            logger.info(f"🚀 Starting {script_name} update...")
            logger.info(f"   Running: python3 {script_path}")

            # Run the script
            result = subprocess.run(
                ['python3', str(script_path)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.base_dir)
            )

            if result.returncode == 0:
                logger.info(f"✅ {script_name} update completed successfully")

                # Log summary if available
                if result.stdout:
                    output_lines = result.stdout.strip().split('\n')
                    # Look for summary lines
                    summary_lines = [line for line in output_lines if '🎯 Summary:' in line or 'Successfully Processed:' in line]

                    if summary_lines:
                        logger.info(f"   Summary: {summary_lines[-1]}")
                    else:
                        # Log last few non-empty lines as summary
                        non_empty_lines = [line for line in output_lines if line.strip()]
                        if non_empty_lines:
                            logger.info(f"   Output: {non_empty_lines[-1]}")

                return True

            else:
                logger.error(f"❌ {script_name} update failed")
                if result.stderr:
                    logger.error(f"   Error: {result.stderr}")
                if result.stdout:
                    logger.error(f"   Output: {result.stdout}")
                return False

        except subprocess.TimeoutExpired:
            logger.error(f"⏰ {script_name} update timed out after {timeout} seconds")
            return False

        except Exception as e:
            logger.error(f"❌ Unexpected error in {script_name} update: {str(e)}")
            return False

    def run_all_updates(self):
        """Run all daily updates in sequence"""
        logger.info("="*80)
        logger.info("🌙 DAILY AUTO UPDATER - Starting daily updates at 11:00 PM IST")
        logger.info("="*80)

        # Get IST time
        ist_timezone = pytz.timezone('Asia/Kolkata')
        current_time_ist = datetime.now(ist_timezone)
        logger.info(f"📅 Current IST Time: {current_time_ist.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        results = {}

        # 1. Update Payments (UOB emails)
        logger.info("\n📧 STEP 1: Processing UOB payment emails...")
        results['payments'] = self.run_script('Payments', self.scripts['payments'], timeout=120)

        # 2. Update Daily Book Closing (Google Drive sales reports)
        logger.info("\n📊 STEP 2: Processing daily book closing reports...")
        results['daily_book_closing'] = self.run_script('Daily Book Closing', self.scripts['daily_book_closing'], timeout=600)

        # 3. Update Invoices (Google Drive invoices)
        logger.info("\n📄 STEP 3: Processing invoices from Google Drive...")
        results['invoices'] = self.run_script('Invoices', self.scripts['invoices'], timeout=600)

        # Summary
        logger.info("\n" + "="*80)
        logger.info("📋 DAILY UPDATE SUMMARY")
        logger.info("="*80)

        successful_updates = 0
        total_updates = len(results)

        for update_type, success in results.items():
            status = "✅ SUCCESS" if success else "❌ FAILED"
            logger.info(f"   {update_type.replace('_', ' ').title():20} : {status}")
            if success:
                successful_updates += 1

        success_rate = (successful_updates / total_updates) * 100
        logger.info(f"\n📈 Success Rate: {successful_updates}/{total_updates} ({success_rate:.1f}%)")

        if successful_updates == total_updates:
            logger.info("🎉 All daily updates completed successfully!")
            return True
        else:
            logger.warning(f"⚠️  {total_updates - successful_updates} update(s) failed. Check logs for details.")
            return False

def main():
    """Main function to run all daily updates"""
    updater = DailyAutoUpdater()

    try:
        success = updater.run_all_updates()
        exit_code = 0 if success else 1

        logger.info(f"\n🔚 Daily Auto Updater finished with exit code: {exit_code}")
        sys.exit(exit_code)

    except KeyboardInterrupt:
        logger.info("\n⏹️  Daily Auto Updater interrupted by user")
        sys.exit(1)

    except Exception as e:
        logger.error(f"\n💥 Fatal error in Daily Auto Updater: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()