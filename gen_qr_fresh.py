#!/usr/bin/env python3
"""Generate QR code for RAB9 Wallet Report — fresh."""
import qrcode
from PIL import Image, ImageDraw, ImageFont
import os
from datetime import datetime

base_dir = os.path.dirname(os.path.abspath(__file__))
today = datetime.utcnow().strftime("%Y-%m-%d")

# Compact summary for QR
summary = (
    f"RAB9 Wallet Intel {today}\n"
    f"31K wallets | 8 KABAL | 42 suspicious\n"
    f"Top: GACHA $5.8M, CUM $1.6M, SOLANGELES $1M"
)

qr = qrcode.QRCode(
    version=None,
    error_correction=qrcode.constants.ERROR_CORRECT_M,
    box_size=5,
    border=2,
)
qr.add_data(summary)
qr.make(fit=True)

img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

# Add title + date
try:
    font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
    font_date = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
except (IOError, OSError):
    font_title = ImageFont.load_default()
    font_date = ImageFont.load_default()

title = "RAB9 WALLET INTEL"
date_str = today

# Extend canvas
final = Image.new("RGB", (img.width, img.height + 55), "white")
final.paste(img, (0, 0))

draw = ImageDraw.Draw(final)
tw = draw.textlength(title, font=font_title)
draw.text(((final.width - tw) / 2, img.height + 5), title, fill="black", font=font_title)

tw2 = draw.textlength(date_str, font=font_date)
draw.text(((final.width - tw2) / 2, img.height + 30), date_str, fill="black", font=font_date)

output_path = os.path.join(base_dir, "rab9_qr_wallet_report.png")
final.save(output_path)
print(f"QR saved: {output_path} ({os.path.getsize(output_path)} bytes, {final.width}x{final.height})")
