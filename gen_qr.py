#!/usr/bin/env python3
"""Generate QR code pointing to RAB9 dashboard with clean URL."""
import qrcode
from PIL import Image, ImageDraw, ImageFont
import os

# Simple QR — point to the local MSF HTTP endpoint (accessible info)
qr = qrcode.QRCode(
    version=None,
    error_correction=qrcode.constants.ERROR_CORRECT_H,
    box_size=4,
    border=2,
)

# A concise message that fits in a QR
base_dir = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(base_dir, "rab9_wallet_report_20260705.txt")

qr.add_data(f"RAB9 Report: {path}")
qr.make(fit=True)

img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

# Add title below
draw = ImageDraw.Draw(img)
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
except (IOError, OSError):
    font = ImageFont.load_default()

title = "RAB9 Wallet Analysis"
date = "2026-07-05"

# Create a taller canvas for text
final = Image.new("RGB", (img.width, img.height + 50), "white")
final.paste(img, (0, 0))

draw = ImageDraw.Draw(final)
try:
    font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
    font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
except (IOError, OSError):
    font_big = ImageFont.load_default()
    font_small = ImageFont.load_default()

tw = draw.textlength(title, font=font_big)
draw.text(((final.width - tw) / 2, img.height + 5), title, fill="black", font=font_big)

tw2 = draw.textlength(date, font=font_small)
draw.text(((final.width - tw2) / 2, img.height + 27), date, fill="black", font=font_small)

output_path = os.path.join(base_dir, "rab9_qr_report.png")
final.save(output_path)
print(f"QR code saved: {output_path}")
print(f"Size: {os.path.getsize(output_path)} bytes")
print(f"Dimensions: {final.width}x{final.height}")
