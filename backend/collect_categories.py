import argparse
import getpass
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import requests
from psycopg.types.json import Jsonb


ROOT = Path(__file__).resolve().parent
BASE = "https://standardsadmin.bis.gov.in/review-service//"

# Initial discovery terms, not an exhaustive BIS catalogue.
CATEGORIES = {
    "construction": [
        "cement", "concrete", "aggregate", "mortar", "brick", "block",
        "masonry", "reinforcement", "structural steel", "building", "construction",
        "foundation", "soil", "geotechnical", "timber", "plywood", "door", "window",
        "glass", "roof", "floor", "tile", "stone", "gypsum", "plaster",
        "waterproofing", "sealant", "paint", "bitumen", "road", "bridge",
        "scaffolding", "formwork", "prefabricated", "earthquake", "fire resistance",
    ],
    "electrical": [
        "cable", "wire", "conductor", "wiring", "insulation", "switch", "socket",
        "plug", "circuit breaker", "switchgear", "fuse", "contactor", "relay",
        "residual current", "earthing", "lightning", "surge", "distribution board",
        "transformer", "motor", "generator", "electrical", "electric",
        "luminaire", "lamp", "LED", "battery", "inverter", "photovoltaic",
        "uninterruptible", "conduit", "capacitor", "meter", "insulator",
    ],
    "plumbing": [
        "pipe", "fitting", "valve", "tap", "faucet", "plumbing", "water supply",
        "potable water", "sanitary", "sanitation", "drain", "sewer", "sewage",
        "water closet", "wash basin", "cistern", "flushing", "water storage",
        "water tank", "water meter", "backflow", "hydrant", "pump", "CPVC",
        "PVC", "polyethylene", "polypropylene", "ductile iron", "cast iron",
    ],
}


AUTH = {
    "token": None,
    "refreshToken": None,
    "clientId": None,
    "clientSecret": None,
    "sub": None,
}


def now():
    return datetime.now(timezone.utc)


def valid_response(value):
    return isinstance(value, dict) and value.get("status") == "SUCCESS"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


class StopCollection(Exception):
    pass


session = requests.Session()
session.headers.update({"Accept": "application/json"})


def fetch(endpoint, payload):
    try:
        response = session.post(
            BASE + endpoint,
            json={**AUTH, **payload},
            timeout=(10, 45),
        )

        if response.status_code in (401, 403, 429):
            raise StopCollection(
                f"BIS returned HTTP {response.status_code}. "
                "Progress is saved. Stop and retry later."
            )

        response.raise_for_status()
        result = response.json()

        if not valid_response(result):
            raise ValueError(
                f"{endpoint}: {result.get('msg', 'Unsuccessful response')}"
            )

        return result
    finally:
        # Avoid sending a burst of requests to BIS.
        time.sleep(1)


def create_tables(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS bis_records (
            standard_id BIGINT PRIMARY KEY,
            search_record JSONB NOT NULL
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS bis_responses (
            standard_id BIGINT NOT NULL
                REFERENCES bis_records(standard_id),
            endpoint TEXT NOT NULL,
            payload JSONB NOT NULL,
            retrieved_at TIMESTAMPTZ,
            imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            source_url TEXT NOT NULL,
            PRIMARY KEY (standard_id, endpoint)
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS bis_searches (
            category TEXT NOT NULL,
            query TEXT NOT NULL,
            payload JSONB NOT NULL,
            retrieved_at TIMESTAMPTZ,
            imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            complete BOOLEAN NOT NULL,
            PRIMARY KEY (category, query)
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS bis_category_candidates (
            standard_id BIGINT NOT NULL
                REFERENCES bis_records(standard_id),
            category TEXT NOT NULL,
            discovery_query TEXT NOT NULL,
            verified BOOLEAN NOT NULL DEFAULT FALSE,
            PRIMARY KEY (standard_id, category, discovery_query)
        )
    """)


def save_record(db, record):
    standard_id = int(record["standardId"])

    db.execute("""
        INSERT INTO bis_records (standard_id, search_record)
        VALUES (%s, %s)
        ON CONFLICT (standard_id)
        DO UPDATE SET search_record = EXCLUDED.search_record
    """, (standard_id, Jsonb(record)))

    return standard_id


def save_response(db, standard_id, endpoint, payload, timestamp):
    db.execute("""
        INSERT INTO bis_responses
            (standard_id, endpoint, payload, retrieved_at, source_url)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (standard_id, endpoint) DO NOTHING
    """, (
        standard_id,
        endpoint,
        Jsonb(payload),
        timestamp,
        BASE + endpoint,
    ))


def import_existing(db):
    imported = 0

    for path in sorted((ROOT / "bis_collected").glob("*.json")):
        try:
            saved = read_json(path)
            record = saved["search_record"]

            # Keep each file import atomic.
            with db.transaction():
                standard_id = save_record(db, record)

                for field, endpoint in (
                    ("details_response", "getWebsiteStandardDetails"),
                    ("references_response", "getCrossRefDetails"),
                ):
                    payload = saved.get(field)
                    if valid_response(payload):
                        save_response(
                            db,
                            standard_id,
                            endpoint,
                            payload,
                            saved.get("retrieved_at"),
                        )

            imported += 1

        except (ValueError, KeyError, TypeError) as error:
            print(f"Skipped invalid cache {path.name}: {error}")

    print(f"Existing collection files imported/reused: {imported}")


def find_cached_search(query):
    # Reuse the raw search filenames used by the existing project.
    name = query.replace(" ", "_")

    for filename in (
        f"bis_{name}_raw.json",
        f"bis_{name}.json",
    ):
        path = ROOT / filename
        if not path.exists():
            continue

        try:
            result = read_json(path)
            if valid_response(result) and isinstance(result.get("data"), list):
                return result
        except (ValueError, OSError):
            pass

    return None


def discover(db, refresh=False):
    incomplete = []

    for category, queries in CATEGORIES.items():
        for query in queries:
            stored = db.execute("""
                SELECT complete, retrieved_at FROM bis_searches
                WHERE category = %s AND query = %s
            """, (category, query)).fetchone()

            if (not refresh and stored and stored[0] and stored[1]
                    and (now() - stored[1]).total_seconds() < 30 * 86400):
                print(f"[Search cached] {category}: {query}")
                continue

            payload = None
            timestamp = None

            if payload is None:
                payload = fetch("searchKnowStandards", {"searchText": query})
                timestamp = now()

            records = payload.get("data")
            if not isinstance(records, list):
                raise ValueError(f"{query}: expected a list of search records")

            try:
                reported = int(payload["totalRecords"])
            except (KeyError, TypeError, ValueError):
                reported = None

            ids = [int(record["standardId"]) for record in records]
            complete = (reported is not None and len(records) == reported
                        and len(set(ids)) == len(records))

            with db.transaction():
                for record in records:
                    standard_id = save_record(db, record)

                    db.execute("""
                        INSERT INTO bis_category_candidates
                            (standard_id, category, discovery_query)
                        VALUES (%s, %s, %s)
                        ON CONFLICT DO NOTHING
                    """, (standard_id, category, query))

                db.execute("""
                    INSERT INTO bis_searches
                        (category, query, payload, retrieved_at, complete)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (category, query) DO UPDATE SET
                        payload = EXCLUDED.payload,
                        retrieved_at = EXCLUDED.retrieved_at,
                        complete = EXCLUDED.complete
                """, (
                    category, query, Jsonb(payload), timestamp, complete
                ))

            print(
                f"[Search] {category} / {query}: "
                f"{len(records)} received / {reported} reported"
            )

            if not complete:
                incomplete.append(query)

    if incomplete:
        print("INCOMPLETE responses (pagination must be investigated):", ", ".join(incomplete))
    print("Keyword discovery finished. Full category coverage is NOT verified.")


def collect_missing(db):
        # Collection priorities selected from the audited catalogue.
    # These are BIS database IDs, not IS numbers or ranking overrides.
    priority_ids = [
        # Electrical products
        13826,  # IS 694:2010 — PVC-insulated cables
        29854,  # IS 3854:2023 — domestic switches
        25402,  # IS 1293:2019 — plugs and socket-outlets
        20830,  # IS/IEC 60898 Part 1:2015 — circuit breakers
        31276,  # IS 12640 Part 1:2024 — RCCBs
        4056,   # IS 12640 Part 2:2016 — RCBOs

        # Electrical supporting / installation records
        14236,  # IS 732:2019 — wiring installations
        15200,  # IS 8130:2013 — conductors
        12637,  # IS 5831:1984 — insulation and sheath materials

        # Plumbing products
        25779,  # IS 4985:2021 — PVC potable-water pipes
        7976,   # IS 15778:2007 — CPVC hot/cold-water pipes
        11693,  # IS 4984:2016 — polyethylene water pipes
        7998,   # IS 15801:2008 — polypropylene hot/cold-water pipes
        25791,  # IS 17546:2021 — CPVC fittings
        27371,  # IS 8008:2022 — polyethylene fittings
        17155,  # IS 9739:1981 — domestic pressure-reducing valves
        17179,  # IS 9763:2000 — taps and valves

        # Plumbing supporting / installation records
        14621,  # IS 7634 Part 3:2003 — UPVC installation
        886,    # IS 10124 Part 1:2009 — fabricated PVC-U fittings
        14864,  # IS 7834 Part 1:1987 — moulded PVC fittings
    ]

    records = db.execute("""
        SELECT standard_id, search_record
        FROM bis_records
        WHERE standard_id = ANY(%s)
        ORDER BY standard_id
    """, (priority_ids,)).fetchall()

    print(
        f"Selected {len(records)} priority records. "
        "Only missing endpoint responses will be fetched."
    )

    failed = 0

    for index, (standard_id, record) in enumerate(records, 1):
        endpoints = (
            "getWebsiteStandardDetails",
            "getCrossRefDetails",
            "getAmendmentDetails",
        )

        saved = {
            row[0] for row in db.execute("""
                SELECT endpoint FROM bis_responses
                WHERE standard_id = %s
            """, (standard_id,)).fetchall()
        }

        missing = [endpoint for endpoint in endpoints if endpoint not in saved]
        if not missing:
            continue

        print(
            f"[{index}/{len(records)}] "
            f"{record.get('standardNumber', standard_id)}"
        )

        enc_id = record.get("standardEncId")
        if not enc_id:
            print("  Missing encrypted identifier; needs review.")
            failed += 1
            continue

        for endpoint in missing:
            try:
                if endpoint == "getAmendmentDetails":
                    request = {"standardId": enc_id}
                else:
                    request = {
                        "encId": enc_id,
                        "fromPage": "guestUserPage",
                    }

                payload = fetch(endpoint, request)

                expected_type = (
                    list if endpoint == "getAmendmentDetails" else dict
                )
                if not isinstance(payload.get("data"), expected_type):
                    raise ValueError("Unexpected response data structure")

                if endpoint == "getWebsiteStandardDetails":
                    returned_id = payload["data"].get("rowStandardId")
                    if returned_id is None or int(returned_id) != standard_id:
                        raise ValueError("Returned standard ID does not match")

                # Save each endpoint immediately, so a later failure
                # does not cause successful requests to be repeated.
                save_response(db, standard_id, endpoint, payload, now())
                print(f"  Saved {endpoint}")

            except (requests.RequestException, ValueError) as error:
                failed += 1
                print(f"  Retry needed: {endpoint}: {error}")

    print(f"Requests requiring retry/review: {failed}")


def show_summary(db):
    print("\nDATABASE SUMMARY")

    for category, count in db.execute("""
        SELECT category, COUNT(DISTINCT standard_id)
        FROM bis_category_candidates
        GROUP BY category
        ORDER BY category
    """):
        print(f"{category}: {count} discovered candidates")

    count = db.execute("SELECT COUNT(*) FROM bis_records").fetchone()[0]
    print(f"Unique standards stored: {count}")
    print("Category assignments are provisional until reviewed.")


def audit_database(db):
    from collections import Counter, defaultdict
    import re

    records = db.execute("""
        SELECT standard_id, search_record
        FROM bis_records
        ORDER BY standard_id
    """).fetchall()

    responses = db.execute("""
        SELECT standard_id, endpoint, payload, retrieved_at
        FROM bis_responses
    """).fetchall()

    assignments = db.execute("""
        SELECT standard_id, category, discovery_query, verified
        FROM bis_category_candidates
        ORDER BY category, standard_id
    """).fetchall()

    searches = db.execute("""
        SELECT category, query, complete, retrieved_at, payload
        FROM bis_searches
        ORDER BY category, query
    """).fetchall()

    by_record = defaultdict(dict)
    by_category = defaultdict(list)

    for standard_id, endpoint, payload, timestamp in responses:
        by_record[standard_id][endpoint] = {
            "payload": payload,
            "retrieved_at": timestamp.isoformat() if timestamp else None,
        }

    for standard_id, category, query, verified in assignments:
        by_category[standard_id].append({
            "category": category,
            "discovery_query": query,
            "verified": verified,
        })

    def normalized(value):
        return re.sub(r"\s+", "", str(value or "")).upper()

    def integer(value):
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    def populated(value):
        return value not in (None, "", [], {}) and bool(str(value).strip())

    inventory = []
    issue_counts = Counter()
    identifier_groups = defaultdict(list)

    endpoints = (
        "getWebsiteStandardDetails",
        "getCrossRefDetails",
        "getAmendmentDetails",
    )

    for standard_id, raw in records:
        issues = []

        if not isinstance(raw, dict):
            raw = {}
            issues.append("invalid_search_record")

        saved = by_record.get(standard_id, {})
        detail_payload = saved.get(
            "getWebsiteStandardDetails", {}
        ).get("payload", {})

        details = (
            detail_payload.get("data", {})
            if isinstance(detail_payload, dict)
            else {}
        )
        if not isinstance(details, dict):
            details = {}
            issues.append("invalid_detail_data")

        number = raw.get("standardNumber")
        title = raw.get("standardName")

        if not number:
            issues.append("missing_identifier")
        else:
            identifier_groups[normalized(number)].append(standard_id)

        if not title:
            issues.append("missing_title")

        if not raw.get("standardEncId"):
            issues.append("missing_fetch_identifier")

        for endpoint in endpoints:
            if endpoint not in saved:
                issues.append(f"missing:{endpoint}")
                continue

            response = saved[endpoint]
            payload = response["payload"]

            if not isinstance(payload, dict):
                issues.append(f"invalid_response:{endpoint}")
                continue

            if payload.get("status") != "SUCCESS":
                issues.append(f"unsuccessful_response:{endpoint}")

            expected = list if endpoint == "getAmendmentDetails" else dict
            if not isinstance(payload.get("data"), expected):
                issues.append(f"invalid_data_shape:{endpoint}")

            if response["retrieved_at"] is None:
                issues.append(f"unknown_retrieval_date:{endpoint}")

        if details:
            if integer(details.get("rowStandardId")) != standard_id:
                issues.append("detail_id_mismatch_or_missing")

            if normalized(details.get("standardNumber")) != normalized(number):
                issues.append("detail_identifier_mismatch_or_missing")

            if (
                title
                and details.get("standardName")
                and normalized(title) != normalized(details["standardName"])
            ):
                issues.append("search_detail_title_difference")

            a = raw.get("withdrawStatus")
            b = details.get("withdrawStatus")
            if a is not None and b is not None and str(a) != str(b):
                issues.append("withdrawal_metadata_conflict")

        amendment_payload = saved.get(
            "getAmendmentDetails", {}
        ).get("payload", {})

        amendment_data = (
            amendment_payload.get("data")
            if isinstance(amendment_payload, dict)
            else None
        )

        if isinstance(amendment_data, list):
            metadata_count = integer(details.get("noOfAmendment"))
            reported_count = integer(
                amendment_payload.get("totalAmendments")
            )

            if (
                metadata_count is not None
                and metadata_count != len(amendment_data)
            ):
                issues.append("amendment_metadata_count_mismatch")

            if (
                reported_count is not None
                and reported_count != len(amendment_data)
            ):
                issues.append("amendment_response_count_mismatch")

        categories = by_category.get(standard_id, [])

        if not categories:
            issues.append("no_category_assignment")
        elif not any(item["verified"] for item in categories):
            issues.append("category_not_reviewed")

        withdrawn = any(
            str(item.get("withdrawStatus", "")).strip() == "1"
            for item in (raw, details)
        )

        replacement = (
            details.get("superseded_byis")
            or raw.get("superseded_byis")
        )

        if withdrawn:
            issues.append("withdrawal_recorded")
        if populated(replacement):
            issues.append("replacement_recorded")

        issue_counts.update(issues)

        # Deliberately omit encrypted IDs, credentials and document bodies.
        inventory.append({
            "standard_id": standard_id,
            "is_number": number,
            "title": title,
            "category_assignments": categories,
            "committee_id": details.get(
                "committeeId", raw.get("committeeId")
            ),
            "committee_name": details.get("committeeName"),
            "department_name": details.get("departmentName"),
            "group": details.get("groupName"),
            "subgroup": details.get("subGroupName"),
            "sub_subgroup": details.get("subSubGroupName"),
            "standard_type": details.get("typeOfStandardId"),
            "ics_code": details.get("icsCode"),
            "withdrawal_recorded": withdrawn,
            "replacement": replacement,
            "stored_endpoints": {
                endpoint: item["retrieved_at"]
                for endpoint, item in saved.items()
            },
            "issues": issues,
        })

    category_counts = {}
    for category in CATEGORIES:
        category_counts[category] = len({
            standard_id
            for standard_id, assigned, _, _ in assignments
            if assigned == category
        })

    search_inventory = []
    for category, query, complete, timestamp, payload in searches:
        payload = payload if isinstance(payload, dict) else {}
        data = payload.get("data")

        search_inventory.append({
            "category": category,
            "query": query,
            "received": len(data) if isinstance(data, list) else None,
            "reported": payload.get("totalRecords"),
            "stored_complete_flag": complete,
            "retrieved_at": timestamp.isoformat() if timestamp else None,
        })

    duplicates = {
        number: ids
        for number, ids in identifier_groups.items()
        if len(ids) > 1
    }

    report = {
        "audit_generated_at": now().isoformat(),
        "note": (
            "Read-only database inventory. Category correctness, scope "
            "applicability and current BIS status are not verified by "
            "this audit. Search completeness is not catalogue coverage."
        ),
        "unique_records": len(records),
        "category_candidate_counts": category_counts,
        "issue_counts": dict(sorted(issue_counts.items())),
        "duplicate_identifier_groups": duplicates,
        "searches": search_inventory,
        "records": inventory,
    }

    output = ROOT / "bis_data_audit.json"
    temporary = output.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    temporary.replace(output)

    print("\nDATA AUDIT")
    print(f"Unique records: {len(records)}")

    for category, count in category_counts.items():
        print(f"{category}: {count} candidates")

    print(f"Duplicate identifier groups: {len(duplicates)}")

    print("\nChecks requiring attention:")
    for issue, count in sorted(issue_counts.items()):
        print(f"  {issue}: {count}")

    print(f"\nAudit saved: {output}")
    print("Audit itself is read-only. Earlier collection steps may have updated the database.")


def main():
    parser = argparse.ArgumentParser(description="Resumable BIS discovery into PostgreSQL")
    parser.add_argument("--refresh", action="store_true", help="Refresh all configured searches")
    parser.add_argument("--audit-only", action="store_true", help="Only inspect existing records")
    args = parser.parse_args()
    print("CATALOGUE DISCOVERY — basic records only; no detail downloads.")
    host = input("Host [localhost]: ").strip() or "localhost"
    port = input("Port [5432]: ").strip() or "5432"
    user = input("User [postgres]: ").strip() or "postgres"
    password = getpass.getpass("PostgreSQL password: ")

    try:
        with psycopg.connect(
            host=host,
            port=port,
            dbname="velocia",
            user=user,
            password=password,
            connect_timeout=10,
        ) as db:
            # Save each completed search independently.
            db.autocommit = True

            try:
                create_tables(db)
                if not args.audit_only:
                    discover(db, refresh=args.refresh)
                show_summary(db)

            except StopCollection as error:
                print(error)

            except (requests.RequestException, ValueError) as error:
                print(f"Discovery paused: {error}")

            except KeyboardInterrupt:
                print("\nDiscovery paused. Completed searches are saved.")

            with db.transaction():
                db.execute(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
                )
                audit_database(db)

    except psycopg.Error as error:
        print(f"Database audit failed: {error}")
    except OSError as error:
        print(f"Could not write the audit report: {error}")
    except KeyboardInterrupt:
        print("\nStopped. Previously committed collection progress is retained.")


if __name__ == "__main__":
    main()