"""Local extraction with bounded English OCR and no external API calls."""
import os
import shutil
import time
from io import BytesIO
from pathlib import Path
from threading import Lock
from zipfile import ZipFile, BadZipFile
import xml.etree.ElementTree as ET

from PIL import Image, ImageOps, UnidentifiedImageError
from pypdf import PdfReader

MAX_BYTES = 10 * 1024 * 1024
MAX_CHARS = 100000
MAX_PAGES = 50
MAX_OCR_PAGES = 8
MAX_PIXELS = 24000000
_OCR_LOCK = Lock()
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def read_image(image, deadline):
    import pytesseract
    command = os.getenv('TESSERACT_CMD') or shutil.which('tesseract')
    windows = Path(r'C:\Program Files\Tesseract-OCR\tesseract.exe')
    if not command and windows.exists():
        command = str(windows)
    if not command:
        raise ValueError('Install Tesseract OCR, or set TESSERACT_CMD in backend/.env.')
    remaining = deadline - time.monotonic()
    if remaining <= 0 or not _OCR_LOCK.acquire(timeout=max(0, min(2, remaining))):
        raise ValueError('OCR is busy or timed out. Retry with a shorter document.')
    try:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError('OCR time limit reached. Upload fewer scanned pages.')
        pytesseract.pytesseract.tesseract_cmd = command
        image = ImageOps.exif_transpose(image).convert('RGBA')
        background = Image.new('RGBA', image.size, 'white')
        background.alpha_composite(image)
        rgb = background.convert('RGB')
        rgb.thumbnail((2600, 3600))
        return pytesseract.image_to_string(
            rgb, lang='eng', config='--psm 3',
            timeout=max(0.1, min(20, remaining)),
        ).strip()
    except RuntimeError as error:
        raise ValueError('OCR timed out. Upload a clearer image or fewer scanned pages.') from error
    except pytesseract.TesseractError as error:
        raise ValueError('OCR failed. Check that the Tesseract English language data is installed.') from error
    finally:
        _OCR_LOCK.release()


def extract_document(filename, content):
    if not content or len(content) > MAX_BYTES:
        raise ValueError('Choose a nonempty file of up to 10 MB.')
    extension = Path(filename).suffix.lower()
    warnings, page_info = [], []
    deadline = time.monotonic() + 75
    method = 'text'
    try:
        if extension == '.txt':
            text = content.decode('utf-8-sig')
        elif extension == '.docx':
            with ZipFile(BytesIO(content)) as archive:
                if sum(x.file_size for x in archive.infolist()) > 40 * 1024 * 1024:
                    raise ValueError('Expanded DOCX exceeds 40 MB.')
                xml = archive.read('word/document.xml')
            if b'<!DOCTYPE' in xml or b'<!ENTITY' in xml:
                raise ValueError('Unsupported XML declarations in DOCX.')
            root = ET.fromstring(xml)
            ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
            text = '\n'.join(''.join(t.text or '' for t in p.iter(ns + 't'))
                             for p in root.iter(ns + 'p'))
            warnings.append('DOCX headers, footers and embedded images are not extracted. Check tables and reading order.')
        elif extension in {'.png', '.jpg', '.jpeg', '.webp'}:
            with Image.open(BytesIO(content)) as image:
                if image.width * image.height > MAX_PIXELS:
                    raise ValueError('Image exceeds 24 megapixels. Resize it before uploading.')
                if getattr(image, 'n_frames', 1) != 1:
                    raise ValueError('Upload a single-frame image.')
                text = read_image(image, deadline)
            method = 'ocr'
            page_info.append({'page': 1, 'method': method, 'characters': len(text)})
        elif extension == '.pdf':
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted:
                raise ValueError('Upload an unlocked PDF.')
            if len(reader.pages) > MAX_PAGES:
                raise ValueError('Upload at most 50 PDF pages.')
            pages, scanned, total = [], [], 0
            for i, page in enumerate(reader.pages):
                value = (page.extract_text() or '').strip()
                # Sparse text can be only a page number over a scanned page.
                if sum(c.isalnum() for c in value) < 30:
                    scanned.append(i)
                pages.append(value)
                total += len(value)
                if total > MAX_CHARS:
                    raise ValueError('Document exceeds 100,000 characters.')
            if len(scanned) > MAX_OCR_PAGES:
                raise ValueError('Upload at most 8 scanned pages at a time. No pages were silently skipped.')
            if scanned:
                import pypdfium2 as pdfium
                pdf = pdfium.PdfDocument(content)
                try:
                    for i in scanned:
                        page = pdf[i]
                        try:
                            width, height = page.get_size()
                            scale = min(2.5, 2600 / max(width, 1), 3600 / max(height, 1))
                            bitmap = page.render(scale=scale)
                            try:
                                image = bitmap.to_pil().copy()
                            finally:
                                bitmap.close()
                        finally:
                            page.close()
                        with image:
                            value = read_image(image, deadline)
                        total += len(value) - len(pages[i])
                        pages[i] = value or pages[i]
                        if total > MAX_CHARS:
                            raise ValueError('Document exceeds 100,000 characters.')
                finally:
                    pdf.close()
                method = 'mixed' if len(scanned) < len(pages) else 'ocr'
            for i, value in enumerate(pages):
                page_info.append({'page': i + 1, 'method': 'ocr' if i in scanned else 'text', 'characters': len(value)})
                if not value:
                    warnings.append(f'Page {i + 1}: no text detected; check the original page.')
            text = '\n\n'.join(pages)
            warnings.append('Check page order, tables and image-based text. Pages with substantial selectable text are not OCR-scanned.')
        else:
            raise ValueError('Supported: PDF, PNG, JPG, WEBP, DOCX and TXT.')
    except UnicodeDecodeError as error:
        raise ValueError('Save TXT documents as UTF-8.') from error
    except ValueError:
        raise
    except (BadZipFile, KeyError, ET.ParseError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        raise ValueError('The file is damaged, unsupported or too large to decode.') from error
    except Exception as error:
        raise ValueError('Could not extract this document. Check its format and the installed extraction dependencies.') from error
    text = text.strip()
    if not text:
        raise ValueError('No readable text found. Upload a clearer, upright document.')
    if len(text) > MAX_CHARS:
        raise ValueError('Document exceeds 100,000 characters. Upload a shorter section.')
    if method != 'text':
        warnings.append('English OCR was used. Verify IS numbers, years, units and symbols before analysis. Handwriting and non-English OCR are not supported in this version.')
    return {
        'filename': Path(filename.replace('\\', '/')).name,
        'text': text, 'character_count': len(text), 'warnings': warnings,
        'extraction_method': method, 'pages': page_info,
        'analysis_character_limit': 5000, 'requires_excerpt': len(text) > 5000,
    }
