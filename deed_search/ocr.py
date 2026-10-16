import os
import time

import cv2
import numpy as np
import pdfplumber
from pdf2image import convert_from_path
from tqdm import tqdm
from winrt.windows.globalization import Language
from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap

# pywinrt imports
from winrt.windows.media.ocr import OcrEngine

DEFAULT_POPPLER = (
    r"C:\Users\pc\Downloads\poppler-26.09.0\Library\bin"
    if os.path.exists(r"C:\Users\pc\Downloads\poppler-26.09.0\Library\bin")
    else r"C:\Users\asus\Downloads\poppler-25.12.0\Library\bin"
)

# Global persistent OCR engine
_OCR_ENGINE = None


def _get_ocr_engine() -> OcrEngine:
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        _OCR_ENGINE = OcrEngine.try_create_from_language(Language("en-US"))
        if _OCR_ENGINE is None:
            raise RuntimeError(
                "Windows OCR engine not available for en-US.\n"
                "Run in PowerShell as Admin:\n"
                "Get-WindowsCapability -Online | Where-Object "
                "{ $_.Name -Like 'Language.OCR*en-US*' } | Add-WindowsCapability -Online"
            )
    return _OCR_ENGINE


# ─────────────────────────────────────────────
# PREPROCESSING
# ─────────────────────────────────────────────

def _preprocess(pil_img) -> np.ndarray:
    """Clean up blurry / bad-ink document image."""
    img = np.array(pil_img.convert("L"))

    h, w = img.shape
    if max(h, w) < 1500:
        scale = 1500 / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
    elif max(h, w) > 2000:
        scale = 2000 / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    if cv2.Laplacian(img, cv2.CV_64F).var() < 100.0:
        img = cv2.fastNlMeansDenoising(img, h=25, templateWindowSize=7, searchWindowSize=21)
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        img = cv2.filter2D(img, -1, kernel)
        img = cv2.adaptiveThreshold(
            img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10
        )
        kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        img = cv2.morphologyEx(img, cv2.MORPH_CLOSE, kernel_close)

    return img


# ─────────────────────────────────────────────
# WINDOWS OCR (SYNCHRONOUS & SAFE)
# ─────────────────────────────────────────────

def _run_ocr_sync(pil_or_np_img) -> str:
    """
    Run Windows OCR synchronously on the current thread.
    Avoids multi-threaded COM apartment access violations and event-loop churn.
    """
    try:
        if isinstance(pil_or_np_img, np.ndarray):
            cleaned = pil_or_np_img
        else:
            cleaned = _preprocess(pil_or_np_img)

        # Ensure BGRA
        if len(cleaned.shape) == 2:
            img_bgra = cv2.cvtColor(cleaned, cv2.COLOR_GRAY2BGRA)
        elif cleaned.shape[2] == 3:
            img_bgra = cv2.cvtColor(cleaned, cv2.COLOR_BGR2BGRA)
        else:
            img_bgra = cleaned

        h, w = img_bgra.shape[:2]
        pixel_bytes = bytearray(img_bgra.tobytes())

        bitmap = SoftwareBitmap.create_copy_from_buffer(
            pixel_bytes,
            BitmapPixelFormat.BGRA8,
            w, h
        )

        engine = _get_ocr_engine()
        result = engine.recognize_async(bitmap).get()
        return "\n".join(line.text for line in result.lines)
    except Exception as e:
        print(f"   [!] OCR error: {e}")
        return ""


async def _ocr_page_async(img: np.ndarray) -> str:
    """Async wrapper for backward compatibility."""
    return _run_ocr_sync(img)


def _convert_single_page(pdf_path: str, page_num: int, dpi: int, poppler_path: str, max_retries: int = 3):
    """Convert only one specific page with retries and DPI fallback."""
    for attempt in range(max_retries):
        try:
            current_dpi = dpi if attempt == 0 else 150
            imgs = convert_from_path(
                pdf_path,
                dpi=current_dpi,
                poppler_path=poppler_path,
                first_page=page_num,
                last_page=page_num,
            )
            if imgs:
                return imgs[0]
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1.0)
            else:
                print(f"   [!] Failed to convert page {page_num} after {max_retries} attempts: {e}")
    return None


def _process_ocr_page(args) -> tuple:
    """Helper for converting a single page image and running OCR."""
    page_num, pdf_path, dpi, poppler_path = args
    img = _convert_single_page(pdf_path, page_num, dpi, poppler_path)
    if img is None:
        return page_num, ""
    text = _run_ocr_sync(img)
    return page_num, text


def _run_ocr(args) -> tuple:
    """Sync wrapper for compatibility."""
    page_num, pil_img = args
    text = _run_ocr_sync(pil_img)
    return page_num, text


# ─────────────────────────────────────────────
# SMART HYBRID PIPELINE
# ─────────────────────────────────────────────

# Minimum characters to trust direct text extraction
_MIN_TEXT_LENGTH = 50


def _is_real_text(text: str) -> bool:
    """
    True if extracted text looks like real content,
    not garbage from a scanned image layer.
    """
    if not text or len(text.strip()) < _MIN_TEXT_LENGTH:
        return False

    printable = sum(c.isprintable() for c in text)
    ratio = printable / len(text)
    return ratio > 0.95


def pdf_to_text(
        pdf_path: str,
        dpi: int = 200,
        workers: int = 4,
        min_chars: int = 150,  # tune this to your needs
        poppler_path: str = DEFAULT_POPPLER
) -> str:
    results = {}
    ocr_pages = []
    direct_count = 0
    ocr_count = 0

    print("[*] Scanning pages for selectable text...")

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)

        for i, page in enumerate(
                tqdm(pdf.pages, total=total_pages, unit="page", desc="Scanning"),
                start=1
        ):
            text = page.extract_text() or ""
            char_count = len(text.strip())

            if char_count >= min_chars:
                results[i] = text.strip()
                direct_count += 1
                print(f"   Page {i}: {char_count} chars -> direct [OK]")
            else:
                ocr_pages.append(i)
                ocr_count += 1
                print(f"   Page {i}: {char_count} chars -> OCR [IMAGE]")

    print(f"\n[*] Scan complete:")
    print(f"   {direct_count} pages -> direct extraction")
    print(f"   {ocr_count} pages -> need OCR\n")

    if not ocr_pages:
        print("[*] No OCR needed -- all pages had selectable text!")
    else:
        # Step 2 & 3: Convert & OCR only needed pages sequentially
        print(f"[*] Converting and OCR'ing {ocr_count} image-only pages sequentially...")

        with tqdm(
            total=ocr_count,
            unit="page",
            desc="OCR Progress",
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} pages [{elapsed}<{remaining}, {rate_fmt}]"
        ) as pbar:
            for p in ocr_pages:
                try:
                    img = _convert_single_page(pdf_path, p, dpi, poppler_path)
                    if img is not None:
                        page_text = _run_ocr_sync(img)
                    else:
                        page_text = ""
                    results[p] = page_text
                    pbar.set_postfix_str(f"done: p.{p}")
                except Exception as e:
                    print(f"\n   [!] Error on page {p}: {e}")
                    results[p] = ""
                    pbar.set_postfix_str(f"err: p.{p}")
                pbar.update(1)

        print("\n[*] OCR complete")

    # Step 4: Assemble in correct page order
    all_pages_text = [
        f"--- Page {n} [{'direct' if n not in ocr_pages else 'ocr'}] ---\n{results[n]}"
        for n in sorted(results.keys())
    ]

    return "\n\n".join(all_pages_text)


if __name__ == "__main__":
    text = pdf_to_text("file.pdf")
    print(text)