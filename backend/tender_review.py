"""Editable heuristic segmentation and snapshot-based citation audit."""
import json
import re
from pathlib import Path

CITATION = re.compile(r'\bIS\s*[-:]?\s*(\d+)(?:\s*\(\s*Part\s*(\d+)\s*\))?(?:\s*:\s*(\d{4}))?(?!\d)', re.I)


def identity(text):
    m = CITATION.fullmatch(text.strip())
    return tuple(m.groups()) if m else None


def split_requirements(text):
    # Keep continuation lines with their item. Never split on "and".
    lines = re.sub(r'(?m)^\s*(?:\d+[.)]|[-•])\s+', '\n\n', text)
    items = [x.strip() for x in re.split(r'\n\s*\n', lines) if x.strip()]
    if len(items) > 20 or any(len(x) > 5000 for x in items):
        raise ValueError('Split into at most 20 items, each at most 5,000 characters. Use blank lines between items.')
    return items


def load_snapshot():
    return json.loads(Path(__file__).with_name('citation_snapshot.json').read_text(encoding='utf-8'))


def audit_citations(text, snapshot):
    found, seen = [], set()
    for m in CITATION.finditer(text):
        key = tuple(m.groups())
        if key in seen:
            continue
        seen.add(key)
        # Avoid treating a partially parsed section or slash identifier as complete.
        tail = text[m.end():]
        if re.match(r'\s*(?:/|\(|Part\b|Section\b|Sec\b)', tail, re.I):
            found.append({'citation': m.group(), 'status': 'unsupported_format', 'message': 'This identifier format needs manual review.', 'evidence': []})
            continue
        rows = [r for r in snapshot if identity(r['standard_number']) == key]
        if key[2] is None:
            status, message = 'edition_unspecified', 'No edition year supplied; verify the intended edition.'
        elif not rows:
            status, message = 'not_in_snapshot', 'Citation not found in our limited snapshot; it is not necessarily invalid.'
        elif any(r.get('replacement') for r in rows):
            status, message = 'replacement_recorded', 'BIS snapshot lists a replacement. Check its applicability and transition dates before changing the tender.'
        elif any(str(r.get('withdraw_status')) == '1' for r in rows):
            status, message = 'withdrawal_recorded', 'BIS snapshot marks this record withdrawn; review the citation.'
        else:
            status, message = 'record_found', 'Edition found in snapshot. Latest status and applicability remain unverified.'
        found.append({'citation': m.group(), 'status': status, 'message': message, 'evidence': rows})
    return found


def recommendation_text(text):
    # Audit the cited edition separately; do not let it dominate product retrieval.
    return CITATION.sub('', text).strip(' .,:;-\n')
