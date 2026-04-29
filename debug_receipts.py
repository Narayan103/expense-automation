"""debug_receipts.py"""
import sys
sys.path.append('.')
from PIL import Image
from src.ocr_engine import preprocess_image
import pytesseract

path = "data/receipts/EVy7lnuXkAAiTr7.jpg"  # your hospital receipt

img = Image.open(path)
clean = preprocess_image(img)

# Force Tesseract and show output
text = pytesseract.image_to_string(clean, config="--psm 6")
print("=== TESSERACT OUTPUT ===")
print(text)