from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
import os
import tempfile
import logging
from datetime import datetime
from dotenv import load_dotenv

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

load_dotenv(override=True)
# Bot configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOTNAME = "@ddSentinel_Bot"

# Google Drive folder IDs
INVOICES_FOLDER_ID = "162d4TyRYwvGXdeVYkZTAY6AMpc50sJtf"
DAILY_BOOK_CLOSING_FOLDER_ID = "1sxtFv5mgGSafgWQ3UufW1D2c9f4xE7-Y"

# Google Drive OAuth2 credentials (same as stockSentinel.py)
SCOPES = ['https://www.googleapis.com/auth/drive']
CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.json'

# Global variable to store user states
user_states = {}

class DriveUploader:
    def __init__(self):
        self.service = None
        
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
        logger.info("Google Drive authentication successful")
        return True
    
    def upload_file(self, file_path, folder_id, file_name=None):
        """Upload file to Google Drive"""
        if not self.service:
            if not self.authenticate():
                return None
        
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
            logger.error(f"Upload failed: {e}")
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
    """Handle photo uploads"""
    user_id = update.effective_user.id
    
    # Check if user is in upload mode
    if user_id not in user_states:
        await update.message.reply_text(
            "❌ Please use /upload_invoices or /upload_dailybookclosing first to activate upload mode!"
        )
        return
    
    user_state = user_states[user_id]
    mode = user_state['mode']
    folder_id = user_state['folder_id']
    
    if update.message and update.message.photo:
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
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            if mode == 'upload_invoices':
                filename = f"invoice_{timestamp}_{file.file_id}.jpg"
                folder_name = "Invoices"
            else:  # upload_dailybookclosing
                filename = f"daily_closing_{timestamp}_{file.file_id}.jpg"
                folder_name = "Daily Book Closing"
            
            # Upload to Google Drive
            uploaded_file = drive_uploader.upload_file(temp_file_path, folder_id, filename)
            
            # Clean up temporary file
            os.unlink(temp_file_path)
            
            # Update processing message with result
            if uploaded_file:
                success_message = f"""
✅ **Photo uploaded successfully!**

📁 Folder: {folder_name}
📄 File: {filename}
🔗 [View on Drive]({uploaded_file.get('webViewLink', '#')})

Send more photos or use another command when done.
                """
                await processing_msg.edit_text(success_message, parse_mode='Markdown')
            else:
                await processing_msg.edit_text(
                    "❌ Failed to upload photo to Google Drive. Please check the bot configuration."
                )
                
        except Exception as e:
            logger.error(f"Error processing photo: {e}")
            await update.message.reply_text(
                "❌ An error occurred while processing the photo. Please try again."
            )

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
        
        # Test Google Drive authentication
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