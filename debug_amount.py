"""
debug_amount.py
---------------
Temporary debug script to see raw OCR output.
Helps us understand why amount extraction is failing.
Delete this file after debugging is done.
"""

import sys
sys.path.append('.')

from PIL import Image, ImageDraw, ImageFont
from src.ocr_engine import extract_text

# Step 1: Create the sample receipt image
img = Image.new('RGB', (600, 800), color='white')
draw = ImageDraw.Draw(img)
font = ImageFont.load_default()

lines = [
    '================================',
    '        QUICK MART STORE        ',
    '     123 Main Street, Delhi     ',
    '       Tel: 011-2345-6789       ',
    '================================',
    '',
    'Date: 25-Apr-2025   Time: 14:32',
    'Bill No: QM-2025-00847',
    '',
    '--------------------------------',
    'ITEM              QTY    AMOUNT',
    '--------------------------------',
    'Office Pens        2     Rs 120',
    'Notebook A4        3     Rs 180',
    'Stapler            1     Rs 250',
    'Printer Paper      2     Rs 440',
    'Tea Bags Pack      1     Rs  95',
    '--------------------------------',
    '',
    'Subtotal:             Rs 1,085',
    'GST (18%):            Rs   195',
    '                    ----------',
    'TOTAL:                Rs 1,280',
    '',
    'Payment: Credit Card',
    'Card: **** **** **** 4521',
    '',
    '================================',
    '   Thank you for your visit!    ',
    '================================',
]

y = 40
for line in lines:
    draw.text((30, y), line, fill='black', font=font)
    y += 24

img.save('data/receipts/test_receipt.jpg')
print('✅ Receipt image created')

# Step 2: Run OCR and print raw text
result = extract_text('data/receipts/test_receipt.jpg')

print('\n--- RAW OCR TEXT ---')
print(result['text'])

print('\n--- LINES CONTAINING NUMBERS ---')
for i, line in enumerate(result['text'].splitlines()):
    if any(char.isdigit() for char in line):
        print(f'  Line {i:02d}: {repr(line)}')