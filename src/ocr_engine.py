"""
ocr_engine.py
-------------
Handles all OCR (Optical Character Recognition) operations.
Supports both image and PDF inputs.
Uses Tesseract (fast) with EasyOCR fallback (accurate).
"""

import os
import platform
import pytesseract
import easyocr
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
from pdf2image import convert_from_path

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

# Tell Python where Tesseract is installed (Windows only)
if platform.system() == "Windows":
    pytesseract.pytesseract.tesseract_cmd = (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    )

# EasyOCR reader — loads once, reused across calls
# ['en'] means English. Add more languages if needed e.g. ['en', 'hi']
_easyocr_reader = None  # Lazy load (only load when needed)


def _get_easyocr_reader():
    """Load EasyOCR reader once and reuse it (it's slow to load)."""
    global _easyocr_reader
    if _easyocr_reader is None:
        print("⏳ Loading EasyOCR model (first time only, ~10 seconds)...")
        _easyocr_reader = easyocr.Reader(['en'], gpu=False)
        print("✅ EasyOCR ready.")
    return _easyocr_reader


# ─────────────────────────────────────────────
# IMAGE PREPROCESSING
# ─────────────────────────────────────────────

def preprocess_image(image: Image.Image) -> Image.Image:
    """
    Clean up the image before OCR to improve accuracy.
    
    Steps:
    1. Convert to grayscale (removes color noise)
    2. Increase contrast (makes text stand out)
    3. Sharpen (makes blurry text crisper)
    4. Scale up small images (OCR works better on larger images)
    
    Args:
        image: PIL Image object
    
    Returns:
        Cleaned PIL Image object
    """
    # Step 1: Convert to grayscale
    image = image.convert("L")  # "L" = grayscale mode

    # Step 2: Increase contrast
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(2.0)  # 2.0 = double the contrast

    # Step 3: Sharpen the image
    image = image.filter(ImageFilter.SHARPEN)

    # Step 4: Scale up if image is too small (OCR struggles below 300px)
    width, height = image.size
    if width < 1000:
        scale_factor = 1000 / width
        new_size = (int(width * scale_factor), int(height * scale_factor))
        image = image.resize(new_size, Image.LANCZOS)

    return image


# ─────────────────────────────────────────────
# PDF HANDLING
# ─────────────────────────────────────────────

def pdf_to_images(pdf_path: str) -> list:
    """
    Convert each page of a PDF into an image.
    
    Why? OCR works on images, not PDFs directly.
    We convert PDF pages → images → run OCR on each.
    
    Args:
        pdf_path: Full path to the PDF file
    
    Returns:
        List of PIL Image objects (one per page)
    """
    print(f"📄 Converting PDF to images: {pdf_path}")
    
    # poppler_path needed on Windows — adjust if yours is different
    try:
        if platform.system() == "Windows":
            images = convert_from_path(
                pdf_path,
                dpi=300,  # Higher DPI = better quality
                poppler_path=r"C:\Program Files\poppler\Library\bin"
            )
        else:
            images = convert_from_path(pdf_path, dpi=300)
        
        print(f"✅ Converted {len(images)} page(s) from PDF.")
        return images

    except Exception as e:
        print(f"❌ PDF conversion failed: {e}")
        print("💡 Tip: Install poppler — see README for instructions.")
        return []


# ─────────────────────────────────────────────
# OCR ENGINES
# ─────────────────────────────────────────────

def run_tesseract(image: Image.Image) -> tuple[str, float]:
    """
    Extract text using Tesseract OCR.
    
    Returns:
        Tuple of (extracted_text, confidence_score)
        Confidence is 0-100. Above 60 = reliable.
    """
    try:
        # Get detailed data including confidence scores per word
        data = pytesseract.image_to_data(
            image,
            output_type=pytesseract.Output.DICT,
            config="--psm 6"  # PSM 6 = assume uniform block of text
        )

        # Calculate average confidence (ignore -1 values = spaces/blanks)
        confidences = [
            int(c) for c in data["conf"] if int(c) != -1
        ]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0

        # Extract just the text
        text = pytesseract.image_to_string(image, config="--psm 6")

        return text.strip(), avg_confidence

    except Exception as e:
        print(f"⚠️ Tesseract error: {e}")
        return "", 0.0


def run_easyocr(image: Image.Image) -> str:
    """
    Extract text using EasyOCR (slower but more accurate).
    Used as fallback when Tesseract confidence is low.
    
    Returns:
        Extracted text as a single string
    """
    try:
        reader = _get_easyocr_reader()

        # EasyOCR needs numpy array, not PIL image
        image_array = np.array(image)

        results = reader.readtext(image_array)

        # results = list of (bounding_box, text, confidence)
        # We join all detected text pieces
        text = "\n".join([result[1] for result in results])

        return text.strip()

    except Exception as e:
        print(f"⚠️ EasyOCR error: {e}")
        return ""


# ─────────────────────────────────────────────
# MAIN FUNCTION
# ─────────────────────────────────────────────

def extract_text(file_path: str) -> dict:
    """
    Main function — extracts text from any receipt image or PDF.
    
    Logic:
    1. Load the file (image or PDF)
    2. Preprocess (clean up image)
    3. Try Tesseract first
    4. If confidence < 60%, fall back to EasyOCR
    5. Return results with metadata
    
    Args:
        file_path: Path to receipt image or PDF
    
    Returns:
        Dictionary with:
        - text: extracted text
        - engine: which OCR engine was used
        - confidence: Tesseract confidence score (if used)
        - file: original file path
    """
    print(f"\n{'='*50}")
    print(f"📂 Processing: {file_path}")
    print(f"{'='*50}")

    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}", "text": ""}

    file_ext = os.path.splitext(file_path)[1].lower()

    # ── Load images ──────────────────────────
    if file_ext == ".pdf":
        images = pdf_to_images(file_path)
        if not images:
            return {"error": "Failed to convert PDF", "text": ""}
    elif file_ext in [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"]:
        images = [Image.open(file_path)]
    else:
        return {"error": f"Unsupported file type: {file_ext}", "text": ""}

    # ── Process each page ────────────────────
    all_text = []

    for page_num, image in enumerate(images, start=1):
        print(f"\n🔍 Processing page {page_num}/{len(images)}...")

        # Preprocess
        clean_image = preprocess_image(image)

        # Try Tesseract first
        tess_text, confidence = run_tesseract(clean_image)
        print(f"   Tesseract confidence: {confidence:.1f}%")

        if confidence >= 60 and len(tess_text) > 10:
            print(f"   ✅ Using Tesseract output.")
            all_text.append(tess_text)
            engine_used = "tesseract"
        else:
            print(f"   ⚠️ Low confidence — switching to EasyOCR...")
            easy_text = run_easyocr(clean_image)
            if easy_text:
                all_text.append(easy_text)
                engine_used = "easyocr"
            else:
                # Last resort: use tesseract anyway
                all_text.append(tess_text)
                engine_used = "tesseract (low confidence)"

    final_text = "\n\n--- PAGE BREAK ---\n\n".join(all_text)

    print(f"\n✅ Extraction complete using: {engine_used}")
    print(f"📝 Characters extracted: {len(final_text)}")

    return {
        "text": final_text,
        "engine": engine_used,
        "confidence": confidence,
        "file": file_path,
        "pages": len(images)
    }