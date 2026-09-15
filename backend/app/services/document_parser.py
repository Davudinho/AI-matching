"""
backend/app/services/document_parser.py — Universeller Dokument-Parser

Unterstützte Formate:
    .pdf   → PyMuPDF (native Textextraktion)
             Wenn leer: OCR via Gemini Vision (kein Tesseract nötig!)
    .docx  → python-docx (Paragraphen + Tabellen)
    .doc   → win32com (Windows, erfordert MS Word) → dann wie .docx
    .txt   → direktes Einlesen

Hybrid-OCR-Strategie:
    1. Erst native Extraktion versuchen (schnell, kostenlos)
    2. Wenn < OCR_THRESHOLD Zeichen → Gemini Vision OCR (langsamer, API-kosten)
    3. So werden normale PDFs nicht unnötig per OCR verarbeitet

Verwendung:
    from backend.app.services.document_parser import extract_text

    text = extract_text(Path("lebenslauf.pdf"))
    text = extract_text(Path("cv.docx"))
    text = extract_text(Path("resume.doc"))
    text = extract_text(Path("bewerbung.txt"))
"""

import logging
import tempfile
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Schwelle: Weniger als diese Anzahl Zeichen → OCR wird versucht
OCR_THRESHOLD = 100

# Maximale Seiten für OCR (begrenzt Kosten bei sehr langen Dokumenten)
OCR_MAX_PAGES = 15

# Auflösung für PDF-zu-Bild-Konvertierung (300 DPI = gute OCR-Qualität)
OCR_DPI = 300

# Alle unterstützten Datei-Endungen
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}


# ============================================================
# .txt
# ============================================================

def extract_text_from_txt(filepath: Path) -> str:
    """
    Liest eine .txt-Datei ein.
    Versucht zuerst UTF-8, fällt auf latin-1 zurück (typisch für ältere Windows-Dateien).
    """
    try:
        return filepath.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            text = filepath.read_text(encoding="latin-1")
            logger.info(f"  .txt: latin-1 Encoding verwendet für {filepath.name}")
            return text
        except Exception as e:
            raise ValueError(f"Konnte {filepath.name} nicht lesen: {e}") from e


# ============================================================
# .docx
# ============================================================

def extract_text_from_docx(filepath: Path) -> str:
    """
    Extrahiert Text aus einer .docx-Datei (python-docx).
    Liest Paragraphen UND Tabellen aus — wichtig, da viele CVs tabellarisch aufgebaut sind.
    """
    try:
        import docx
    except ImportError as e:
        raise ImportError("python-docx nicht installiert: pip install python-docx") from e

    doc = docx.Document(str(filepath))
    parts = []

    # Paragraphen (Haupttext, Überschriften, etc.)
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            parts.append(text)

    # Tabellen (z.B. zweispaltige CVs mit Stelle | Datum)
    for table in doc.tables:
        for row in table.rows:
            row_texts = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if row_texts:
                # Duplikate entfernen (python-docx dupliziert manchmal verbundene Zellen)
                seen = set()
                unique = []
                for t in row_texts:
                    if t not in seen:
                        seen.add(t)
                        unique.append(t)
                parts.append(" | ".join(unique))

    return "\n".join(parts)


# ============================================================
# .doc (altes Word 97–2003 Binärformat)
# ============================================================

def extract_text_from_doc(filepath: Path) -> str:
    """
    Extrahiert Text aus einer alten .doc-Datei (Word 97–2003 Binärformat).

    Strategien (in Reihenfolge):
    1. win32com (Windows + MS Word installiert) — beste Qualität, konvertiert zu .docx
    2. Fehlermeldung mit klarem Hinweis

    Warum kein antiword/textract?
    Auf Windows ist win32com zuverlässiger und erfordert keine extra Systeminstallation
    (nur `pip install pywin32`), sofern MS Word installiert ist.
    """
    # Strategie: win32com (Windows + MS Word)
    try:
        import win32com.client

        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False

        # Temporäre .docx-Datei als Zwischenschritt
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".docx")
        os.close(tmp_fd)

        try:
            abs_path = str(filepath.resolve())
            doc = word.Documents.Open(abs_path)
            # FileFormat 16 = wdFormatXMLDocument (.docx)
            doc.SaveAs2(tmp_path, FileFormat=16)
            doc.Close(False)

            # Als .docx einlesen
            text = extract_text_from_docx(Path(tmp_path))
            logger.info(
                f"  .doc konvertiert via win32com: {len(text)} Zeichen aus {filepath.name}"
            )
            return text

        finally:
            word.Quit()
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    except ImportError:
        logger.warning(
            f"  win32com nicht installiert — kann {filepath.name} nicht lesen. "
            "Installieren: pip install pywin32 (erfordert MS Word auf Windows)"
        )
    except Exception as e:
        logger.warning(f"  win32com Fehler bei {filepath.name}: {e}")

    raise ValueError(
        f"Konnte '{filepath.name}' (.doc-Format) nicht lesen.\n"
        "Lösung: Bitte die Datei als .docx oder .pdf einreichen.\n"
        "Oder auf Windows: 'pip install pywin32' installieren (MS Word benötigt)."
    )


# ============================================================
# .pdf — Nativ + Gemini Vision OCR Fallback
# ============================================================

def _extract_pdf_native(filepath: Path) -> str:
    """
    Extrahiert Text nativ aus einem PDF via PyMuPDF.
    Funktioniert nur bei textbasierten PDFs — nicht bei gescannten Bildern.
    """
    try:
        import fitz
    except ImportError as e:
        raise ImportError("PyMuPDF nicht installiert: pip install pymupdf") from e

    doc = fitz.open(str(filepath))
    pages_text = []

    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("text")
        if text.strip():
            pages_text.append(f"[Seite {page_num}]\n{text.strip()}")

    doc.close()
    return "\n\n".join(pages_text)


def _extract_pdf_ocr_gemini(filepath: Path) -> str:
    """
    OCR für gescannte PDFs via Gemini Vision API.

    Funktionsweise:
    1. Jede PDF-Seite wird mit PyMuPDF in ein 300-DPI-PNG-Bild gerendert
    2. Das Bild wird an Gemini 2.0 Flash gesendet
    3. Gemini erkennt und extrahiert den Text aus dem Bild

    Vorteile gegenüber Tesseract:
    - Keine Systeminstallation nötig (nur der API-Key, den wir schon haben)
    - Besser bei schlechten Scans, Handschrift und komplexen Layouts
    - Versteht tabellarische CV-Strukturen semantisch
    - Mehrsprachig ohne extra Sprachpakete
    """
    try:
        import fitz
    except ImportError as e:
        raise ImportError("PyMuPDF nicht installiert: pip install pymupdf") from e

    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError as e:
        raise ImportError("google-genai nicht installiert: pip install google-genai") from e

    try:
        try:
            from app.core.config import settings
        except ModuleNotFoundError:
            from backend.app.core.config import settings

        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY nicht gesetzt — OCR nicht möglich")

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        model_name = settings.GEMINI_MODEL  # Nutzt das konfigurierte Modell aus .env
    except Exception as e:
        raise ValueError(f"Gemini-Client konnte nicht initialisiert werden: {e}") from e

    doc = fitz.open(str(filepath))
    total_pages = len(doc)
    pages_to_ocr = min(total_pages, OCR_MAX_PAGES)

    if total_pages > OCR_MAX_PAGES:
        logger.warning(
            f"  {filepath.name}: {total_pages} Seiten — OCR auf erste {OCR_MAX_PAGES} begrenzt"
        )

    all_text_parts = []

    for page_num in range(pages_to_ocr):
        page = doc[page_num]

        # Seite als hochauflösendes PNG rendern (300 DPI)
        mat = fitz.Matrix(OCR_DPI / 72, OCR_DPI / 72)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")

        logger.info(
            f"  Gemini Vision OCR: Seite {page_num + 1}/{pages_to_ocr} "
            f"({len(img_bytes) // 1024} KB)..."
        )

        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[
                    genai_types.Part.from_bytes(
                        data=img_bytes,
                        mime_type="image/png",
                    ),
                    (
                        "Extract ALL text from this CV/resume page exactly as it appears. "
                        "Preserve the structure: name, contact details, work history, "
                        "education, skills, certifications. "
                        "Keep the original order and formatting as much as possible. "
                        "Return ONLY the extracted text — no commentary, no markdown. "
                        "If the page contains no readable text, write '[leere Seite]'."
                    ),
                ],
            )

            page_text = response.text.strip()
            if page_text and page_text not in ("[leere Seite]", "[blank page]", ""):
                all_text_parts.append(f"[Seite {page_num + 1}]\n{page_text}")

        except Exception as e:
            logger.warning(
                f"  Gemini Vision OCR Seite {page_num + 1} fehlgeschlagen: {e}"
            )

    doc.close()
    return "\n\n".join(all_text_parts)


def extract_text_from_pdf(filepath: Path) -> str:
    """
    Haupt-PDF-Extraktionsfunktion mit Hybrid-Strategie:

    1. Native Extraktion (PyMuPDF) — schnell & kostenlos
    2. Falls < OCR_THRESHOLD Zeichen → Gemini Vision OCR

    Dadurch werden normale textbasierte PDFs sofort verarbeitet
    und nur gescannte Dokumente gehen durch den (teureren) OCR-Pfad.
    """
    # Schritt 1: Nativ versuchen
    try:
        native_text = _extract_pdf_native(filepath)
    except Exception as e:
        logger.warning(f"  Native PDF-Extraktion fehlgeschlagen ({filepath.name}): {e}")
        native_text = ""

    char_count = len(native_text.strip())
    logger.info(f"  Native PDF-Extraktion: {char_count} Zeichen aus {filepath.name}")

    if char_count >= OCR_THRESHOLD:
        return native_text

    # Schritt 2: Gemini Vision OCR
    logger.info(
        f"  Nur {char_count} Zeichen nativ → Gemini Vision OCR wird gestartet..."
    )
    try:
        ocr_text = _extract_pdf_ocr_gemini(filepath)
        ocr_chars = len(ocr_text.strip())
        logger.info(f"  Gemini Vision OCR abgeschlossen: {ocr_chars} Zeichen")

        if ocr_chars > 0:
            return ocr_text
        elif native_text.strip():
            logger.warning(
                "  OCR ergab keinen Text — verwende unvollständige native Extraktion"
            )
            return native_text
        else:
            logger.error(
                f"  {filepath.name}: Weder native Extraktion noch OCR lieferten Text. "
                "Möglicherweise passwortgeschützt oder beschädigt."
            )
            return ""

    except Exception as e:
        logger.error(f"  Gemini Vision OCR fehlgeschlagen: {e}")
        if native_text.strip():
            logger.warning("  Verwende unvollständigen nativen Text als Fallback")
            return native_text
        return ""


# ============================================================
# Zentrale Routing-Funktion (öffentliche API)
# ============================================================

def extract_text(filepath: Path) -> str:
    """
    Universelle Text-Extraktion: wählt automatisch den richtigen Parser.

    Unterstützte Formate:
        .pdf   → PyMuPDF nativ + Gemini Vision OCR (Fallback für gescannte PDFs)
        .docx  → python-docx (Paragraphen + Tabellen)
        .doc   → win32com (Windows + MS Word erforderlich)
        .txt   → direktes Einlesen (UTF-8 oder latin-1)

    Args:
        filepath: Pfad zur Datei (Path-Objekt)

    Returns:
        Extrahierter Text als String. Leer bei unlesbaren Dateien.

    Raises:
        FileNotFoundError: Datei existiert nicht
        ValueError: Format nicht unterstützt oder Datei nicht lesbar
    """
    if not isinstance(filepath, Path):
        filepath = Path(filepath)

    if not filepath.exists():
        raise FileNotFoundError(f"Datei nicht gefunden: {filepath}")

    suffix = filepath.suffix.lower()

    if suffix == ".txt":
        return extract_text_from_txt(filepath)
    elif suffix == ".docx":
        return extract_text_from_docx(filepath)
    elif suffix == ".doc":
        return extract_text_from_doc(filepath)
    elif suffix == ".pdf":
        return extract_text_from_pdf(filepath)
    else:
        raise ValueError(
            f"Format nicht unterstützt: '{suffix}' ({filepath.name})\n"
            f"Unterstützte Formate: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )


def get_supported_glob_patterns() -> list[str]:
    """Gibt Glob-Patterns für alle unterstützten Formate zurück."""
    return [f"*{ext}" for ext in sorted(SUPPORTED_EXTENSIONS)]
