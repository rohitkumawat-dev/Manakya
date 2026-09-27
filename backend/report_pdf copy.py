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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, LongTable, PageBreak, KeepTogether

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


BOLD = 'Helvetica-Bold'
for candidate in (Path(r'C:\Windows\Fonts\arialbd.ttf'), Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')):
    if candidate.exists():
        pdfmetrics.registerFont(TTFont('SpecGyanBold', str(candidate)))
        BOLD = 'SpecGyanBold'
        break
pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=BOLD, italic=FONT, boldItalic=BOLD)


def build_pdf(report):
    """Render the supplied snapshot; no standard facts are added by the template."""
    stream = BytesIO()
    ink = colors.HexColor('#111111')
    purple = colors.HexColor('#e5d4f2')
    pale = colors.HexColor('#f6f1fa')
    yellow = colors.HexColor('#f2efb7')
    width = A4[0] - 84
    styles = {
        'body': ParagraphStyle('body', fontName=FONT, fontSize=8, leading=12, textColor=ink, spaceAfter=3),
        'small': ParagraphStyle('small', fontName=FONT, fontSize=7, leading=10, textColor=ink),
        'label': ParagraphStyle('label', fontName=BOLD, fontSize=6.5, leading=10, textColor=ink),
        'heading': ParagraphStyle('heading', fontName=BOLD, fontSize=15, leading=20, textColor=ink, spaceAfter=9),
        'code': ParagraphStyle('code', fontName=BOLD, fontSize=13, leading=18, textColor=ink, spaceAfter=7),
        'title': ParagraphStyle('title', fontName=BOLD, fontSize=23, leading=28, textColor=ink, spaceAfter=10),
    }
    glyphs = getattr(pdfmetrics.getFont(FONT).face, 'charToGlyph', None)
    def p(value, style='body'):
        text = str(value if value is not None and value != '' else 'Not recorded')
        text = ''.join(ch for ch in text if ord(ch) >= 32 or ch in '\n\t')
        if glyphs is not None:
            text = ''.join(ch if ch.isspace() or ord(ch) in glyphs else f'[U+{ord(ch):04X}]' for ch in text)
        return Paragraph(escape(text).replace('\n', '<br/>'), styles[style])
    def table(rows, widths, header=False, fills=None):
        t = LongTable(rows, colWidths=widths, repeatRows=1 if header else 0, hAlign='LEFT', splitByRow=1, splitInRow=1)
        commands = [('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.55,ink),
                    ('LEFTPADDING',(0,0),(-1,-1),9),('RIGHTPADDING',(0,0),(-1,-1),9),
                    ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]
        if header: commands.append(('BACKGROUND',(0,0),(-1,0),purple))
        for first,last,color in fills or []: commands.append(('BACKGROUND',first,last,color))
        t.setStyle(TableStyle(commands))
        return t
    def cell(label,value): return [p(label,'label'),Spacer(1,3),p(value)]
    def choose(*values): return next((v for v in values if v is not None and v != ''), 'Not recorded')
    def date(value):
        if not value: return 'Not recorded'
        try: return datetime.fromisoformat(str(value).replace('Z','+00:00')).strftime('%d %b %Y')
        except ValueError: return str(value)
    def reason(s): return choose(s.get('why_recommended'),s.get('reason'))
    def scope(s): return choose(s.get('scope_summary'),(s.get('manual_details') or {}).get('scope_text'))
    def certification(s): return choose((s.get('manual_details') or {}).get('certification_as_shown'),(s.get('certification_check') or {}).get('bis_metadata_label'),s.get('certification_label_raw'))
    items = report.get('items') or []
    story = [p('Tender standards\nrecommendation report.','title'),p('A structured review of the submitted procurement requirement and its related Indian Standards.'),Spacer(1,14)]
    first = items[0] if items else {}
    summary = [[cell('PROJECT','SpecGyan'),cell('REQUIREMENT',first.get('requirement') if len(items)==1 else f'{len(items)} procurement requirements'),cell('DOMAIN',str(first.get('category','Unspecified')).title() if len(items)==1 else 'Multiple categories')],
               [cell('SOURCE',report.get('source_document')),cell('REQUIREMENTS REVIEWED',len(items)),cell('REVIEW SNAPSHOT',date(report.get('generated_at')))]]
    story += [table(summary,[width*.28,width*.43,width*.29],fills=[((0,0),(-1,0),purple)]),Spacer(1,16)]
    note = 'This report records candidate recommendations, not verified compliance or approved tender clauses. Latest editions, scope applicability and certification obligations require checking.'
    story += [table([[cell('DRAFT - FOR TECHNICAL REVIEW',note)]],[width],fills=[((0,0),(-1,-1),yellow)]),Spacer(1,18)]
    for i,item in enumerate(items,1):
        result=item.get('recommendations') or {}
        standards=result.get('standards') or []
        if i>1: story += [PageBreak(),p(f'Requirement {i:02d}','heading')]
        left=cell(f'{i:02d} REQUIREMENT',item.get('requirement'))+[Spacer(1,6),p('Tender category: '+str(item.get('category','Unspecified')).title(),'small')]
        if standards:
            s=standards[0]
            right=[p('TOP RECOMMENDED STANDARD','label'),Spacer(1,8),p(s.get('is_number'),'code'),p(s.get('title')),Spacer(1,6),p('Why: '+str(reason(s)))]
        else: right=cell('REVIEW OUTCOME',choose(result.get('clarification_question'),result.get('message'),'No supported standard recommendation.'))
        story += [table([[left,right]],[width*.45,width*.55],fills=[((0,0),(0,0),purple)]),Spacer(1,16),p('Citation & edition check','heading')]
        checks=item.get('citation_checks') or []
        for check in checks: story.append(p(str(check.get('citation',''))+': '+str(check.get('message',''))))
        if not checks: story.append(p('No supported citation detected in this requirement.'))
        for check in checks:
            for evidence in check.get('evidence') or []: story.append(p('Snapshot evidence: '+str(evidence.get('standard_number',''))+'; retrieved '+str(evidence.get('retrieved_at') or 'Not recorded'),'small'))
        if standards:
            s=standards[0]
            story += [Spacer(1,8),table([[cell('RECORD LEVEL',s.get('record_level')),cell('ROLE',s.get('standard_role')),cell('CATEGORY METADATA','Reviewed' if s.get('category_verified') else 'Provisional'),cell('CERTIFICATION',certification(s))]],[width/4]*4,fills=[((0,0),(-1,-1),pale)]),Spacer(1,12),p('Scope / coverage: '+str(scope(s)))]
        if result.get('clarification_question') and standards: story.append(p(result['clarification_question']))
        for rank,s in enumerate(standards,1):
            m=s.get('manual_details') or {}
            story += [PageBreak(),p('Recommendation detail','heading'),p(f'Candidate {rank} | '+str(s.get('is_number',''))),Spacer(1,8)]
            amendments=s.get('amendments') or []
            amendment_text='\n'.join(str(a.get('amendmentLabel') or 'Amendment')+' | '+str(a.get('amendmentYear') or 'Year not recorded') for a in amendments)
            fields=[('IS code',s.get('is_number')),('Title',s.get('title')),('Why recommended',reason(s)),('Record level',s.get('record_level')),('Role',s.get('standard_role')),('Category metadata','Reviewed' if s.get('category_verified') else 'Provisional'),('Data retrieved',s.get('retrieved_at')),('Source checked',choose(s.get('scope_checked_on'),m.get('checked_on'))),('Reaffirmation recorded',choose(m.get('reaffirmation_year_as_shown'),s.get('reaffirmation_date'))),('Amendment retrieval',s.get('amendments_checked_at')),('Recorded amendments',amendment_text or choose(m.get('amendment_count_as_shown'),s.get('amendment_count_raw'))),('Certification metadata',certification(s))]
            story += [table([[p('STANDARD','label'),p('DETAIL','label')]]+[[p(label,'label'),p(value)] for label,value in fields],[width*.28,width*.72],header=True),Spacer(1,17)]
            verification='Confirm edition, full scope applicability and certification obligations before procurement use.'
            story += [table([[cell('COVERAGE SUMMARY',scope(s)),cell('VERIFICATION NOTE',verification)]],[width/2]*2,fills=[((0,0),(0,0),pale)]),Spacer(1,16),p('Recommendation logic','heading')]
            logic=[('01','Tender requirement',item.get('requirement')),('02','Selection basis',reason(s)),('03','Review',verification)]
            story += [table([[p(number,'label'),cell(label,value)] for number,label,value in logic],[30,width-30]),Spacer(1,14)]
            for warning in (s.get('revision_check') or {}).get('warnings') or []: story.append(p('Review note: '+str(warning)))
            if (s.get('certification_check') or {}).get('message'): story.append(p(s['certification_check']['message']))
            story += [p('Source note','heading'),p(choose(s.get('scope_source_url'),BIS),'small')]
            refs=[]
            for key,label in [('related_standards','Related'),('referenced_by','Referenced by')]:
                for ref in s.get(key) or []:
                    refs.append((choose(ref.get('is_number'),ref.get('standardNumber')),choose(ref.get('title'),ref.get('standardName')),label))
            if refs:
                story += [PageBreak(),p('Related Indian Standards','heading'),p(f'{len(refs)} relationships for '+str(s.get('is_number',''))+'. Related standards and referenced-by records are listed separately from recommendations.'),Spacer(1,10)]
                counts=[[cell('TOTAL LISTED',len(refs)),cell('RELATED',sum(r[2]=='Related' for r in refs)),cell('REFERENCED BY',sum(r[2]=='Referenced by' for r in refs))]]
                story += [table(counts,[width/3]*3,fills=[((0,0),(-1,-1),pale)]),Spacer(1,13)]
                rows=[[p('#','label'),p('IS CODE','label'),p('STANDARD / TITLE','label'),p('RELATIONSHIP','label')]]
                rows += [[p(n,'small'),p(code,'small'),p(title,'small'),p(label,'small')] for n,(code,title,label) in enumerate(refs,1)]
                story += [table(rows,[25,105,width-206,76],header=True),Spacer(1,12),p('BIS-listed relationships only; necessity for this procurement and current editions require review.','small')]
    if report.get('limitations'): story += [Spacer(1,16),p('Review notes','heading'),p(report['limitations'])]
    def frame(canvas,doc):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor('#fcfaf7'))
        canvas.rect(0,0,A4[0],A4[1],fill=1,stroke=0)
        canvas.setFillColor(ink);canvas.setFont(BOLD,15)
        canvas.drawString(42,A4[1]-44,'SpecGyan')
        canvas.setFont(FONT,7);canvas.drawString(42,A4[1]-58,'Indian Standards Intelligence')
        canvas.setFillColor(yellow);canvas.setStrokeColor(ink)
        canvas.rect(A4[0]-192,A4[1]-63,150,30,fill=1,stroke=1)
        canvas.setFillColor(ink);canvas.setFont(FONT,7)
        canvas.drawString(A4[0]-182,A4[1]-45,'TENDER REVIEW')
        canvas.drawString(A4[0]-182,A4[1]-55,'Technical draft')
        canvas.setStrokeColor(colors.HexColor('#888888'));canvas.setLineWidth(.4)
        canvas.line(42,37,A4[0]-42,37)
        canvas.setFont(FONT,6.5);canvas.setFillColor(colors.HexColor('#666666'))
        canvas.drawString(42,25,'SpecGyan | Tender standards recommendation report')
        canvas.drawRightString(A4[0]-42,25,f'Page {doc.page}')
        canvas.restoreState()
    SimpleDocTemplate(stream,pagesize=A4,leftMargin=42,rightMargin=42,topMargin=92,bottomMargin=53,title='SpecGyan - Tender standards recommendation report',author='SpecGyan').build(story,onFirstPage=frame,onLaterPages=frame)
    return stream.getvalue()
