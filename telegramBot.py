from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
import os
import tempfile
import logging
import asyncio
from datetime import datetime

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
        self._auth_lock = asyncio.Lock()
        
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
        async with self._auth_lock:
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

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    welcome_message = f"""
🤖 Welcome to Daily Delights Inventory Bot!

Available commands:
/upload_invoices - Upload invoice photos to Drive
/upload_dailybookclosing - Upload daily book closing photos to Drive
/help - Show this help message

Just send the command and then share your photos!
    """
    await update.message.reply_text(welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = f"""
📋 **Available Commands:**

/upload_invoices - Upload invoice photos
• Send this command first
• Then send photos one by one or multiple at once
• Photos will be uploaded to the invoices folder

/upload_dailybookclosing - Upload daily book closing photos  
• Send this command first
• Then send photos one by one or multiple at once
• Photos will be uploaded to the daily book closing folder

/help - Show this help message

**Note:** Make sure to send the command first, then send your photos!
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def upload_invoices_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /upload_invoices command"""
    user_id = update.effective_user.id
    user_states[user_id] = {'mode': 'upload_invoices', 'folder_id': INVOICES_FOLDER_ID}
    
    await update.message.reply_text(
        "📄 **Invoice Upload Mode Activated!**\n\n"
        "Please send the invoice photos now. I'll upload them to the invoices folder.\n"
        "You can send multiple photos at once or one by one.",
        parse_mode='Markdown'
    )

async def upload_dailybookclosing_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /upload_dailybookclosing command"""
    user_id = update.effective_user.id
    user_states[user_id] = {'mode': 'upload_dailybookclosing', 'folder_id': DAILY_BOOK_CLOSING_FOLDER_ID}
    
    await update.message.reply_text(
        "📊 **Daily Book Closing Upload Mode Activated!**\n\n"
        "Please send the daily book closing photos now. I'll upload them to the daily book closing folder.\n"
        "You can send multiple photos at once or one by one.",
        parse_mode='Markdown'
    )

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
                    success_message = f"""✅ **Photo uploaded successfully!**

📁 Folder: {folder_name}
📄 File: {filename}
🔗 [View on Drive]({uploaded_file.get('webViewLink', '#')})

Send more photos or use another command when done."""
                    
                    await processing_msg.edit_text(success_message, parse_mode='Markdown')
                    logger.info("Success message sent to user")
                    
                except Exception as message_error:
                    logger.error(f"Failed to edit message: {message_error}")
                    # Try sending a new message instead
                    try:
                        await update.message.reply_text(success_message, parse_mode='Markdown')
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

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages"""
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