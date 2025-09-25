# Daily Delights Automated Update System 🕚

This automated system runs daily at **11:00 PM IST** to update your inventory management system with the latest data from emails and Google Drive.

## 🎯 What It Does

The system automatically processes:

1. **💰 Payments** - Fetches and processes UOB payment emails from last 24 hours
2. **📊 Daily Book Closing** - Processes daily sales reports from Google Drive
3. **📄 Invoices** - Processes invoice images from Google Drive

## 📁 Files Created

- `daily_auto_updater.py` - Core automation script that runs all updates
- `automated_scheduler.py` - Scheduler that triggers updates at 11 PM IST daily
- `start_scheduler.sh` - Easy script to start the automated scheduler
- `stop_scheduler.sh` - Easy script to stop the automated scheduler
- `status_scheduler.sh` - Check if scheduler is running and view status
- `logs/` - Directory containing all automation logs

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip3 install schedule pytz
```

### 2. Start the Automated Scheduler
```bash
./start_scheduler.sh
```

### 3. Check Status
```bash
./status_scheduler.sh
```

### 4. Stop the Scheduler (if needed)
```bash
./stop_scheduler.sh
```

## 📋 Detailed Usage

### Starting the Scheduler

**Option 1: Use the shell script (recommended)**
```bash
./start_scheduler.sh
```

**Option 2: Run directly with Python**
```bash
python3 automated_scheduler.py
```

The scheduler will:
- Run continuously in the background
- Execute daily updates at exactly 11:00 PM IST
- Create detailed logs in the `logs/` directory
- Show status updates every hour

### Testing the System

To test the automation immediately (without waiting for 11 PM):

```bash
python3 automated_scheduler.py --now
```

OR

```bash
python3 daily_auto_updater.py
```

### Monitoring

**Check Scheduler Status:**
```bash
./status_scheduler.sh
```

**View Live Logs:**
```bash
# Scheduler logs
tail -f logs/automated_scheduler.log

# Daily update logs
tail -f logs/daily_auto_updater.log

# Startup logs
tail -f logs/scheduler_startup.log
```

## 📊 What Happens at 11 PM IST

1. **🕚 11:00 PM IST Trigger**
   - Scheduler detects the time and starts daily updates

2. **📧 Step 1: Payment Processing**
   - Runs `uob_payment_emails.py`
   - Fetches UOB emails from last 24 hours
   - Processes payment confirmations
   - Updates payments table directly (no invoice validation)
   - Timeout: 2 minutes

3. **📊 Step 2: Daily Book Closing**
   - Runs `dailyBookClosing.py`
   - Processes daily sales reports from Google Drive
   - Updates daily book closing table
   - Timeout: 10 minutes

4. **📄 Step 3: Invoice Processing**
   - Runs `stockSentinel.py`
   - Processes invoice images from Google Drive
   - Updates invoice and inventory tables
   - Timeout: 10 minutes

5. **📋 Summary Report**
   - Shows success/failure status for each update
   - Logs detailed results
   - Provides success rate statistics

## 🔧 Configuration

### Changing the Schedule Time

To change from 11:00 PM IST to a different time, edit `automated_scheduler.py`:

```python
# Change this line (line ~85):
schedule.every().day.at("23:00").do(self.run_daily_updates)

# Example: For 10:30 PM IST:
schedule.every().day.at("22:30").do(self.run_daily_updates)
```

### Adjusting Timeouts

Edit `daily_auto_updater.py` to change script timeouts:

```python
# In the run_all_updates method:
results['payments'] = self.run_script('Payments', self.scripts['payments'], timeout=120)  # 2 minutes
results['daily_book_closing'] = self.run_script('Daily Book Closing', self.scripts['daily_book_closing'], timeout=600)  # 10 minutes
results['invoices'] = self.run_script('Invoices', self.scripts['invoices'], timeout=600)  # 10 minutes
```

## 📝 Logs Explanation

### Log Files Location: `logs/`

- `automated_scheduler.log` - Main scheduler activity and status
- `daily_auto_updater.log` - Detailed update process results
- `scheduler_startup.log` - Shell script startup messages

### Log Format
```
2025-09-25 23:00:01,234 - INFO - 🌙 DAILY AUTO UPDATER - Starting daily updates at 11:00 PM IST
2025-09-25 23:00:01,235 - INFO - 📅 Current IST Time: 2025-09-25 23:00:01 IST
2025-09-25 23:00:01,236 - INFO - 📧 STEP 1: Processing UOB payment emails...
2025-09-25 23:00:03,456 - INFO - ✅ Payments update completed successfully
2025-09-25 23:00:03,456 - INFO -    Summary: Found 3 payment emails in last 24 hours, successfully processed 2
```

## 🛡️ Error Handling

The system includes comprehensive error handling:

- **Script failures** are logged with error details
- **Timeouts** are handled gracefully with warning messages
- **Process crashes** are caught and reported
- **File not found** errors are detected and reported
- **Network issues** during email fetching are handled

### Common Issues and Solutions

**Issue: Scheduler not starting**
```bash
# Check for permission issues
chmod +x *.sh

# Check Python path
which python3

# Check dependencies
python3 -c "import schedule, pytz; print('OK')"
```

**Issue: Scripts timing out**
- Increase timeout values in `daily_auto_updater.py`
- Check network connectivity for Google Drive/Gmail access
- Verify credentials files are present

**Issue: No payment emails found**
- Check Gmail credentials and authentication
- Verify UOB emails are reaching the Gmail account
- Check spam/promotions folders

## 🔄 System Integration

### Flask App Integration

The automated system works alongside your Flask app by:

1. **Using same scripts** - Calls the same `uob_payment_emails.py`, `dailyBookClosing.py`, and `stockSentinel.py` that the Flask app uses
2. **Same database** - Updates the same `dailydelights.db` database
3. **Independent operation** - Runs without interfering with Flask app operation
4. **Same results** - Produces identical results to clicking "Update" buttons in Flask GUI

### Manual vs Automated Updates

You can still use the Flask app's manual update buttons anytime:
- **Payments Page** → "Update Payments" button
- **Daily Book Closing Page** → "Update" button
- **Invoices Page** → "Update" button

The automated system simply runs these same operations at 11 PM daily.

## 🔧 Maintenance

### Daily Maintenance (Automatic)
- System runs automatically every day at 11 PM IST
- Logs rotate automatically (older logs are preserved)
- Database updates happen automatically

### Weekly Maintenance (Manual)
```bash
# Check status
./status_scheduler.sh

# Review logs for any recurring issues
less logs/automated_scheduler.log

# Clean up very old logs (optional)
find logs/ -name "*.log" -mtime +30 -delete
```

### Monthly Maintenance (Manual)
- Review success rates in logs
- Check disk space usage of logs directory
- Verify all three update types are working correctly

## 🚨 Troubleshooting

### Scheduler Not Running
```bash
# Check status
./status_scheduler.sh

# Start if stopped
./start_scheduler.sh

# Check for errors
cat logs/scheduler_startup.log
```

### Updates Failing
```bash
# Check detailed update logs
tail -f logs/daily_auto_updater.log

# Test individual components
python3 uob_payment_emails.py
python3 dailyBookClosing.py
python3 stockSentinel.py

# Test full update cycle manually
python3 daily_auto_updater.py
```

### High Resource Usage
```bash
# Check process resource usage
./status_scheduler.sh

# Restart scheduler if needed
./stop_scheduler.sh
./start_scheduler.sh
```

## 📞 Support

If you encounter issues:

1. **Check logs first** - Most issues are explained in the log files
2. **Test individual scripts** - Run `uob_payment_emails.py`, `dailyBookClosing.py`, `stockSentinel.py` individually
3. **Verify dependencies** - Ensure `schedule` and `pytz` are installed
4. **Check permissions** - Ensure shell scripts are executable (`chmod +x *.sh`)

## 🎉 Success!

Once set up, your Daily Delights inventory system will automatically update every night at 11 PM IST with:
- ✅ Latest payment confirmations from UOB emails
- ✅ Daily sales reports from Google Drive
- ✅ New invoices and inventory updates from Google Drive

The system runs silently in the background, ensuring your data is always up-to-date when you start your business day! 🌅