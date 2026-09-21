import re


def parse_standard_number(text):
    # Allow harmless punctuation at the end of an identifier.
    text = text.strip().rstrip(".,;").strip()

    pattern = (
        r"IS\s*[-:]?\s*(?P<number>\d+)"
        r"(?:\s*(?:"
        r"\(\s*Part\s*(?P<paren_part>\d+)\s*\)"
        r"|Part\s*(?P<plain_part>\d+)"
        r"))?"
        r"(?:\s*:\s*(?P<year>\d{4}))?"
    )

    match = re.fullmatch(pattern, text, flags=re.IGNORECASE)

    if not match:
        return None

    return {
        "number": str(int(match.group("number"))),
        "part": (
            str(int(match.group("paren_part") or match.group("plain_part")))
            if match.group("paren_part") or match.group("plain_part")
            else None
        ),
        "year": match.group("year"),
    }


def matches_standard_number(query, identifier):
    requested = parse_standard_number(query)
    stored = parse_standard_number(identifier)

    if not requested or not stored:
        return False

    if requested["number"] != stored["number"]:
        return False

    for field in ("part", "year"):
        if requested[field] is not None:
            if requested[field] != stored[field]:
                return False

    return True