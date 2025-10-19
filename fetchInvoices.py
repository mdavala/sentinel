#!/usr/bin/env python3
"""
fetchInvoices.py - Monitor Daily Delights invoices folder for new images
Updated with image download and base64 encoding functionality
"""

import os
import time
import base64
import mimetypes
from datetime import datetime
from typing import Set, List, Dict
from io import BytesIO

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class StockSentinel:
    """Monitor Daily Delights invoices folder for new image uploads"""
    
    # Google Drive API configuration
    SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
    CREDENTIALS_FILE = 'credentials.json'
    TOKEN_FILE = 'token.json'
    
    # Your invoices folder ID (from debug output)
    INVOICES_FOLDER_ID = '162d4TyRYwvGXdeVYkZTAY6AMpc50sJtf'
    
    def __init__(self):
        self.service = None
        self.seen_images: Set[str] = set()  # Track seen image IDs
        
    def authenticate(self) -> bool:
        """Authenticate with Google Drive API"""
        creds = None
        
        # Load existing token
        if os.path.exists(self.TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(self.TOKEN_FILE, self.SCOPES)
        
        # Refresh or get new credentials
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    print(f"Token refresh failed: {e}")
                    creds = None
            
            if not creds:
                if not os.path.exists(self.CREDENTIALS_FILE):
                    print(f"Error: {self.CREDENTIALS_FILE} not found")
                    return False
                
                flow = InstalledAppFlow.from_client_secrets_file(self.CREDENTIALS_FILE, self.SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Save credentials for next time
            with open(self.TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())
        
        self.service = build('drive', 'v3', credentials=creds)
        print("Authentication successful")
        return True
    
    def download_image(self, file_id: str, file_name: str) -> str:
        """
        Download image from Google Drive and return base64 encoded data URL
        Returns: data:image/jpeg;base64,{base64_data}
        """
        if not self.service:
            if not self.authenticate():
                raise Exception("Authentication failed")
        
        try:
            print(f"📥 Downloading image: {file_name}")
            
            # Download file content
            request = self.service.files().get_media(fileId=file_id)
            file_content = request.execute()
            
            # Encode to base64
            base64_encoded = base64.b64encode(file_content).decode('utf-8')
            
            # Determine MIME type from file name
            mime_type, _ = mimetypes.guess_type(file_name)
            if not mime_type or not mime_type.startswith('image/'):
                mime_type = 'image/jpeg'  # Default fallback
            
            # Create data URL
            data_url = f"data:{mime_type};base64,{base64_encoded}"
            
            print(f"✅ Successfully downloaded and encoded: {file_name}")
            print(f"📊 Encoded size: {len(base64_encoded)} characters")
            
            return data_url
            
        except HttpError as e:
            error_msg = f"Google Drive API error downloading {file_name}: {e}"
            print(f"❌ {error_msg}")
            raise Exception(error_msg)
        except Exception as e:
            error_msg = f"Error downloading {file_name}: {e}"
            print(f"❌ {error_msg}")
            raise Exception(error_msg)
    
    def get_current_images(self) -> List[Dict]:
        """Get all current images in the invoices folder"""
        if not self.service:
            if not self.authenticate():
                return []
        
        try:
            # Query for all images in the invoices folder
            query = f"'{self.INVOICES_FOLDER_ID}' in parents and mimeType contains 'image/' and trashed=false"
            
            results = self.service.files().list(
                q=query,
                orderBy='modifiedTime desc',
                fields="files(id,name,mimeType,size,modifiedTime,createdTime,webViewLink,imageMediaMetadata)",
                supportsAllDrives=True,
                pageSize=100
            ).execute()
            
            return results.get('files', [])
            
        except Exception as e:
            print(f"Error fetching images: {e}")
            return []
    
    def get_image_with_content(self, file_id: str) -> Dict:
        """
        Get image metadata along with base64 encoded content
        Returns enhanced image dict with 'base64_data_url' field
        """
        # First get the image metadata
        images = self.get_current_images()
        image = None
        
        for img in images:
            if img['id'] == file_id:
                image = img
                break
        
        if not image:
            raise Exception(f"Image with ID {file_id} not found")
        
        try:
            # Download and encode the image
            base64_data_url = self.download_image(file_id, image['name'])
            
            # Add base64 data to image dict
            enhanced_image = image.copy()
            enhanced_image['base64_data_url'] = base64_data_url
            
            return enhanced_image
            
        except Exception as e:
            print(f"❌ Error getting image content for {image['name']}: {e}")
            raise
    
    def get_all_images_with_content(self) -> List[Dict]:
        """
        Get all images with their base64 encoded content
        WARNING: This downloads all images and can be memory intensive
        """
        images = self.get_current_images()
        enhanced_images = []
        
        print(f"📥 Downloading {len(images)} images...")
        
        for i, image in enumerate(images, 1):
            try:
                print(f"🔄 Processing {i}/{len(images)}: {image['name']}")
                
                # Download and encode
                base64_data_url = self.download_image(image['id'], image['name'])
                
                # Add to enhanced image
                enhanced_image = image.copy()
                enhanced_image['base64_data_url'] = base64_data_url
                enhanced_images.append(enhanced_image)
                
                # Brief pause between downloads to avoid rate limits
                time.sleep(0.5)
                
            except Exception as e:
                print(f"❌ Failed to download {image['name']}: {e}")
                # Add image without content (for error handling)
                enhanced_image = image.copy()
                enhanced_image['base64_data_url'] = None
                enhanced_image['download_error'] = str(e)
                enhanced_images.append(enhanced_image)
        
        print(f"✅ Downloaded {len([img for img in enhanced_images if img.get('base64_data_url')])} images successfully")
        return enhanced_images
    
    def check_for_new_images(self) -> List[Dict]:
        """Check for new images that we haven't seen before"""
        current_images = self.get_current_images()
        
        # Find images we haven't seen before
        new_images = []
        for image in current_images:
            if image['id'] not in self.seen_images:
                new_images.append(image)
                self.seen_images.add(image['id'])
        
        return new_images
    
    def check_for_new_images_with_content(self) -> List[Dict]:
        """
        Check for new images and download their content
        Returns new images with base64_data_url field
        """
        new_images = self.check_for_new_images()
        
        if not new_images:
            return []
        
        print(f"🚨 Found {len(new_images)} new images, downloading content...")
        
        enhanced_new_images = []
        for image in new_images:
            try:
                base64_data_url = self.download_image(image['id'], image['name'])
                enhanced_image = image.copy()
                enhanced_image['base64_data_url'] = base64_data_url
                enhanced_new_images.append(enhanced_image)
                
            except Exception as e:
                print(f"❌ Failed to download new image {image['name']}: {e}")
                enhanced_image = image.copy()
                enhanced_image['base64_data_url'] = None
                enhanced_image['download_error'] = str(e)
                enhanced_new_images.append(enhanced_image)
        
        return enhanced_new_images
    
    def print_image_details(self, image: Dict):
        """Print detailed information about a new invoice image"""
        print("\n" + "="*70)
        print("NEW INVOICE IMAGE DETECTED")
        print("="*70)
        
        # Basic file information
        print(f"File Name: {image['name']}")
        print(f"File ID: {image['id']}")
        print(f"MIME Type: {image['mimeType']}")
        print(f"File Size: {self.format_file_size(int(image.get('size', 0)))}")
        
        # Check if base64 content is available
        if 'base64_data_url' in image:
            if image['base64_data_url']:
                print(f"✅ Base64 Content: Available ({len(image['base64_data_url'])} chars)")
            else:
                print(f"❌ Base64 Content: Failed to download")
                if 'download_error' in image:
                    print(f"   Error: {image['download_error']}")
        
        # Timestamps
        print(f"Created: {self.format_timestamp(image.get('createdTime'))}")
        print(f"Modified: {self.format_timestamp(image.get('modifiedTime'))}")
        print(f"Detected At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Drive links
        print(f"View Link: {image.get('webViewLink', 'Not available')}")
        print(f"Direct Link: https://drive.google.com/file/d/{image['id']}/view")
        
        # Image metadata (if available)
        if 'imageMediaMetadata' in image:
            self.print_image_metadata(image['imageMediaMetadata'])
        
        # Invoice analysis
        self.print_invoice_analysis(image)
        
        print("="*70)
        print()
    
    def print_image_metadata(self, metadata: Dict):
        """Print image-specific metadata"""
        print(f"\nImage Properties:")
        
        # Dimensions
        width = metadata.get('width', 'Unknown')
        height = metadata.get('height', 'Unknown')
        print(f"  Dimensions: {width} x {height} pixels")
        
        # Camera info
        if 'cameraMake' in metadata:
            camera_make = metadata.get('cameraMake', '')
            camera_model = metadata.get('cameraModel', '')
            print(f"  Camera: {camera_make} {camera_model}".strip())
        
        # Photo timestamp
        if 'time' in metadata:
            print(f"  Photo Taken: {metadata['time']}")
        
        # Location (if available)
        if 'location' in metadata:
            location = metadata['location']
            if 'latitude' in location and 'longitude' in location:
                lat = location['latitude']
                lon = location['longitude']
                print(f"  GPS Location: {lat:.6f}, {lon:.6f}")
    
    def print_invoice_analysis(self, image: Dict):
        """Analyze if this looks like an invoice"""
        filename = image['name'].lower()
        
        print(f"\nInvoice Analysis:")
        
        # Check filename patterns
        invoice_keywords = ['invoice', 'bill', 'receipt', 'purchase', 'order', 'payment']
        likely_invoice = any(keyword in filename for keyword in invoice_keywords)
        print(f"  Likely Invoice: {likely_invoice}")
        
        # File analysis
        file_extension = os.path.splitext(image['name'])[1].upper()
        print(f"  File Type: {file_extension}")
        
        # OCR recommendation
        ocr_formats = ['.JPG', '.JPEG', '.PNG', '.TIFF', '.TIF']
        ocr_recommended = file_extension in ocr_formats
        print(f"  OCR Suitable: {ocr_recommended}")
        
        # Source analysis
        if 'whatsapp' in filename:
            print(f"  Source: WhatsApp (mobile upload)")
        elif 'scan' in filename:
            print(f"  Source: Scanner")
        elif 'photo' in filename:
            print(f"  Source: Camera/Photo")
        else:
            print(f"  Source: Unknown")
    
    def format_file_size(self, size_bytes: int) -> str:
        """Format file size in human readable format"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        return f"{size_bytes:.1f} {size_names[i]}"
    
    def format_timestamp(self, timestamp_str: str) -> str:
        """Format timestamp for display"""
        if not timestamp_str:
            return "Unknown"
        
        try:
            dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d %H:%M:%S UTC')
        except:
            return timestamp_str
    
    def start_monitoring(self, check_interval: int = 30):
        """Start continuous monitoring of the invoices folder"""
        print("Stock Sentinel - Daily Delights Invoice Monitor")
        print("="*50)
        print(f"Monitoring: My Drive > dailydelights > invoices")
        print(f"Folder ID: {self.INVOICES_FOLDER_ID}")
        print(f"Check Interval: {check_interval} seconds")
        print("Press Ctrl+C to stop monitoring")
        print()
        
        # Authenticate
        if not self.authenticate():
            print("Authentication failed. Exiting.")
            return
        
        # Initial check to populate seen images (avoids spam on first run)
        print("Initializing - checking existing images...")
        existing_images = self.get_current_images()
        for image in existing_images:
            self.seen_images.add(image['id'])
        print(f"Found {len(existing_images)} existing images in folder")
        print("Starting monitoring for NEW images...")
        print()
        
        try:
            while True:
                # Check for new images with content
                new_images = self.check_for_new_images_with_content()
                
                if new_images:
                    print(f"ALERT: {len(new_images)} new image(s) uploaded!")
                    for image in new_images:
                        self.print_image_details(image)
                else:
                    current_time = datetime.now().strftime('%H:%M:%S')
                    print(f"[{current_time}] No new images - monitoring...")
                
                time.sleep(check_interval)
                
        except KeyboardInterrupt:
            print("\nStock Sentinel monitoring stopped")
        except Exception as e:
            print(f"Monitoring error: {e}")
    
    def test_detection(self):
        """Test image detection without continuous monitoring"""
        print("Testing image detection...")
        
        if not self.authenticate():
            return
        
        images = self.get_current_images()
        
        if images:
            print(f"Found {len(images)} images in invoices folder:")
            for image in images[:3]:  # Show first 3
                self.print_image_details(image)
        else:
            print("No images found in invoices folder")
    
    def test_single_download(self, file_id: str = None):
        """Test downloading a single image"""
        if not self.authenticate():
            return
        
        images = self.get_current_images()
        if not images:
            print("No images found to test")
            return
        
        # Use provided file_id or first image
        test_image = None
        if file_id:
            test_image = next((img for img in images if img['id'] == file_id), None)
        else:
            test_image = images[0]
        
        if not test_image:
            print(f"Image with ID {file_id} not found")
            return
        
        print(f"🧪 Testing download of: {test_image['name']}")
        
        try:
            enhanced_image = self.get_image_with_content(test_image['id'])
            print("✅ Download test successful!")
            print(f"📊 Base64 length: {len(enhanced_image['base64_data_url'])}")
            
            # Test if it's valid base64 image data
            if enhanced_image['base64_data_url'].startswith('data:image/'):
                print("✅ Valid data URL format")
            else:
                print("❌ Invalid data URL format")
                
        except Exception as e:
            print(f"❌ Download test failed: {e}")
    
    def list_recent_uploads(self, hours_back: int = 24):
        """List images uploaded in the last N hours"""
        if not self.authenticate():
            return
        
        from datetime import timedelta
        cutoff_time = datetime.now() - timedelta(hours=hours_back)
        time_filter = cutoff_time.isoformat().replace('+00:00', 'Z')
        
        query = f"'{self.INVOICES_FOLDER_ID}' in parents and mimeType contains 'image/' and modifiedTime > '{time_filter}'"
        
        try:
            results = self.service.files().list(
                q=query,
                orderBy='modifiedTime desc',
                fields="files(id,name,mimeType,size,modifiedTime)",
                supportsAllDrives=True
            ).execute()
            
            files = results.get('files', [])
            print(f"Images uploaded in last {hours_back} hours: {len(files)}")
            
            for image in files:
                print(f"- {image['name']} ({self.format_timestamp(image['modifiedTime'])})")
            
        except Exception as e:
            print(f"Error: {e}")


def main():
    """Main entry point"""
    print("Stock Sentinel - Invoice Image Monitor")
    print("Choose mode:")
    print("1. Start continuous monitoring")
    print("2. Test detection (show existing images)")
    print("3. List recent uploads (last 24 hours)")
    print("4. Test single image download")
    print("5. Download all images (WARNING: Memory intensive)")
    
    try:
        choice = input("Enter choice (1-5): ").strip()
    except KeyboardInterrupt:
        print("\nExiting...")
        return
    
    sentinel = StockSentinel()
    
    try:
        if choice == "1":
            sentinel.start_monitoring(check_interval=30)
        elif choice == "2":
            sentinel.test_detection()
        elif choice == "3":
            sentinel.list_recent_uploads(hours_back=24)
        elif choice == "4":
            sentinel.test_single_download()
        elif choice == "5":
            print("⚠️  This will download ALL images. Continue? (y/n)")
            confirm = input().strip().lower()
            if confirm == 'y':
                enhanced_images = sentinel.get_all_images_with_content()
                print(f"✅ Downloaded {len(enhanced_images)} images")
            else:
                print("Cancelled.")
        else:
            print("Invalid choice. Starting continuous monitoring...")
            sentinel.start_monitoring(check_interval=30)
            
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()