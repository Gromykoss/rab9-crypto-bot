#!/usr/bin/env python3
"""Generate QR code for RAB9 Wallet Report — fresh with real data."""
import qrcode, json, os
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

base_dir = os.path.dirname(os.path.abspath(__file__))
now = datetime.utcnow()
today = now.strftime("%Y-%m-%d")
time_str = now.strftime("%H:%M UTC")

kabal = json.load(open(os.path.join(base_dir, "data/kabal_library.json")))
kabal_count = sum(1 for v in kabal.values() if v.get("classification") == "kabal")
suspicious_count = sum(1 for v in kabal.values() if v.get("classification") == "suspicious")
total = len(kabal)
infra_count = total - kabal_count - suspicious_count

kabals = sorted(
    [(a, i) for a, i in kabal.items() if i.get("classification") == "kabal"],
    key=lambda x: x[1]["probability"], reverse=True
)
top_p = ", ".join(f"P={k[1]['probability']:.0%}" for k in kabals[:3])

analyses = []
ap = os.path.join(base_dir, "data/grok_analyses.jsonl")
if os.path.exists(ap):
    with open(ap) as f:
        for line in f:
            analyses.append(json.loads(line))
last = analyses[-1] if analyses else None

summary = (
    f"RAB9 Wallet Intel {today} {time_str}\n"
    f"{total} wallets: {kabal_count} KABAL, {suspicious_count} suspicious, {infra_count} infra\n"
    f"Top: {top_p}"
)
if last:
    summary += f"\nLast signal: {last['token']} {last['mc']}"

qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=5, border=2)
qr.add_data(summary)
qr.make(fit=True)
qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

try:
    font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
    font_line = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
except (IOError, OSError):
    font_title = ImageFont.load_default()
    font_line = ImageFont.load_default()

draw_dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))

line1 = f"RAB9 WALLET INTEL  •  {today} {time_str}"
line2 = f"{total} wallets  |  {kabal_count} KABAL (P>=80%)  |  {suspicious_count} SUSPICIOUS  |  {infra_count} INFRA"
line3 = f"Top: {top_p}"

# Measure text widths
tw1 = draw_dummy.textlength(line1, font=font_title)
tw2 = draw_dummy.textlength(line2, font=font_line)
tw3 = draw_dummy.textlength(line3, font=font_line)
max_text_w = max(tw1, tw2, tw3) + 30  # padding

# Canvas: wide enough for text, at least as wide as QR
canvas_w = max(qr_img.width, int(max_text_w))
text_h = 75
canvas_h = qr_img.height + text_h

final = Image.new("RGB", (canvas_w, canvas_h), "white")
# Center QR
qr_x = (canvas_w - qr_img.width) // 2
final.paste(qr_img, (qr_x, 0))

draw = ImageDraw.Draw(final)
draw.text(((canvas_w - tw1) / 2, qr_img.height + 8), line1, fill="black", font=font_title)
draw.text(((canvas_w - tw2) / 2, qr_img.height + 30), line2, fill="#333", font=font_line)
draw.text(((canvas_w - tw3) / 2, qr_img.height + 50), line3, fill="#555", font=font_line)

output_path = os.path.join(base_dir, "rab9_qr_wallet_report.png")
final.save(output_path)
print(f"QR saved: {output_path} ({os.path.getsize(output_path)} bytes, {final.width}x{final.height})")
print(f"Widths: title={tw1:.0f} line2={tw2:.0f} line3={tw3:.0f} canvas={canvas_w} — ALL FIT")
print(summary)
