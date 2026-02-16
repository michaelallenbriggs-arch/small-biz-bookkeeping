from __future__ import annotations

import os
import re
from typing import Tuple, Optional, List, Dict

import cv2
import numpy as np

try:
    import pytesseract
except Exception:
    pytesseract = None

DEFAULT_LANG = "eng"

TESSERACT_CMD = os.getenv("TESSERACT_CMD")
if TESSERACT_CMD and pytesseract is not None:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

# Feature toggles (safe defaults)
OCR_ENABLE_RECTIFY = os.getenv("OCR_ENABLE_RECTIFY", "1").strip().lower() in {"1", "true", "yes", "y"}
OCR_ENABLE_PDF_TEXT = os.getenv("OCR_ENABLE_PDF_TEXT", "1").strip().lower() in {"1", "true", "yes", "y"}

# Safety caps
MAX_PDF_PAGES = int(os.getenv("OCR_MAX_PDF_PAGES", "10"))

# Receipt keywords used for heuristics (not strict requirements)
TOTALISH = ["sale total", "grand total", "total", "amount due", "balance due", "invoice total", "subtotal"]
TAXISH = ["sales tax", "tax", "vat", "gst", "hst"]

def _has_totalish_keywords(text: str) -> bool:
    if not text:
        return False
    lo = text.lower()
    return any(k in lo for k in (TOTALISH + TAXISH))


# -----------------------------------------------------------------------------
# Public API (matches your pipeline)
# -----------------------------------------------------------------------------

def extract_text(path: str, lang: str = DEFAULT_LANG) -> Tuple[str, str, str, float]:
    """
    Returns: (text, ocr_status, ocr_source, ocr_confidence)

    ocr_status:
      - "success"
      - "low_confidence"
      - "failed"

    ocr_source: describes what ran
    ocr_confidence: 0..100 (best-effort)
    """
    if pytesseract is None:
        return "", "failed", "no_pytesseract", 0.0

    try:
        if _is_pdf(path):
            # 1) Text-based PDF extraction first (best for digital invoices)
            if OCR_ENABLE_PDF_TEXT:
                pdf_text = _try_extract_pdf_text(path)
                if pdf_text and len(pdf_text.strip()) >= 40:
                    cleaned = _cleanup_text(pdf_text)
                    return cleaned, "success", "pdf_text", 95.0

            # 2) Render PDF -> images -> OCR each page
            pages = _pdf_to_images(path, max_pages=MAX_PDF_PAGES)
            if not pages:
                return "", "failed", "pdf_render_failed", 0.0

            texts: List[str] = []
            confs: List[float] = []
            srcs: List[str] = []

            for idx, bgr in enumerate(pages):
                t, c, s = _safe_ocr_image_pipeline(bgr, lang=lang, tag=f"page{idx+1}")
                if t.strip():
                    texts.append(t)
                    confs.append(c)
                    srcs.append(s)

            merged = "\n\n----- PAGE BREAK -----\n\n".join([_cleanup_text(t) for t in texts if t.strip()])
            if not merged.strip():
                return "", "failed", "pdf_ocr_empty", 0.0

            best_conf = float(max(confs) if confs else 0.0)
            status = _status_from_conf(best_conf)
            src = "pdf_ocr:" + ",".join(srcs[:3]) if srcs else "pdf_ocr"
            return merged, status, src, best_conf

        # Normal image
        bgr = _load_image(path)
        if bgr is None:
            return "", "failed", "image_load_failed", 0.0

        text, conf, src = _safe_ocr_image_pipeline(bgr, lang=lang, tag="img")
        cleaned = _cleanup_text(text)
        if not cleaned.strip():
            return "", "failed", src + "|empty", 0.0

        status = _status_from_conf(conf)
        return cleaned, status, src, float(conf)

    except Exception as e:
        # Never crash the API pipeline
        return "", "failed", f"fatal_exception:{type(e).__name__}", 0.0


# -----------------------------------------------------------------------------
# Safe wrapper (never throw)
# -----------------------------------------------------------------------------

def _safe_ocr_image_pipeline(bgr: np.ndarray, lang: str, tag: str) -> Tuple[str, float, str]:
    try:
        return _ocr_image_pipeline(bgr, lang=lang, tag=tag)
    except Exception as e:
        return "", 0.0, f"{tag}_pipeline_exception:{type(e).__name__}"


# -----------------------------------------------------------------------------
# Fast “CPA-grade” OCR pipeline (speed-first)
# -----------------------------------------------------------------------------

def _ocr_image_pipeline(bgr: np.ndarray, lang: str, tag: str) -> Tuple[str, float, str]:
    """
    Fast multi-pass OCR designed for your parser.

    Key speed principles:
      - Minimize # of Tesseract calls
      - Don't call image_to_data for confidence on every candidate
      - Prefer mixed-right-strip first (keeps TOTAL/TAX labels)
      - Only run expensive conditional passes when needed
    """
    src_parts: List[str] = []

    # Resize policy: avoid huge images + avoid always upscaling to 1800
    bgr = _resize_sane(bgr)

    # Optional safe rectification
    if OCR_ENABLE_RECTIFY:
        bgr2, did = _try_rectify_receipt(bgr)
        if did:
            bgr = bgr2
            src_parts.append("rectify")

    # Precompute a couple fast full-page variants once
    full_gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    full_norm = cv2.normalize(full_gray, None, 0, 255, cv2.NORM_MINMAX)
    full_clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(full_norm)
    full_denoise = cv2.fastNlMeansDenoising(full_clahe, h=10)

    # Variant A: denoise (good general)
    v_a = full_denoise
    # Variant B: sharpen (good for thermal receipts)
    blur = cv2.GaussianBlur(full_denoise, (0, 0), sigmaX=1.0)
    v_b = cv2.addWeighted(full_denoise, 1.6, blur, -0.6, 0)

    # --- A) Base OCR: 2 variants x 2 PSMs (FAST) ---
    base_text, base_score, base_src = _ocr_best_by_quality(
        variants=[("denoise", v_a), ("sharp", v_b)],
        psms=[6, 11],
        lang=lang,
        tag=f"{tag}_base",
        whitelist=None,
    )
    src_parts.append(f"base:{base_src}")

    merged_text = base_text or ""
    merged_conf = _score_to_conf(base_score)

    # --- D) Vendor TOP STRIP (cheap, keep it) ---
    v_text, v_score, v_src = _ocr_vendor_top_strip_fast(bgr, lang=lang, tag=tag)
    v_clean = _cleanup_text(v_text)
    if v_clean.strip():
        merged_text += "\n\n----- VENDOR PASS (TOP STRIP) -----\n" + v_clean
        merged_conf = max(merged_conf, _score_to_conf(v_score, cap=92.0))
        src_parts.append(f"vendor:{v_src}")

    # --- E) Totals RIGHT STRIP: run MIXED first (labels matter) ---
    rm_text, rm_score, rm_src = _ocr_right_strip_mixed_fast(bgr, lang=lang, tag=tag)
    rm_clean = _cleanup_text(rm_text)
    if rm_clean.strip():
        merged_text += "\n\n----- TOTALS PASS (RIGHT STRIP MIXED) -----\n" + rm_clean
        merged_conf = max(merged_conf, _score_to_conf(rm_score, bump=4.0, cap=94.0))
        src_parts.append(f"right_mixed:{rm_src}")

    # If right-mixed has numbers but lacks keywords, still okay (parser can do unlabeled fallbacks),
    # BUT if it has neither money nor keywords, run digits strip.
    need_right_digits = True
    if rm_clean.strip():
        has_money = _has_money_tokens(rm_clean)
        has_kw = _has_totalish_keywords(rm_clean)
        if has_money or has_kw:
            need_right_digits = False

    if need_right_digits:
        rd_text, rd_score, rd_src = _ocr_right_strip_digits_fast(bgr, lang=lang, tag=tag)
        rd_clean = _cleanup_text(rd_text)
        if rd_clean.strip():
            merged_text += "\n\n----- TOTALS PASS (RIGHT STRIP DIGITS) -----\n" + rd_clean
            merged_conf = max(merged_conf, _score_to_conf(rd_score, bump=6.0, cap=94.0))
            src_parts.append(f"right_digits:{rd_src}")

    # --- B) Digits full-page: ONLY if base looks like it mentions totals but has no money ---
    if _looks_like_totals_missing(base_text):
        d_text, d_score, d_src = _ocr_best_by_quality(
            variants=[("denoise", v_a), ("sharp", v_b)],
            psms=[6, 11],
            lang=lang,
            tag=f"{tag}_digits",
            whitelist="0123456789.$:/- ",
        )
        d_clean = _cleanup_text(d_text)
        if d_clean.strip():
            merged_text += "\n\n----- NUMERIC PASS (FULL) -----\n" + d_clean
            merged_conf = max(merged_conf, _score_to_conf(d_score, bump=8.0, cap=94.0))
            src_parts.append(f"digits:{d_src}")

    # --- C) Soft-text pass: ONLY if vendor letters look mangled ---
    if _looks_like_vendor_letters_missing(base_text):
        s_text, s_score, s_src = _ocr_softtext_full_fast(v_a, lang=lang, tag=tag)
        s_clean = _cleanup_text(s_text)
        if s_clean.strip():
            merged_text += "\n\n----- SOFT TEXT PASS (FULL) -----\n" + s_clean
            merged_conf = max(merged_conf, _score_to_conf(s_score, cap=90.0))
            src_parts.append(f"soft:{s_src}")

    return merged_text, float(_clamp(merged_conf, 0.0, 100.0)), "+".join(src_parts) if src_parts else f"{tag}_ocr"


# -----------------------------------------------------------------------------
# Heuristics
# -----------------------------------------------------------------------------

def _looks_like_totals_missing(text: str) -> bool:
    if not text:
        return True
    lo = text.lower()
    has_total_words = any(k in lo for k in (TOTALISH + TAXISH))
    if not has_total_words:
        return False
    has_money = _has_money_tokens(text)
    return not has_money


def _looks_like_vendor_letters_missing(text: str) -> bool:
    if not text:
        return True
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    top = " ".join(lines[:6]).strip()
    if len(top) < 10:
        return True
    alpha = sum(ch.isalpha() for ch in top)
    digit = sum(ch.isdigit() for ch in top)
    return (alpha < 6) or (digit > alpha * 2 and digit > 8)


def _has_money_tokens(text: str) -> bool:
    if not text:
        return False
    return bool(re.search(r"\b\d+\.\d{2}\b", text)) or bool(re.search(r"\b\d{3,6}\b", text))


# -----------------------------------------------------------------------------
# Fast OCR runners (single tesseract call per attempt)
# -----------------------------------------------------------------------------

def _ocr_best_by_quality(
    *,
    variants: List[Tuple[str, np.ndarray]],
    psms: List[int],
    lang: str,
    tag: str,
    whitelist: Optional[str],
) -> Tuple[str, float, str]:
    """
    Runs a small set of OCR attempts and chooses by a cheap quality score,
    avoiding expensive image_to_data calls per attempt.
    Returns (best_text, best_score_0_to_1, best_src)
    """
    best_text = ""
    best_score = -1.0
    best_src = f"{tag}_none"

    for vname, img in variants:
        if img is None:
            continue
        if len(img.shape) == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        for psm in psms:
            text = _tesseract_string(img, lang=lang, psm=psm, whitelist=whitelist)
            score = _text_quality_score(text)
            src = f"{tag}_{vname}_psm{psm}" + ("" if whitelist is None else "_wl")

            if score > best_score:
                best_text = text
                best_score = score
                best_src = src

            # Early exit: if we clearly got good OCR, stop wasting time
            if best_score >= 0.86:
                return best_text, best_score, best_src

    return best_text, max(best_score, 0.0), best_src


def _tesseract_string(img: np.ndarray, lang: str, psm: int, whitelist: Optional[str]) -> str:
    config = f"--oem 1 --psm {psm} -c preserve_interword_spaces=1 -c tessedit_do_invert=0"
    if whitelist:
        config += f" -c tessedit_char_whitelist={whitelist}"
    try:
        return pytesseract.image_to_string(img, lang=lang, config=config) or ""
    except Exception:
        return ""


def _text_quality_score(text: str) -> float:
    """
    Cheap quality score 0..1 based on:
      - length
      - alnum density
      - presence of receipt keywords
      - presence of money tokens
    """
    if not text:
        return 0.0

    t = text.strip()
    if not t:
        return 0.0

    # Normalize a bit for scoring only
    lo = t.lower()
    length = len(t)

    alpha = sum(ch.isalpha() for ch in t)
    digit = sum(ch.isdigit() for ch in t)
    alnum = alpha + digit

    # Basic density: avoid pure noise
    density = alnum / max(1, length)

    has_kw = 1.0 if _has_totalish_keywords(lo) else 0.0
    has_money = 1.0 if _has_money_tokens(t) else 0.0

    # Token count helps avoid "one-word" garbage
    tokens = len([x for x in re.split(r"\s+", t) if x])

    score = 0.0
    score += min(0.45, (length / 600.0) * 0.45)          # up to 0.45
    score += min(0.20, density * 0.20)                   # up to 0.20
    score += min(0.10, (tokens / 80.0) * 0.10)           # up to 0.10
    score += 0.15 * has_kw                               # up to 0.15
    score += 0.10 * has_money                            # up to 0.10

    return float(_clamp(score, 0.0, 1.0))


def _score_to_conf(score01: float, bump: float = 0.0, cap: float = 100.0) -> float:
    """
    Convert score 0..1 into 0..100 that roughly matches your existing thresholds.
    """
    conf = (float(score01) * 100.0) + float(bump or 0.0)
    return float(_clamp(conf, 0.0, cap))


# -----------------------------------------------------------------------------
# Fast vendor/top and totals/right passes
# -----------------------------------------------------------------------------

def _ocr_vendor_top_strip_fast(bgr: np.ndarray, lang: str, tag: str) -> Tuple[str, float, str]:
    top = _crop_top(bgr, frac=0.32)
    g = _ensure_gray(top)

    g = cv2.normalize(g, None, 0, 255, cv2.NORM_MINMAX)
    g = cv2.createCLAHE(clipLimit=2.3, tileGridSize=(8, 8)).apply(g)

    # light close to reconnect broken letters
    k2 = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    kh = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 1))
    g = cv2.morphologyEx(g, cv2.MORPH_CLOSE, k2, iterations=1)
    g = cv2.morphologyEx(g, cv2.MORPH_CLOSE, kh, iterations=1)

    # Only 2 PSMs, no huge variant fanout
    text, score, src = _ocr_best_by_quality(
        variants=[("vendor", g)],
        psms=[7, 6],
        lang=lang,
        tag=f"{tag}_vendor_top",
        whitelist=None,
    )
    return text, score, src


def _ocr_right_strip_mixed_fast(bgr: np.ndarray, lang: str, tag: str) -> Tuple[str, float, str]:
    right = _crop_right(bgr, frac=0.42)
    g = _ensure_gray(right)

    g = cv2.normalize(g, None, 0, 255, cv2.NORM_MINMAX)
    g = cv2.createCLAHE(clipLimit=2.3, tileGridSize=(8, 8)).apply(g)
    g = cv2.fastNlMeansDenoising(g, h=10)

    blur = cv2.GaussianBlur(g, (0, 0), sigmaX=1.0)
    sharp = cv2.addWeighted(g, 1.6, blur, -0.6, 0)

    text, score, src = _ocr_best_by_quality(
        variants=[("right_mixed", sharp)],
        psms=[6, 11],
        lang=lang,
        tag=f"{tag}_right_mixed",
        whitelist=None,
    )
    return text, score, src


def _ocr_right_strip_digits_fast(bgr: np.ndarray, lang: str, tag: str) -> Tuple[str, float, str]:
    right = _crop_right(bgr, frac=0.42)
    g = _ensure_gray(right)

    g = cv2.normalize(g, None, 0, 255, cv2.NORM_MINMAX)
    g = cv2.createCLAHE(clipLimit=2.3, tileGridSize=(8, 8)).apply(g)

    blur = cv2.GaussianBlur(g, (0, 0), sigmaX=1.0)
    sharp = cv2.addWeighted(g, 1.6, blur, -0.6, 0)

    text, score, src = _ocr_best_by_quality(
        variants=[("right_digits", sharp)],
        psms=[6, 7],
        lang=lang,
        tag=f"{tag}_right_digits",
        whitelist="0123456789.$:/- ",
    )
    return text, score, src


def _ocr_softtext_full_fast(gray_like: np.ndarray, lang: str, tag: str) -> Tuple[str, float, str]:
    g = gray_like.copy()
    g = cv2.GaussianBlur(g, (3, 3), 0)
    g = cv2.normalize(g, None, 0, 255, cv2.NORM_MINMAX)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    g = cv2.morphologyEx(g, cv2.MORPH_CLOSE, kernel, iterations=1)

    text, score, src = _ocr_best_by_quality(
        variants=[("soft_full", g)],
        psms=[6],
        lang=lang,
        tag=f"{tag}_soft_full",
        whitelist=None,
    )
    return text, score, src


# -----------------------------------------------------------------------------
# Optional receipt rectification (your original, kept)
# -----------------------------------------------------------------------------

def _try_rectify_receipt(bgr: np.ndarray) -> Tuple[np.ndarray, bool]:
    """
    Attempts to find a receipt contour and perspective warp it.
    Safe fallback: original.
    """
    try:
        img = bgr.copy()
        h, w = img.shape[:2]

        scale = 900.0 / max(h, w) if max(h, w) > 900 else 1.0
        small = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA) if scale != 1.0 else img

        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        edges = cv2.Canny(gray, 40, 140)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)

        cnts, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            return bgr, False

        cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:6]
        quad = None
        for c in cnts:
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.02 * peri, True)
            if len(approx) == 4:
                quad = approx.reshape(4, 2).astype(np.float32)
                break

        if quad is None:
            return bgr, False

        if scale != 1.0:
            quad = quad / scale

        quad = _order_points(quad)
        warped = _four_point_transform(img, quad)
        if warped is None or min(warped.shape[:2]) < 400:
            return bgr, False

        return warped, True

    except Exception:
        return bgr, False


def _order_points(pts: np.ndarray) -> np.ndarray:
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def _four_point_transform(image: np.ndarray, rect: np.ndarray) -> Optional[np.ndarray]:
    try:
        (tl, tr, br, bl) = rect
        widthA = np.linalg.norm(br - bl)
        widthB = np.linalg.norm(tr - tl)
        maxW = int(max(widthA, widthB))

        heightA = np.linalg.norm(tr - br)
        heightB = np.linalg.norm(tl - bl)
        maxH = int(max(heightA, heightB))

        if maxW <= 0 or maxH <= 0:
            return None

        dst = np.array(
            [[0, 0], [maxW - 1, 0], [maxW - 1, maxH - 1], [0, maxH - 1]],
            dtype=np.float32,
        )
        M = cv2.getPerspectiveTransform(rect, dst)
        return cv2.warpPerspective(
            image, M, (maxW, maxH),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE
        )
    except Exception:
        return None


# -----------------------------------------------------------------------------
# Resize policy (fixes your "always upscale to 1800" slowdown)
# -----------------------------------------------------------------------------

def _resize_sane(bgr: np.ndarray) -> np.ndarray:
    """
    Keep OCR input at a sane size:
      - downscale huge images (major speed win)
      - only lightly upscale very small images
    """
    h, w = bgr.shape[:2]
    m = max(h, w)

    # Downscale giant images (phones can produce 3000-5000px)
    if m > 2000:
        scale = 2000.0 / m
        return cv2.resize(bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    # Slight upscale if tiny
    if m < 1200:
        scale = 1400.0 / m
        return cv2.resize(bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

    return bgr


# -----------------------------------------------------------------------------
# Crops + grayscale
# -----------------------------------------------------------------------------

def _ensure_gray(img: np.ndarray) -> np.ndarray:
    if img is None:
        raise ValueError("image is None")
    if len(img.shape) == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return img


def _crop_top(bgr: np.ndarray, frac: float = 0.32) -> np.ndarray:
    h, w = bgr.shape[:2]
    y2 = max(1, int(h * frac))
    return bgr[0:y2, 0:w].copy()


def _crop_right(bgr: np.ndarray, frac: float = 0.42) -> np.ndarray:
    h, w = bgr.shape[:2]
    x1 = max(0, int(w * (1.0 - frac)))
    return bgr[0:h, x1:w].copy()


# -----------------------------------------------------------------------------
# PDF helpers (kept)
# -----------------------------------------------------------------------------

def _is_pdf(path: str) -> bool:
    return path.lower().endswith(".pdf")


def _try_extract_pdf_text(path: str) -> str:
    try:
        from pypdf import PdfReader  # pip install pypdf
    except Exception:
        return ""
    try:
        reader = PdfReader(path)
        out = []
        for page in reader.pages[:25]:
            t = page.extract_text() or ""
            if t.strip():
                out.append(t)
        return "\n\n".join(out)
    except Exception:
        return ""


def _pdf_to_images(path: str, max_pages: int = 10) -> List[np.ndarray]:
    try:
        from pdf2image import convert_from_path  # pip install pdf2image
    except Exception:
        return []
    try:
        pil_pages = convert_from_path(path, dpi=300, first_page=1, last_page=max_pages)
        bgr_pages = []
        for p in pil_pages:
            rgb = np.array(p.convert("RGB"))
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            bgr_pages.append(bgr)
        return bgr_pages
    except Exception:
        return []


# -----------------------------------------------------------------------------
# Misc helpers (kept)
# -----------------------------------------------------------------------------

def _load_image(path: str) -> Optional[np.ndarray]:
    try:
        return cv2.imread(path)
    except Exception:
        return None


def _cleanup_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[^\x09\x0A\x0D\x20-\x7E]", "", text)
    lines = []
    for ln in text.split("\n"):
        ln = re.sub(r"\s+", " ", ln).strip()
        if ln:
            lines.append(ln)
    return "\n".join(lines).strip()


def _status_from_conf(conf: float) -> str:
    conf = float(conf or 0.0)
    if conf >= 70:
        return "success"
    if conf >= 35:
        return "low_confidence"
    return "failed"


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))
