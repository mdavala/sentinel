from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, ConversationHandler, filters, ContextTypes
import os
import tempfile
import logging
import asyncio
import sqlite3
from datetime import datetime, date

# Google Drive imports (OAuth2 - same as stockSentinel.py)
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv()

# Bot configuration - Added error checking for BOT_TOKEN
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ Error: BOT_TOKEN environment variable not set!")
    print("Please set your bot token: export BOT_TOKEN='your_bot_token_here'")
    exit(1)

BOTNAME = "@ddSentinel_Bot"

# Google Drive folder IDs
INVOICES_FOLDER_ID = "162d4TyRYwvGXdeVYkZTAY6AMpc50sJtf"
DAILY_BOOK_CLOSING_FOLDER_ID = "1sxtFv5mgGSafgWQ3UufW1D2c9f4xE7-Y"

# Google Drive OAuth2 credentials (same as stockSentinel.py)
SCOPES = ['https://www.googleapis.com/auth/drive']
CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.json'

# Global variable to store user states and upload counters
user_states = {}
upload_counters = {}  # Added missing upload_counters dictionary
upload_locks = {}  # To prevent concurrent upload issues per user

# Conversation states for cash denomination
(DENOMINATION_START, DENOMINATION_INPUT, DENOMINATION_CONFIRM) = range(3)

# Cash denomination structure based on the image
DENOMINATIONS = [
    {'name': '$100', 'value': 100.00, 'type': 'dollar'},
    {'name': '$50', 'value': 50.00, 'type': 'dollar'},
    {'name': '$10', 'value': 10.00, 'type': 'dollar'},
    {'name': '$5', 'value': 5.00, 'type': 'dollar'},
    {'name': '$2', 'value': 2.00, 'type': 'dollar'},
    {'name': '$1', 'value': 1.00, 'type': 'dollar'},
    {'name': '50¢', 'value': 0.50, 'type': 'cent'},
    {'name': '20¢', 'value': 0.20, 'type': 'cent'},
    {'name': '10¢', 'value': 0.10, 'type': 'cent'},
    {'name': '5¢', 'value': 0.05, 'type': 'cent'},
]

def generate_random_filename(mode, counter):
    """Generate a filename with timestamp and counter"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if mode == 'upload_invoices':
        return f"invoice_{timestamp}_{counter}.jpg"
    else:  # upload_dailybookclosing
        return f"dailybook_{timestamp}_{counter}.jpg"

class DriveUploader:
    def __init__(self):
        self.service = None
        self.authenticated = False
        self._auth_lock = None
        
    def authenticate(self):
        """Authenticate with Google Drive API using OAuth2 (same as stockSentinel.py)"""
        creds = None
        
        # Load existing token
        if os.path.exists(TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        
        # Refresh or get new credentials
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logger.error(f"Token refresh failed: {e}")
                    creds = None
            
            if not creds:
                if not os.path.exists(CREDENTIALS_FILE):
                    logger.error(f"Error: {CREDENTIALS_FILE} not found")
                    return False
                
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Save credentials for next time
            with open(TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())
        
        self.service = build('drive', 'v3', credentials=creds)
        self.authenticated = True
        logger.info("Google Drive authentication successful")
        return True
    
    async def upload_file(self, file_path, folder_id, file_name=None, max_retries=3):
        """Upload file to Google Drive with retry mechanism"""
        # Ensure authentication is complete before upload
        if not self.service or not self.authenticated:
            if not self.authenticate():
                return None
        
        # Retry mechanism for upload
        for attempt in range(max_retries):
            try:
                if not file_name:
                    file_name = os.path.basename(file_path)

                file_metadata = {
                    'name': file_name,
                    'parents': [folder_id]
                }

                media = MediaFileUpload(file_path, resumable=True)

                file = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id,name,webViewLink'
                ).execute()

                logger.info(f"File uploaded successfully: {file.get('name')}")
                return file

            except Exception as e:
                logger.error(f"Upload failed (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    # Wait before retry (exponential backoff)
                    await asyncio.sleep(2 ** attempt)
                    continue
                else:
                    logger.error(f"Upload failed after {max_retries} attempts: {e}")
                    return None

# Initialize Drive uploader
drive_uploader = DriveUploader()

def get_db_connection():
    """Get database connection"""
    return sqlite3.connect('dailydelights.db')

def save_cash_denomination(user_id, username, denominations_data):
    """Save cash denomination data to database"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        today = date.today()
        current_time = datetime.now().strftime("%H:%M:%S")

        # Calculate totals
        dollar_100_total = denominations_data.get('dollar_100_qty', 0) * 100.00
        dollar_50_total = denominations_data.get('dollar_50_qty', 0) * 50.00
        dollar_10_total = denominations_data.get('dollar_10_qty', 0) * 10.00
        dollar_5_total = denominations_data.get('dollar_5_qty', 0) * 5.00
        dollar_2_total = denominations_data.get('dollar_2_qty', 0) * 2.00
        dollar_1_total = denominations_data.get('dollar_1_qty', 0) * 1.00
        cent_50_total = denominations_data.get('cent_50_qty', 0) * 0.50
        cent_20_total = denominations_data.get('cent_20_qty', 0) * 0.20
        cent_10_total = denominations_data.get('cent_10_qty', 0) * 0.10
        cent_5_total = denominations_data.get('cent_5_qty', 0) * 0.05

        grand_total = (dollar_100_total + dollar_50_total + dollar_10_total +
                      dollar_5_total + dollar_2_total + dollar_1_total +
                      cent_50_total + cent_20_total + cent_10_total + cent_5_total)

        # Check if entry exists for today
        cursor.execute("SELECT id FROM cash_denomination_table WHERE entry_date = ?", (today,))
        existing = cursor.fetchone()

        if existing:
            # Update existing entry
            cursor.execute('''
                UPDATE cash_denomination_table SET
                    entry_time = ?,
                    dollar_100_qty = ?, dollar_50_qty = ?, dollar_10_qty = ?,
                    dollar_5_qty = ?, dollar_2_qty = ?, dollar_1_qty = ?,
                    cent_50_qty = ?, cent_20_qty = ?, cent_10_qty = ?, cent_5_qty = ?,
                    dollar_100_total = ?, dollar_50_total = ?, dollar_10_total = ?,
                    dollar_5_total = ?, dollar_2_total = ?, dollar_1_total = ?,
                    cent_50_total = ?, cent_20_total = ?, cent_10_total = ?, cent_5_total = ?,
                    grand_total = ?, telegram_user_id = ?, telegram_username = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE entry_date = ?
            ''', (
                current_time,
                denominations_data.get('dollar_100_qty', 0), denominations_data.get('dollar_50_qty', 0),
                denominations_data.get('dollar_10_qty', 0), denominations_data.get('dollar_5_qty', 0),
                denominations_data.get('dollar_2_qty', 0), denominations_data.get('dollar_1_qty', 0),
                denominations_data.get('cent_50_qty', 0), denominations_data.get('cent_20_qty', 0),
                denominations_data.get('cent_10_qty', 0), denominations_data.get('cent_5_qty', 0),
                dollar_100_total, dollar_50_total, dollar_10_total, dollar_5_total,
                dollar_2_total, dollar_1_total, cent_50_total, cent_20_total,
                cent_10_total, cent_5_total, grand_total, str(user_id), username, today
            ))
        else:
            # Insert new entry
            cursor.execute('''
                INSERT INTO cash_denomination_table (
                    entry_date, entry_time,
                    dollar_100_qty, dollar_50_qty, dollar_10_qty, dollar_5_qty,
                    dollar_2_qty, dollar_1_qty, cent_50_qty, cent_20_qty,
                    cent_10_qty, cent_5_qty, dollar_100_total, dollar_50_total,
                    dollar_10_total, dollar_5_total, dollar_2_total, dollar_1_total,
                    cent_50_total, cent_20_total, cent_10_total, cent_5_total,
                    grand_total, telegram_user_id, telegram_username
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                today, current_time,
                denominations_data.get('dollar_100_qty', 0), denominations_data.get('dollar_50_qty', 0),
                denominations_data.get('dollar_10_qty', 0), denominations_data.get('dollar_5_qty', 0),
                denominations_data.get('dollar_2_qty', 0), denominations_data.get('dollar_1_qty', 0),
                denominations_data.get('cent_50_qty', 0), denominations_data.get('cent_20_qty', 0),
                denominations_data.get('cent_10_qty', 0), denominations_data.get('cent_5_qty', 0),
                dollar_100_total, dollar_50_total, dollar_10_total, dollar_5_total,
                dollar_2_total, dollar_1_total, cent_50_total, cent_20_total,
                cent_10_total, cent_5_total, grand_total, str(user_id), username
            ))

        conn.commit()
        conn.close()
        return True, grand_total
    except Exception as e:
        logger.error(f"Error saving cash denomination: {e}")
        return False, 0

def format_denomination_summary(denominations_data):
    """Format denomination data for display"""
    summary = "💰 **Cash Denomination Summary**\n\n"

    total = 0
    for denom in DENOMINATIONS:
        key = f"{denom['type']}_{int(denom['value']*100) if denom['value'] < 1 else int(denom['value'])}_qty"
        qty = denominations_data.get(key, 0)
        if qty > 0:
            subtotal = qty * denom['value']
            total += subtotal
            summary += f"{denom['name']}: {qty} × ${denom['value']:.2f} = ${subtotal:.2f}\n"

    summary += f"\n**Grand Total: ${total:.2f}**"
    return summary, total

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    welcome_message = f"""
🤖 Welcome to Daily Delights Inventory Bot!

Available commands:
/upload_invoices - Upload invoice photos to Drive
/upload_dailybookclosing - Upload daily book closing photos to Drive
/cash_denomination - Enter daily cash denomination counts
/help - Show this help message

Just send the command and then share your photos or follow the prompts!
    """
    await update.message.reply_text(welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = """
📋 Available Commands:

/upload_invoices - Upload invoice photos
• Send this command first
• Then send photos one by one or multiple at once
• Photos will be uploaded to the invoices folder

/upload_dailybookclosing - Upload daily book closing photos
• Send this command first
• Then send photos one by one or multiple at once
• Photos will be uploaded to the daily book closing folder

/cash_denomination - Enter daily cash denomination counts
• Follow the interactive form to enter cash counts
• System will calculate totals automatically
• Data saved to cash management system

/help - Show this help message

Note: Make sure to send the command first, then follow the prompts!
    """
    await update.message.reply_text(help_text)

async def upload_invoices_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /upload_invoices command"""
    user_id = update.effective_user.id
    user_states[user_id] = {'mode': 'upload_invoices', 'folder_id': INVOICES_FOLDER_ID}

    await update.message.reply_text(
        "📄 Invoice Upload Mode Activated!\n\n"
        "Please send the invoice photos now. I'll upload them to the invoices folder.\n"
        "You can send multiple photos at once or one by one."
    )
    logger.info(f"User {user_id} activated invoice upload mode")

async def upload_dailybookclosing_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /upload_dailybookclosing command"""
    user_id = update.effective_user.id
    user_states[user_id] = {'mode': 'upload_dailybookclosing', 'folder_id': DAILY_BOOK_CLOSING_FOLDER_ID}

    await update.message.reply_text(
        "📊 Daily Book Closing Upload Mode Activated!\n\n"
        "Please send the daily book closing photos now. I'll upload them to the daily book closing folder.\n"
        "You can send multiple photos at once or one by one."
    )
    logger.info(f"User {user_id} activated daily book closing upload mode")

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo uploads with concurrency control"""
    user_id = update.effective_user.id

    # Check if user is in upload mode
    if user_id not in user_states:
        await update.message.reply_text(
            "❌ Please use /upload_invoices or /upload_dailybookclosing first to activate upload mode!"
        )
        return

    # Initialize upload lock for this user if not exists
    if user_id not in upload_locks:
        upload_locks[user_id] = asyncio.Lock()

    # Use lock to prevent concurrent uploads for same user
    async with upload_locks[user_id]:
        user_state = user_states[user_id]
        mode = user_state['mode']
        folder_id = user_state['folder_id']

        if update.message and update.message.photo:
            processing_msg = None
            temp_file_path = None

            try:
                # Send processing message
                processing_msg = await update.message.reply_text("⏳ Processing photo...")

                # Get the highest quality photo
                photo = update.message.photo[-1]
                file = await photo.get_file()

                # Create temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
                    temp_file_path = temp_file.name

                # Download photo to temporary file
                await file.download_to_drive(temp_file_path)
                logger.info(f"Photo downloaded successfully to {temp_file_path}")

                # Increment upload counter for this user
                upload_counters[user_id] = upload_counters.get(user_id, 0) + 1

                # Generate simple random filename
                filename = generate_random_filename(mode, upload_counters[user_id])
                logger.info(f"Generated filename: {filename}")

                # Set folder name for display
                if mode == 'upload_invoices':
                    folder_name = "Invoices"
                else:  # upload_dailybookclosing
                    folder_name = "Daily Book Closing"

                # Upload to Google Drive with async retry mechanism
                logger.info(f"Starting upload to Google Drive...")
                uploaded_file = await drive_uploader.upload_file(temp_file_path, folder_id, filename)

                if uploaded_file:
                    logger.info(f"Upload successful: {uploaded_file.get('name')}")

                    # Clean up temporary file
                    try:
                        os.unlink(temp_file_path)
                        logger.info("Temporary file cleaned up")
                    except Exception as cleanup_error:
                        logger.warning(f"Failed to cleanup temp file: {cleanup_error}")

                    # Update processing message with result
                    try:
                        success_message = f"✅ Photo uploaded successfully!\n\n📁 Folder: {folder_name}\n📄 File: {filename}\n\nSend more photos or use another command when done."

                        await processing_msg.edit_text(success_message)
                        logger.info("Success message sent to user")

                    except Exception as message_error:
                        logger.error(f"Failed to edit message: {message_error}")
                        # Try sending a new message instead
                        try:
                            await update.message.reply_text(success_message)
                        except Exception as reply_error:
                            logger.error(f"Failed to send reply message: {reply_error}")
                            # Send simple message without markdown
                            await update.message.reply_text(f"✅ Photo uploaded successfully! File: {filename}")
                else:
                    logger.error("Upload failed - no file returned")
                    await processing_msg.edit_text(
                        "❌ Failed to upload photo to Google Drive. Please check the bot configuration."
                    )

            except Exception as e:
                logger.error(f"Error processing photo: {e}", exc_info=True)

                # Clean up temp file if it exists
                if temp_file_path and os.path.exists(temp_file_path):
                    try:
                        os.unlink(temp_file_path)
                        logger.info("Cleaned up temp file after error")
                    except Exception as cleanup_error:
                        logger.warning(f"Failed to cleanup temp file after error: {cleanup_error}")

                # Try to update the processing message, or send a new one
                error_message = "❌ An error occurred while processing the photo. Please try again."
                try:
                    if processing_msg:
                        await processing_msg.edit_text(error_message)
                    else:
                        await update.message.reply_text(error_message)
                except Exception as msg_error:
                    logger.error(f"Failed to send error message: {msg_error}")
                    # Last resort - try a simple reply
                    try:
                        await update.message.reply_text("❌ Error occurred during processing.")
                    except:
                        pass  # Give up if even this fails

# Cash Denomination Conversation Handlers
async def cash_denomination_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start cash denomination entry process"""
    context.user_data['denominations'] = {}
    context.user_data['current_step'] = 0

    keyboard = [
        [InlineKeyboardButton("✅ Start Cash Count", callback_data="start_cash_count")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_cash_count")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    today = date.today().strftime("%B %d, %Y")
    message = f"""
💰 **Daily Cash Denomination Entry**

📅 Date: {today}

This will guide you through entering cash denomination counts for today's daily book closing.

Click 'Start Cash Count' to begin the process.
    """

    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    return DENOMINATION_START

async def cash_denomination_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle denomination input step by step"""
    query = update.callback_query
    await query.answer()

    if query.data == "cancel_cash_count":
        await query.edit_message_text("❌ Cash denomination entry cancelled.")
        return ConversationHandler.END

    if query.data == "start_cash_count":
        context.user_data['current_step'] = 0

    step = context.user_data.get('current_step', 0)

    if step >= len(DENOMINATIONS):
        # All denominations collected, show summary
        return await show_denomination_summary(update, context)

    denom = DENOMINATIONS[step]
    keyboard = [
        [InlineKeyboardButton("0", callback_data=f"qty_0"),
         InlineKeyboardButton("1", callback_data=f"qty_1"),
         InlineKeyboardButton("2", callback_data=f"qty_2")],
        [InlineKeyboardButton("3", callback_data=f"qty_3"),
         InlineKeyboardButton("4", callback_data=f"qty_4"),
         InlineKeyboardButton("5", callback_data=f"qty_5")],
        [InlineKeyboardButton("6", callback_data=f"qty_6"),
         InlineKeyboardButton("7", callback_data=f"qty_7"),
         InlineKeyboardButton("8", callback_data=f"qty_8")],
        [InlineKeyboardButton("9", callback_data=f"qty_9"),
         InlineKeyboardButton("10+", callback_data=f"qty_10plus")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_step") if step > 0 else InlineKeyboardButton("❌ Cancel", callback_data="cancel_cash_count")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    progress = f"({step + 1}/{len(DENOMINATIONS)})"
    message = f"""
💰 **Cash Denomination Entry** {progress}

**{denom['name']} (${denom['value']:.2f})**

How many {denom['name']} do you have?

Select quantity or choose "10+" for larger amounts:
    """

    if step == 0:
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

    return DENOMINATION_INPUT

async def handle_denomination_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quantity selection for each denomination"""
    query = update.callback_query
    await query.answer()

    if query.data == "cancel_cash_count":
        await query.edit_message_text("❌ Cash denomination entry cancelled.")
        return ConversationHandler.END

    if query.data == "back_step":
        context.user_data['current_step'] = max(0, context.user_data.get('current_step', 0) - 1)
        return await cash_denomination_input(update, context)

    if query.data.startswith("qty_"):
        step = context.user_data.get('current_step', 0)
        denom = DENOMINATIONS[step]

        if query.data == "qty_10plus":
            # Handle 10+ input via text message
            await query.edit_message_text(
                f"Please type the quantity for **{denom['name']}** (must be 10 or more):",
                parse_mode='Markdown'
            )
            context.user_data['awaiting_text_input'] = True
            context.user_data['current_denomination'] = denom
            return DENOMINATION_INPUT
        else:
            # Direct quantity selection
            qty = int(query.data.split('_')[1])
            key = f"{denom['type']}_{int(denom['value']*100) if denom['value'] < 1 else int(denom['value'])}_qty"
            context.user_data['denominations'][key] = qty

            context.user_data['current_step'] = step + 1
            return await cash_denomination_input(update, context)

    return DENOMINATION_INPUT

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text input for quantities 10+"""
    try:
        qty = int(update.message.text.strip())
        if qty < 10:
            await update.message.reply_text("❌ Please enter 10 or more. Use the buttons for quantities below 10.")
            return DENOMINATION_INPUT

        step = context.user_data.get('current_step', 0)
        denom = DENOMINATIONS[step]

        # Store the quantity
        key = f"{denom['type']}_{int(denom['value']*100) if denom['value'] < 1 else int(denom['value'])}_qty"
        context.user_data['denominations'][key] = qty

        # Move to next step
        context.user_data['current_step'] = step + 1
        context.user_data['awaiting_text_input'] = False

        # Create a fake query object to simulate button press
        class FakeQuery:
            def __init__(self):
                self.data = "continue_flow"
            async def answer(self):
                pass
            async def edit_message_text(self, text, reply_markup=None, parse_mode=None):
                await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)

        fake_update = type('obj', (object,), {'callback_query': FakeQuery()})()

        # Continue with next denomination or show summary
        return await cash_denomination_input(fake_update, context)

    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number (10 or more).")
        return DENOMINATION_INPUT

async def show_denomination_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show summary and confirmation"""
    denominations_data = context.user_data.get('denominations', {})
    summary, total = format_denomination_summary(denominations_data)

    keyboard = [
        [InlineKeyboardButton("✅ Confirm & Save", callback_data="confirm_save"),
         InlineKeyboardButton("✏️ Edit", callback_data="edit_denominations")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_cash_count")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = f"""
{summary}

Please review the information above. Choose an option:
    """

    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')

    return DENOMINATION_CONFIRM

async def confirm_denomination_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save denomination data and end conversation"""
    query = update.callback_query
    await query.answer()

    if query.data == "cancel_cash_count":
        await query.edit_message_text("❌ Cash denomination entry cancelled.")
        return ConversationHandler.END

    if query.data == "edit_denominations":
        context.user_data['current_step'] = 0
        return await cash_denomination_input(update, context)

    if query.data == "confirm_save":
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.first_name
        denominations_data = context.user_data.get('denominations', {})

        success, total = save_cash_denomination(user_id, username, denominations_data)

        if success:
            today = date.today().strftime("%B %d, %Y")
            await query.edit_message_text(
                f"✅ **Cash denomination saved successfully!**\n\n"
                f"📅 Date: {today}\n"
                f"💰 Total Amount: ${total:.2f}\n\n"
                f"Data has been saved to the cash management system.",
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                "❌ **Error saving cash denomination data.**\n\n"
                "Please try again later or contact support.",
                parse_mode='Markdown'
            )

        # Clear user data
        context.user_data.clear()
        return ConversationHandler.END

    return DENOMINATION_CONFIRM

# Fallback function for conversation
async def cash_denomination_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle conversation cancellation"""
    context.user_data.clear()
    await update.message.reply_text("❌ Cash denomination entry cancelled.")
    return ConversationHandler.END

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages"""
    # Check if we're awaiting text input for cash denomination
    if context.user_data.get('awaiting_text_input'):
        return await handle_text_input(update, context)

    if update.message and update.message.text:
        text = update.message.text.lower()

        # Check if bot is mentioned
        if BOTNAME.lower() in text:
            await update.message.reply_text(
                "👋 Hi! I'm the Daily Delights Inventory Bot.\n"
                "Use /help to see available commands."
            )
        elif any(keyword in text for keyword in ['upload', 'photo', 'image', 'picture']):
            await update.message.reply_text(
                "📸 To upload photos, please use:\n"
                "/upload_invoices - for invoice photos\n"
                "/upload_dailybookclosing - for daily book closing photos"
            )
        elif any(keyword in text for keyword in ['cash', 'denomination', 'money', 'count']):
            await update.message.reply_text(
                "💰 To enter cash denomination counts, use:\n"
                "/cash_denomination - for daily cash counts"
            )

def main():
    """Main function to run the bot"""
    try:
        # Build Application with default settings
        app = Application.builder().token(BOT_TOKEN).build()
        
        # Add command handlers
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("upload_invoices", upload_invoices_command))
        app.add_handler(CommandHandler("upload_dailybookclosing", upload_dailybookclosing_command))

        # Add cash denomination conversation handler
        cash_conv_handler = ConversationHandler(
            entry_points=[CommandHandler("cash_denomination", cash_denomination_start)],
            states={
                DENOMINATION_START: [CallbackQueryHandler(cash_denomination_input)],
                DENOMINATION_INPUT: [
                    CallbackQueryHandler(handle_denomination_quantity),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input)
                ],
                DENOMINATION_CONFIRM: [CallbackQueryHandler(confirm_denomination_save)]
            },
            fallbacks=[CommandHandler("cancel", cash_denomination_cancel)]
        )
        app.add_handler(cash_conv_handler)

        # Add message handlers
        app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
        
        logger.info("🤖 Bot is starting...")
        
        # Pre-authenticate Google Drive to avoid first-upload failures
        logger.info("🔐 Pre-authenticating Google Drive...")
        if drive_uploader.authenticate():
            logger.info("✅ Google Drive authentication successful")
        else:
            logger.warning("⚠️ Google Drive authentication failed - photo uploads will not work")
        
        print("🤖 Bot is running... Press Ctrl+C to stop.")
        app.run_polling()
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        print(f"❌ Error starting bot: {e}")

if __name__ == "__main__":
    main()