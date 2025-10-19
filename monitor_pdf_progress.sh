#!/bin/bash
# Real-time PDF Processing Monitor
# Shows progress, success/failure rates, current file, and more

LOG_FILE="pdf_processing.log"

clear
echo "============================================================"
echo "  📊 PDF PROCESSING MONITOR - Live Dashboard"
echo "============================================================"
echo ""

while true; do
    # Move cursor to beginning
    tput cup 4 0

    # Get current timestamp
    echo "⏰ Last Update: $(date '+%H:%M:%S')"
    echo ""

    # Total PDFs
    echo "📂 TOTAL PDFs TO PROCESS: 81"
    echo ""

    # Count processed (both success and failed)
    TOTAL_PROCESSED=$(grep -c "Processing [0-9]*/81:" "$LOG_FILE" 2>/dev/null || echo "0")
    echo "📊 FILES PROCESSED: $TOTAL_PROCESSED / 81"

    # Calculate progress percentage
    if [ "$TOTAL_PROCESSED" -gt 0 ]; then
        PROGRESS=$((TOTAL_PROCESSED * 100 / 81))
        echo "📈 PROGRESS: $PROGRESS%"

        # Progress bar
        BAR_LENGTH=50
        FILLED=$((PROGRESS * BAR_LENGTH / 100))
        EMPTY=$((BAR_LENGTH - FILLED))
        printf "["
        printf "%${FILLED}s" | tr ' ' '='
        printf "%${EMPTY}s" | tr ' ' '-'
        printf "]\n"
    else
        echo "📈 PROGRESS: 0%"
        printf "[%50s]\n" | tr ' ' '-'
    fi
    echo ""

    # Success count
    SUCCESS=$(grep -c "✅ Saved invoice" "$LOG_FILE" 2>/dev/null || echo "0")
    echo "✅ SUCCESSFULLY PROCESSED: $SUCCESS"

    # Failed count
    FAILED=$(grep -c "❌ Failed to extract data" "$LOG_FILE" 2>/dev/null || echo "0")
    echo "❌ FAILED: $FAILED"

    # Skipped duplicates
    SKIPPED=$(grep -c "⚠️ Invoice .* already exists" "$LOG_FILE" 2>/dev/null || echo "0")
    echo "⏭️  SKIPPED (Duplicates): $SKIPPED"
    echo ""

    # Calculate success rate
    if [ "$TOTAL_PROCESSED" -gt 0 ]; then
        SUCCESS_RATE=$((SUCCESS * 100 / TOTAL_PROCESSED))
        echo "📊 SUCCESS RATE: $SUCCESS_RATE%"
    fi
    echo ""

    # Current file being processed
    CURRENT_FILE=$(grep "Processing [0-9]*/81:" "$LOG_FILE" 2>/dev/null | tail -1 | sed 's/.*Processing [0-9]*\/81: //' || echo "None")
    echo "🔄 CURRENTLY PROCESSING:"
    echo "   $CURRENT_FILE"
    echo ""

    # Recent activity (last 3 files)
    echo "📋 RECENT ACTIVITY:"
    tail -30 "$LOG_FILE" 2>/dev/null | grep -E "✅ Saved invoice|❌ Failed to extract" | tail -3 | sed 's/^/   /'
    echo ""

    # Estimated time remaining
    if [ "$TOTAL_PROCESSED" -gt 0 ] && [ "$TOTAL_PROCESSED" -lt 81 ]; then
        REMAINING=$((81 - TOTAL_PROCESSED))
        # 8 seconds per PDF
        TIME_REMAINING=$((REMAINING * 8))
        MINUTES=$((TIME_REMAINING / 60))
        SECONDS=$((TIME_REMAINING % 60))
        echo "⏱️  ESTIMATED TIME REMAINING: ${MINUTES}m ${SECONDS}s"
    fi
    echo ""

    # Check if process is still running
    if pgrep -f "python3 process_june_invoices.py" > /dev/null; then
        echo "🟢 STATUS: PROCESSING..."
    else
        if [ "$TOTAL_PROCESSED" -eq 81 ]; then
            echo "🎉 STATUS: COMPLETE!"
            echo ""
            echo "============================================================"
            echo "  FINAL SUMMARY"
            echo "============================================================"
            echo "✅ Successfully Processed: $SUCCESS"
            echo "❌ Failed: $FAILED"
            echo "⏭️  Skipped: $SKIPPED"
            echo "📊 Total: $TOTAL_PROCESSED"
            echo ""
            echo "Check supplierOrders.db for results!"
            break
        else
            echo "⚠️  STATUS: STOPPED (Process not running)"
            break
        fi
    fi

    echo ""
    echo "Press Ctrl+C to exit monitor"
    echo "============================================================"

    # Refresh every 2 seconds
    sleep 2
done
