import copy
import html
import json
import os
import re
from collections import Counter
from pathlib import Path

from rank_bm25 import BM25Okapi
import numpy as np

import psycopg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

BIS_CATALOGUE = (
    "https://standards.bis.gov.in/website/know-your-standards"
)
CATEGORIES = {"construction", "electrical", "plumbing"}


def load_scope_evidence():
    """Only join summaries to the exact edition documented by the source."""
    path = Path(__file__).resolve().parent / "scope_evidence.json"
    if not path.exists():
        return {}
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))["entries"]
        if not isinstance(entries, list):
            raise ValueError("entries must be a list")
        output = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            number = normalized(entry.get("is_number"))
            summary = clean(entry.get("summary"))
            url = clean(entry.get("source_url"))
            if not number or not summary or not url.startswith("https://"):
                continue
            if number in output:
                raise ValueError(f"Duplicate scope evidence for {number}")
            output[number] = entry
        return output
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ValueError(f"Invalid scope evidence file: {error}") from error


def clean(value):
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def normalized(value):
    return re.sub(r"[^a-z0-9]", "", clean(value).lower())


def timestamp(value):
    return value.isoformat() if value else None


def integer(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def identifier(text):
    """Support IS and IS/IEC or IS/ISO, including parts and sections."""
    text = clean(text).rstrip(".;,")
    match = re.fullmatch(
        r"IS\s*(?:/\s*(IEC|ISO)\s*)?[-:]?\s*(\d+)"
        r"(?:\s*\(?\s*Part\s*(\d+)"
        r"(?:\s*/?\s*Sec(?:tion)?\s*(\d+))?\s*\)?)?"
        r"(?:\s*:\s*(\d{4}))?",
        text,
        re.I,
    )
    return match.groups() if match else None


def identifier_matches(query, stored):
    requested = identifier(query)
    candidate = identifier(stored)

    if not requested or not candidate:
        return normalized(query) == normalized(stored)

    if (requested[0] or "").upper() != (candidate[0] or "").upper():
        return False

    if requested[1] != candidate[1]:
        return False

    return all(
        requested[index] is None
        or requested[index] == candidate[index]
        for index in (2, 3, 4)
    )


def response_data(responses, endpoint, expected):
    entry = responses.get(endpoint, {})
    payload = entry.get("payload") or {}

    if (
        isinstance(payload, dict)
        and payload.get("status") == "SUCCESS"
        and isinstance(payload.get("data"), expected)
    ):
        return payload["data"]

    return None


def reference_rows(items, incoming=False):
    return [
        {
            "is_number": item.get("standardNumber"),
            "title": clean(item.get("standardName")),
            "bis_reference_type": item.get("typeLabel"),
            "relationship": (
                "Listed by BIS as referencing this standard"
                if incoming
                else "Listed in BIS cross-references"
            ),
            "applicability_verified": False,
        }
        for item in (items or [])
        if isinstance(item, dict)
    ]


def infer_role(title):
    """Fallback title classification; reviewed profiles take precedence."""
    text = title.lower()

    if re.search(r"\binsulation and sheath\b|\binsulating compounds?\b", text):
        return "material"

    if re.search(r"^conductors for\b", text):
        return "component"

    if re.search(r"\bcode of practice\b|\blaying and jointing\b", text):
        return "installation"

    if re.search(
        r"\bmethods? of tests?\b|\btest methods?\b|"
        r"\bterminology\b|\bvocabulary\b",
        text,
    ):
        return "test_or_reference"

    if re.search(r"\bcurrent ratings?\b|\btest and measuring methods\b", text):
        return "test_or_reference"

    return "unclassified"


def product_intent(query):
    text = clean(query).lower()

    # Explicit supporting-standard requests must remain searchable.
    if re.search(
        r"\btest(?:ing)?\b|\btest methods?\b|\binstallation\b|"
        r"\binstalling\b|\blaying\b|\bjointing\b|\bterminology\b",
        text,
    ):
        return "supporting"

    if not re.search(r"\bcables?\b|\bwires?\b", text) and re.search(r"\binsulation\b|\bsheath\b|\bconductors?\b", text):
        return "supporting"

    if re.search(r"\bcement\b", text) and not re.search(
        r"\bconcrete\b|\bmortar\b|\bgrout\b|\bbricks?\b|\bboards?\b|\bpipes?\b", text
    ):
        return "cement"

    if re.search(r"\bfittings?\b|\belbows?\b|\btees?\b", text):
        return "fitting"
    if re.search(r"\bpipes?\b|\btubes?\b", text):
        return "pipe"
    if re.search(r"\bcables?\b|\bwires?\b|\bwiring\b", text):
        return "cable"
    if re.search(r"\bsockets?\b|\bplugs?\b", text):
        return "socket"
    if re.search(r"\bcircuit[\s-]*breakers?\b|\brccb\b|\brcbo\b", text):
        return "breaker"
    if re.search(r"\bswitch(?:es)?\b", text):
        return "switch"
    if re.search(r"\bvalves?\b|\btaps?\b", text):
        return "valve"

    return None


def voltage_values(text):
    # Join grouped thousands only (e.g. BIS titles containing "1 100 V").
    text = re.sub(r"(?<=\d)[ ,](?=\d{3}\b)", "", text.lower())
    matches = re.findall(r"(?<![\w.])(\d+(?:\.\d+)?)(?:\s*/\s*(\d+(?:\.\d+)?))?\s*(kv|volts?|v)\b", text)
    return [float(value) * (1000 if unit == "kv" else 1)
            for first, second, unit in matches for value in (first, second) if value]


def voltage_compatible(query, title):
    """Reject only a conflict with an explicit title voltage range.

    Missing/complex voltage evidence is unknown, not verified compatible.
    This does not establish AC/DC, U0/U, insulation or scope applicability.
    """
    requested = voltage_values(query)
    if not requested:
        return True
    t = re.sub(r"(?<=\d)[ ,](?=\d{3}\b)", "", title.lower())
    number = r"\d+(?:\.\d+)?"
    unit = r"(?:kv|volts?|v)"
    pair = re.search(
        rf"\bfrom\s+({number})\s*({unit})?\s+(?:up\s+to(?:\s+and\s+including)?|to)\s+({number})\s*({unit})\b", t)
    if pair:
        lo, lu, hi, hu = pair.groups()
        lower = float(lo) * (1000 if (lu or hu) == 'kv' else 1)
        upper = float(hi) * (1000 if hu == 'kv' else 1)
        if lower > upper:
            return True
        return all(lower <= v <= upper for v in requested)
    upper = re.search(rf"\b(?:up\s+to(?:\s+and\s+including)?|not\s+exceeding)\s+({number})\s*({unit})\b", t)
    if upper:
        value, u = upper.groups()
        maximum = float(value) * (1000 if u == 'kv' else 1)
        return all(v <= maximum for v in requested)
    return True


def title_fits(query, title, intent, role, category):
    q = clean(query).lower()
    t = clean(title).lower()

    if intent == "cable" and not voltage_compatible(q, t):
        return False

    # Broad discovery tags alone are insufficient for these categories.
    if category == "plumbing":
        if not re.search(
            r"\bpipes?\b|\btubes?\b|\bfittings?\b|\bvalves?\b|"
            r"\btaps?\b|\bplumbing\b|\bsanitary\b|\bwater supply\b",
            t,
        ):
            return False

    if category == "electrical":
        if not re.search(
            r"\belectri\w*\b|\bcables?\b|\bconductors?\b|"
            r"\bcircuit[\s-]*breakers?\b|\bswitchgear\b|"
            r"\bswitch(?:es)?\b|\bsocket[\s-]*outlets?\b|\bwiring\b",
            t,
        ):
            return False

    # Title evidence can reject a mismatch, but cannot verify applicability.
    # These gates never override an exact-identifier lookup.
    if intent == "cement":
        if not re.search(r"\bcement\b", t):
            return False
        if re.search(
            r"\bbricks?\b|\baggregates?\b|\bboards?\b|\bpipes?\b|"
            r"\bapparatus\b|\btesting\b|\bmethods?\b|\bmachines?\b|\bmoulds?\b", t
        ):
            return False

    if intent == "cable":
        if re.search(r"\bxlpe\b|\bcross[ -]?linked polyethylene\b", q):
            if not re.search(r"\bxlpe\b|\bcross[ -]?linked polyethylene\b", t):
                return False
        if re.search(r"\bcurrent ratings?\b|\btest and measuring methods\b", t):
            return False
        if re.search(r"\bbuilding\b|\bhousehold\b|\bdomestic\b", q):
            if re.search(
                r"\blow[ -]frequency\b|\bcommunication\b|\bsignall?ing\b|\btelephone\b", t
            ):
                return False
        if re.search(r"\bpvc[ -]+insulated\b", q) and re.search(
            r"\bxlpe\b|\bcross[ -]?linked polyethylene\b", t
        ):
            return False

    if intent in ("pipe", "fitting") and re.search(
        r"\bpotable\b|\bdrinking\b", q
    ):
        if re.search(
            r"\bsoil\b|\bwaste\b|\bdrainage\b|\brain[ -]?water\b|\bsewer", t
        ):
            return False

    patterns = {
        "cement": r"\bcement\b",
        "pipe": r"\bpipes?\b|\btubes?\b",
        "fitting": r"\bfittings?\b|\belbows?\b|\btees?\b",
        "cable": r"\bcables?\b|\bcords?\b|\bwires?\b",
        "socket": r"\bsocket[\s-]*outlets?\b|\bplugs?\b",
        "breaker": r"\bcircuit[\s-]*breakers?\b",
        "switch": r"\bswitch(?:es)?\b",
        "valve": r"\bvalves?\b|\btaps?\b",
    }

    if intent in patterns:
        if not re.search(patterns[intent], t):
            return False

        if role in (
            "material", "component", "installation", "test_or_reference"
        ):
            return False

        if re.search(
            r"\bmethods? of tests?\b|\btest methods?\b|"
            r"\bterminology\b|\bvocabulary\b|\bcode of practice\b|"
            r"\bapparatus\b|\btesting equipment\b",
            t,
        ):
            return False

    if intent == "pipe" and re.search(
        r"\bcoatings?\b|\bseals?\b|\bjoint rings?\b|\bvalves?\b", t
    ):
        return False

    if intent == "cable":
        if re.search(
            r"\binsulation and sheath\b|\bconductors for\b|"
            r"\bdrums\b|\bcalico\b|\btape\b|\byarn\b",
            t,
        ):
            return False

        if re.search(r"\bbuilding\b|\bhousehold\b|\bdomestic\b", q):
            if re.search(
                r"\bribbon\b|\baircraft\b|\bcoaxial\b|\boptical\b|"
                r"\btelecommunication\b|\bphotovoltaic\b|"
                r"\bsubmarine\b|\boverhead\b",
                t,
            ):
                return False

    # Match explicitly requested pipe/cable materials.
    if intent in ("pipe", "fitting", "cable"):
        if re.search(r"\bcpvc\b|\bchlorinated polyvinyl", q):
            if not re.search(r"\bcpvc\b|\bc p v c\b|\bchlorinated polyvinyl", t):
                return False

        elif re.search(r"\bupvc\b|\bpvc\b|\bpvc-u\b|\bpolyvinyl chloride\b", q):
            if re.search(r"\bcpvc\b|\bchlorinated polyvinyl", t):
                return False
            if not re.search(
                r"\bupvc\b|\bpvc\b|\bpvc-u\b|\bpolyvinyl chloride\b", t
            ):
                return False

        elif re.search(r"\bhdpe\b|\bpolyethylene\b", q):
            if not re.search(r"\bhdpe\b|\bpolyethylene\b", t):
                return False

        elif re.search(r"\bpolypropylene\b|\bppr\b", q):
            if not re.search(r"\bpolypropylene\b|\bppr\b", t):
                return False

    if category == "plumbing" and re.search(
        r"\bdrinking\b|\bpotable\b|\bwater supply\b", q
    ):
        if not re.search(r"\bwater\b|\bpotable\b", t):
            return False
        if re.search(
            r"\bother than potable\b|\bnon[\s-]*potable\b|"
            r"\bsewerage\b|\btelecommunication\b|\bfire extinguishing\b",
            t,
        ):
            return False

    return True


STOP_WORDS = set("a an the we i need want supply provide for of to and or in on with our which standard standards specification specifications requirement requirements is are be this that used use".split())

def lexical_tokens(text):
    # Keep technical codes, grades and numbers; normalize common plurals only.
    plurals = {"cables": "cable", "wires": "wire", "pipes": "pipe",
               "fittings": "fitting", "valves": "valve", "switches": "switch"}
    return [plurals.get(t, t) for t in re.findall(r"[^\W_]+", clean(text).lower())
            if t not in STOP_WORDS]


def why_recommended(query, record, overlap=None, exact=False):
    if exact:
        return "The IS number matches the identifier you entered. Check the standard's scope and current edition before citing it."
    # An overlap is an observation about text, never proof of applicability.
    title_terms = set(lexical_tokens(record.get("title", "")))
    query_terms = list(dict.fromkeys(lexical_tokens(query)))
    shared = [term for term in query_terms if term in title_terms and term not in {"is", "part"}]
    if shared:
        return "Its title matches your terms: " + ", ".join(shared[:5]) + ". Confirm the full scope before using it."
    if overlap and record.get("scope_summary"):
        return "The BIS coverage summary contains related terms. Review its source and the full standard before citing it."
    return "Semantic search found a related title. Check the full scope before using this code."

def search_text(record):
    # Keep retrieval on the existing IS number + title index. Coverage summaries
    # are displayed as evidence until evaluated for their effect on ranking.
    return ". ".join(clean(record.get(key)) for key in
                     ("is_number", "title") if record.get(key))

def reciprocal_rank_fusion(dense, lexical, k=60):
    scores = {}
    for ranking in (dense, lexical):
        for rank, index in enumerate(dict.fromkeys(ranking), 1):
            scores[index] = scores.get(index, 0.0) + 1.0 / (k + rank)
    return scores


class CatalogueSearch:
    def __init__(self, model):
        self.model = model
        self.records = []
        self.vectors = None
        scope_evidence = load_scope_evidence()

        with psycopg.connect(
            host=os.getenv("PGHOST", "localhost"),
            port=os.getenv("PGPORT", "5432"),
            dbname=os.getenv("PGDATABASE", "velocia"),
            user=os.getenv("PGUSER", "postgres"),
            password=os.getenv("PGPASSWORD", ""),
            connect_timeout=5,
        ) as db:
            records = db.execute("""
                SELECT standard_id, search_record
                FROM bis_records ORDER BY standard_id
            """).fetchall()

            assignments = db.execute("""
                SELECT c.standard_id, c.category, MAX(s.retrieved_at)
                FROM bis_category_candidates c
                LEFT JOIN bis_searches s
                    ON s.category = c.category
                    AND s.query = c.discovery_query
                GROUP BY c.standard_id, c.category
            """).fetchall()

            responses = db.execute("""
                SELECT standard_id, endpoint, payload, retrieved_at
                FROM bis_responses
            """).fetchall()

            profiles = db.execute("""
                SELECT standard_id, category, product_family,
                       standard_role, review_status, review_note
                FROM bis_reviewed_profiles
            """).fetchall()

        categories = {}
        dates = {}
        for sid, category, retrieved in assignments:
            categories.setdefault(sid, set()).add(category)
            if retrieved and (sid not in dates or retrieved > dates[sid]):
                dates[sid] = retrieved

        stored = {}
        for sid, endpoint, payload, retrieved in responses:
            stored.setdefault(sid, {})[endpoint] = {
                "payload": payload,
                "retrieved_at": timestamp(retrieved),
            }

        reviewed = {
            row[0]: {
                "category": row[1],
                "family": row[2],
                "role": row[3],
                "status": row[4],
                "note": row[5],
            }
            for row in profiles
        }

        # Ambiguous duplicate identifiers stay out until resolved.
        counts = Counter(
            normalized(raw.get("standardNumber"))
            for _, raw in records if isinstance(raw, dict)
        )

        for sid, raw in records:
            if not isinstance(raw, dict):
                continue

            number = clean(raw.get("standardNumber"))
            if not number or counts[normalized(number)] > 1:
                continue

            profile = reviewed.get(sid)
            if profile and profile["status"] != "metadata_reviewed":
                continue

            evidence = stored.get(sid, {})
            details = response_data(
                evidence, "getWebsiteStandardDetails", dict
            )

            if details is not None:
                if integer(details.get("rowStandardId")) != sid:
                    continue
                if normalized(details.get("standardNumber")) != normalized(number):
                    continue

            details = details or {}

            if any(
                str(item.get("withdrawStatus", "")).strip() == "1"
                or clean(item.get("superseded_byis"))
                for item in (raw, details)
            ):
                continue

            title = clean(
                details.get("standardName") or raw.get("standardName")
            )
            if not title:
                continue

            record_categories = (
                [profile["category"]]
                if profile else sorted(categories.get(sid, []))
            )
            if not record_categories:
                continue

            refs = response_data(
                evidence, "getCrossRefDetails", dict
            )
            amendments = response_data(
                evidence, "getAmendmentDetails", list
            )

            metadata_count = integer(details.get("noOfAmendment"))
            amendment_payload = evidence.get(
                "getAmendmentDetails", {}
            ).get("payload") or {}

            reported_count = integer(
                amendment_payload.get("totalAmendments")
            )
            count_matches = (
                metadata_count == len(amendments)
                if amendments is not None and metadata_count is not None
                else None
            )

            warnings = [
                "Latest edition and technical applicability remain unverified."
            ]

            if count_matches is False:
                warnings.append(
                    "Amendment records and BIS metadata report different counts."
                )

            if (
                amendments is not None
                and reported_count is not None
                and reported_count != len(amendments)
            ):
                warnings.append(
                    "The amendment response count differs from its record list."
                )

            detailed = bool(profile and details)
            detail_date = evidence.get(
                "getWebsiteStandardDetails", {}
            ).get("retrieved_at")
            amendment_date = evidence.get(
                "getAmendmentDetails", {}
            ).get("retrieved_at")
            scope = scope_evidence.get(normalized(number), {})

            self.records.append({
                "standard_id": sid,
                "is_number": number,
                "title": title,
                "categories": record_categories,
                "category_verified": bool(profile),
                "product_family": profile["family"] if profile else None,
                "standard_role": (
                    profile["role"] if profile else infer_role(title)
                ),
                "record_level": "detailed" if detailed else "catalogue",
                "scope_summary": clean(scope.get("summary")),
                "scope_source_url": scope.get("source_url"),
                "scope_source_label": scope.get("source_label"),
                "scope_verified": False,
                "latest_version_verified": False,
                "applicability_verified": False,
                "retrieved_at": (
                    detail_date if detailed else timestamp(dates.get(sid))
                ),
                "reaffirmation_date": details.get("reAffirmationYear"),
                "amendments_checked_at": amendment_date,
                "amendments": amendments or [],
                "related_standards": reference_rows(
                    (refs or {}).get("crossRefData")
                ),
                "referenced_by": reference_rows(
                    (refs or {}).get("crossFollowRefData"), incoming=True
                ),
                "revision_check": {
                    "edition": number,
                    "amendment_count": metadata_count,
                    "amendment_count_matches_metadata": count_matches,
                    "latest_version_verified": False,
                    "amendment_documents_reviewed": False,
                    "warnings": warnings,
                },
                "certification_check": {
                    "bis_metadata_label": (
                        details.get("certificationName") or "Unknown"
                    ),
                    "applicability_verified": False,
                    "message": (
                        "BIS metadata only. QCO applicability, effective dates "
                        "and exemptions have not been verified."
                    ),
                },
                "bis_catalogue_url": BIS_CATALOGUE,
            })

        self.token_sets = [set(lexical_tokens(search_text(r))) for r in self.records]
        corpus = [lexical_tokens(search_text(r)) for r in self.records]
        self.bm25 = BM25Okapi(corpus) if corpus and any(corpus) else None
        if self.records:
            self.vectors = self.model.encode(
                [
                    search_text(item)
                    for item in self.records
                ],
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            ).astype("float32")

        detailed_count = sum(
            item["record_level"] == "detailed" for item in self.records
        )

        print(
            f"Hybrid catalogue ready (BM25 + semantic + RRF): {len(self.records)} records; "
            f"{detailed_count} with reviewed metadata and details."
        )

    def search(self, query, category, limit=5):
        if category not in CATEGORIES:
            raise ValueError("Unsupported category.")

        if not self.records or limit < 1:
            return []

        eligible = [
            index for index, record in enumerate(self.records)
            if category in record["categories"]
        ]

        if identifier(query):
            return [
                {
                    **copy.deepcopy(self.records[index]),
                    "exact_match": True,
                    "similarity": None,
                    "reason": (
                        "Exact identifier match. Technical applicability "
                        "and latest-edition status remain unverified."
                    ),
                    "why_recommended": why_recommended(query, self.records[index], exact=True),
                }
                for index in eligible
                if identifier_matches(
                    query, self.records[index]["is_number"]
                )
            ][:limit]

        # Do not silently ignore explicit exclusions.
        if re.search(
            r"\bwithout\b|\bmust not\b|\bexcluding\b|\bnot suitable\b",
            query,
            re.I,
        ):
            return []

        intent = product_intent(query)
        query_vector = self.model.encode(
            [query],
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        ).astype("float32")[0]

        scores = self.vectors @ query_vector
        tokens = list(dict.fromkeys(lexical_tokens(query)))
        lexical_scores = (self.bm25.get_scores(tokens) if self.bm25 is not None
                          else np.zeros(len(self.records)))
        eligible = [i for i in eligible if title_fits(
            query, self.records[i]["title"], intent,
            self.records[i]["standard_role"], category)]
        # Independent recall: lexical hits need not pass the dense threshold.
        # RRF is a rank score, never a probability or an acceptance threshold.
        dense = sorted((i for i in eligible if np.isfinite(scores[i]) and scores[i] >= 0.40),
                       key=lambda i: (-float(scores[i]), self.records[i]["standard_id"]))[:25]
        terms = set(tokens)
        lexical = sorted((i for i in eligible
                          if np.isfinite(lexical_scores[i]) and lexical_scores[i] > 0
                          and len(terms & self.token_sets[i]) >= min(2, len(terms))
                          and terms),
                         key=lambda i: (-float(lexical_scores[i]), self.records[i]["standard_id"]))[:25]
        fused = reciprocal_rank_fusion(dense, lexical)
        dense_ranks = {i: rank for rank, i in enumerate(dense, 1)}
        lexical_ranks = {i: rank for rank, i in enumerate(lexical, 1)}
        order = sorted(fused, key=lambda i: (-fused[i], -float(scores[i]) if np.isfinite(scores[i]) else 0.0, self.records[i]["standard_id"]))
        output = []
        for index in order[:limit]:
            record = copy.deepcopy(self.records[index])
            methods = []
            if index in dense_ranks:
                methods.append("semantic similarity")
            if index in lexical_ranks:
                methods.append("keyword matching")
            overlap = sorted(terms & self.token_sets[index])
            record.update({
                "exact_match": False,
                "similarity": round(float(scores[index]), 4) if np.isfinite(scores[index]) else None,
                "bm25_score": round(float(lexical_scores[index]), 6),
                "rrf_score": round(fused[index], 8),
                "dense_rank": dense_ranks.get(index),
                "lexical_rank": lexical_ranks.get(index),
                "retrieval_method": "bm25_dense_rrf",
                "matched_terms": overlap,
                "reason": "Retrieved using " + " and ".join(methods) + ". "
                    + ("Matching terms: " + ", ".join(overlap[:8]) + ". " if overlap else "")
                    + "Technical applicability and latest edition remain unverified.",
                "why_recommended": why_recommended(query, record, overlap=overlap),
            })
            output.append(record)
        return output
