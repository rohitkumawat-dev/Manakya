"""PDF export of an immutable, short-lived server-side review snapshot."""
import copy
import json
import secrets
import time
from collections import OrderedDict
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from threading import Lock
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

_CACHE = OrderedDict()
_LOCK = Lock()
TTL = 3600
BIS = 'https://standards.bis.gov.in/website/know-your-standards'
FONT = 'Helvetica'
for candidate in (
    Path(r'C:\Windows\Fonts\arial.ttf'),
    Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
):
    if candidate.exists():
        pdfmetrics.registerFont(TTFont('VelociaText', str(candidate)))
        FONT = 'VelociaText'
        break


def save_report(result, source_document=None):
    snapshot = copy.deepcopy(result)
    snapshot['generated_at'] = datetime.now(timezone.utc).isoformat()
    snapshot['source_document'] = source_document
    payload = json.dumps(snapshot, ensure_ascii=False).encode('utf-8')
    if len(payload) > 2 * 1024 * 1024:
        raise ValueError('This report is too large. Review fewer requirements.')
    token = secrets.token_urlsafe(32)
    with _LOCK:
        now = time.monotonic()
        for key in list(_CACHE):
            if _CACHE[key][0] <= now:
                del _CACHE[key]
        while len(_CACHE) >= 20:
            _CACHE.popitem(last=False)
        _CACHE[token] = (now + TTL, payload)
    return token


def get_report(token):
    with _LOCK:
        entry = _CACHE.get(token)
        if not entry or entry[0] <= time.monotonic():
            _CACHE.pop(token, None)
            raise KeyError(token)
        payload = entry[1]
    return build_pdf(json.loads(payload))


def build_pdf(report):
    stream = BytesIO()
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = FONT
    styles.add(ParagraphStyle('BodyTextV', fontName=FONT, fontSize=9,
                              leading=14, spaceAfter=7, splitLongWords=True))
    styles['Title'].fontSize = 23
    styles['Title'].leading = 29
    styles['Title'].textColor = colors.HexColor('#382566')
    styles['Heading2'].textColor = colors.HexColor('#382566')
    styles['Heading2'].spaceBefore = 16
    story = []
    missing_glyphs = set()
    glyphs = getattr(pdfmetrics.getFont(FONT).face, 'charToGlyph', None)

    def paragraph(value, style='BodyTextV'):
        text = str(value if value is not None else 'Not recorded')
        safe = []
        for char in text:
            if ord(char) < 32 and char not in '\n\t':
                continue
            if (glyphs is not None and ord(char) not in glyphs and not char.isspace()) or (glyphs is None and ord(char) > 255):
                missing_glyphs.add(ord(char))
                safe.append(f'[U+{ord(char):04X}]')
            else:
                safe.append(char)
        story.append(Paragraph(escape(''.join(safe)).replace('\n', '<br/>'), styles[style]))

    paragraph('VELOCIA', 'Title')
    paragraph('Tender standards recommendation report', 'Heading2')
    paragraph('Review snapshot: ' + report.get('generated_at', 'Not recorded'))
    paragraph('Source document: ' + (report.get('source_document') or 'Entered or pasted text'))
    paragraph('DRAFT - FOR TECHNICAL REVIEW', 'Heading3')
    paragraph('This report records candidate recommendations, not verified compliance or approved tender clauses. Latest editions, scope applicability and certification obligations require checking. Retrieval dates indicate collection time, not the date BIS revised a standard.')
    paragraph(report.get('limitations', ''))
    paragraph(f"Requirements reviewed: {len(report.get('items', []))}")

    for i, item in enumerate(report.get('items', []), 1):
        paragraph(f"Requirement {i} | {item.get('category', 'Unspecified').title()}", 'Heading2')
        paragraph(item.get('requirement', ''))
        checks = item.get('citation_checks') or []
        paragraph('Citation checks', 'Heading3')
        if not checks:
            paragraph('No supported citation detected. This does not establish whether any required reference is missing.')
        for check in checks:
            paragraph(f"{check.get('citation', '')}: {check.get('message', '')}")
            for evidence in check.get('evidence') or []:
                paragraph(f"Snapshot evidence: {evidence.get('standard_number', '')}; retrieved {evidence.get('retrieved_at') or 'unknown'}; replacement {evidence.get('replacement') or 'none recorded'}")
        result = item.get('recommendations') or {}
        paragraph(result.get('message', ''))
        if result.get('clarification_question'):
            paragraph('ACTION NEEDED: ' + result['clarification_question'], 'Heading3')
        candidates = result.get('standards') or []
        if not candidates:
            paragraph('No standard recommended for this item. Resolve the clarification or review BIS directly.')
        for j, standard in enumerate(candidates, 1):
            paragraph(f"Candidate {j}: {standard.get('is_number', '')}", 'Heading3')
            paragraph(standard.get('title', ''))
            paragraph('Selection basis: ' + (standard.get('reason') or 'No explanation recorded.'))
            paragraph('Record level: ' + (standard.get('record_level') or 'Not recorded'))
            paragraph('Role: ' + (standard.get('standard_role') or 'Unclassified'))
            paragraph('Category metadata: ' + ('Reviewed' if standard.get('category_verified') else 'Provisional'))
            paragraph('Data retrieved: ' + (standard.get('retrieved_at') or 'Not recorded'))
            paragraph('Reaffirmation recorded: ' + (standard.get('reaffirmation_date') or 'Not recorded'))
            paragraph('Amendment retrieval: ' + (standard.get('amendments_checked_at') or 'Not recorded'))
            paragraph('Scope: ' + (standard.get('scope_summary') or 'No scope summary available.'))
            paragraph('Scope evidence: ' + ('Marked reviewed in stored record; full applicability still requires checking.' if standard.get('scope_verified') else 'Not verified.'))
            for warning in (standard.get('revision_check') or {}).get('warnings') or []:
                paragraph('Review note: ' + warning)
            paragraph('Recorded amendments', 'Heading4')
            amendments = standard.get('amendments') or []
            if not amendments:
                paragraph('No amendment records available here; this does not establish that none exist.')
            for amendment in amendments:
                paragraph(f"{amendment.get('amendmentLabel') or 'Amendment'} | {amendment.get('amendmentYear') or 'Year not recorded'}")
            certification = standard.get('certification_check') or {}
            paragraph('Certification metadata: ' + (certification.get('bis_metadata_label') or 'Unknown'))
            paragraph(certification.get('message') or 'Certification applicability has not been verified.')
            for field, heading in [('related_standards', 'Related standards'), ('referenced_by', 'Referenced by')]:
                paragraph(heading, 'Heading4')
                refs = standard.get(field) or []
                if not refs:
                    paragraph('No records available in this result.')
                for ref in refs:
                    paragraph(f"{ref.get('is_number') or 'Identifier unavailable'} - {ref.get('title') or ''}")
                if refs:
                    paragraph('BIS-listed relationship only; necessity for this procurement and current editions are unverified.')
            paragraph('Source: BIS Know Your Standards catalogue. Search using the IS number above.')
            paragraph(BIS)
            story.append(Spacer(1, 8))
    if missing_glyphs:
        paragraph('Font note: unsupported characters are preserved as [U+XXXX] Unicode code points. Consult the original requirement for those characters.')

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor('#d5d0e0'))
        canvas.line(42, 37, A4[0] - 42, 37)
        canvas.setFont(FONT, 8)
        canvas.setFillColor(colors.HexColor('#665e72'))
        canvas.drawString(42, 24, 'Velocia | Draft for technical review')
        canvas.drawRightString(A4[0] - 42, 24, f'Page {doc.page}')
        canvas.restoreState()

    SimpleDocTemplate(stream, pagesize=A4, rightMargin=42, leftMargin=42,
                      topMargin=40, bottomMargin=52,
                      title='Velocia - Tender standards recommendation report',
                      author='Velocia').build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()
