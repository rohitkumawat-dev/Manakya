"""Conservative corrections: never guess an unknown word from a small catalogue."""
import re

# Only unambiguous, observed misspellings. Unknown words remain unchanged.
TYPOS = {
    'cemnt': 'cement', 'cemennt': 'cement', 'cememt': 'cement',
    'portlnd': 'portland', 'pozolana': 'pozzolana',
    'electrcal': 'electrical', 'insualted': 'insulated',
    'drinkng': 'drinking', 'watr': 'water',
}
# Explicit domain aliases, not query-to-standard mappings.
ALIASES = [
    (r'\bOPC\b', 'ordinary Portland cement'),
    (r'\bPPC\b', 'Portland pozzolana cement'),
    (r'\bCPVC\b|\bchlorinated[\s-]+PVC\b', 'chlorinated polyvinyl chloride'),
    (r'\bUPVC\b|\bPVC[ -]U\b', 'unplasticized PVC'),
    (r'\bXLPE\b', 'crosslinked polyethylene'),
    (r'\bHDPE\b', 'high density polyethylene'),
    (r'\brotomoulded\b|\brotomolded\b', 'rotational moulded'),
]


def correct_query(query):
    changes = []
    if re.search(r'\bIS\s*(?:/\s*(?:IEC|ISO)\s*)?[-:]?\s*\d', query, re.I):
        return query, changes

    def typo(match):
        original = match.group()
        replacement = TYPOS.get(original.lower())
        if replacement:
            changes.append({'original': original, 'corrected': replacement, 'kind':'spelling'})
            return replacement
        return original

    text = re.sub(r'\b[A-Za-z]+\b', typo, query)
    for pattern, replacement in ALIASES:
        def expand(match):
            changes.append({'original':match.group(), 'corrected':replacement, 'kind':'alias'})
            return replacement
        text = re.sub(pattern, expand, text, flags=re.I)
    return text, changes
