#!/usr/bin/env python3
"""
PDF to Image Converter
Converts all PDFs in June_invoices to JPG images in June_invoices_images
"""

import os
from pdf2image import convert_from_path
from PIL import Image

# Directories
SOURCE_DIR = "Invoices/June_invoices"
OUTPUT_DIR = "Invoices/June_invoices_images"

def convert_pdfs_to_images():
    """Convert all PDFs to images"""

    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Get all PDF files
    pdf_files = [f for f in os.listdir(SOURCE_DIR) if f.endswith('.pdf')]
    pdf_files.sort()

    total = len(pdf_files)
    print("=" * 70)
    print("📄 PDF TO IMAGE CONVERTER")
    print("=" * 70)
    print(f"📂 Source: {SOURCE_DIR}")
    print(f"📁 Output: {OUTPUT_DIR}")
    print(f"📊 Total PDFs: {total}")
    print("=" * 70)

    converted = 0
    failed = 0

    for i, pdf_file in enumerate(pdf_files, 1):
        pdf_path = os.path.join(SOURCE_DIR, pdf_file)

        # Output filename (replace .pdf with .jpg)
        image_filename = pdf_file.replace('.pdf', '.jpg')
        image_path = os.path.join(OUTPUT_DIR, image_filename)

        print(f"\n[{i}/{total}] Converting: {pdf_file}")

        try:
            # Convert PDF to images (first page only, 150 DPI)
            images = convert_from_path(
                pdf_path,
                first_page=1,
                last_page=1,
                dpi=150,
                fmt='jpeg'
            )

            if images:
                # Save the first page
                images[0].save(image_path, 'JPEG', quality=85, optimize=True)

                # Get file size
                size_kb = os.path.getsize(image_path) / 1024

                print(f"✅ Saved: {image_filename} ({size_kb:.1f} KB)")
                converted += 1
            else:
                print(f"❌ No images extracted from {pdf_file}")
                failed += 1

        except Exception as e:
            print(f"❌ Error: {e}")
            failed += 1

    # Summary
    print("\n" + "=" * 70)
    print("🎉 CONVERSION COMPLETE!")
    print("=" * 70)
    print(f"✅ Converted: {converted}/{total}")
    print(f"❌ Failed: {failed}")
    print(f"📈 Success Rate: {(converted/total)*100:.1f}%")
    print(f"📁 Images saved to: {OUTPUT_DIR}")
    print("=" * 70)

if __name__ == "__main__":
    convert_pdfs_to_images()
