import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "bis_collected"
CACHE = ROOT / "bis_search_cache"
BASE = "https://standardsadmin.bis.gov.in/review-service/"

# Next batch. Additional categories can be added later.
TERMS = ["concrete", "aggregate", "mortar"]

OUTPUT.mkdir(exist_ok=True)
CACHE.mkdir(exist_ok=True)

session = requests.Session()
session.headers.update({"Accept": "application/json"})

AUTH = {
    "clientId": None,
    "clientSecret": None,
    "refreshToken": None,
    "sub": None,
    "token": None,
}

issues = []
stats = {"completed": 0, "skipped": 0, "failed": 0}


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, data):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def fetch(endpoint, payload):
    try:
        response = session.post(
            BASE + "/" + endpoint,
            json={**AUTH, **payload},
            timeout=30,
        )

        if response.status_code in (401, 403, 429):
            raise RuntimeError(
                f"BIS returned HTTP {response.status_code}. "
                "Stopping; saved progress is retained."
            )

        response.raise_for_status()
        result = response.json()

        if not isinstance(result, dict):
            raise ValueError("Unexpected response format")

        if result.get("status") != "SUCCESS":
            raise ValueError(result.get("msg", "BIS request failed"))

        return result
    finally:
        time.sleep(2)


def collect():
    records = {}
    origins = {}

    # Search all terms first; preserve every raw response.
    for term in TERMS:
        cache_file = CACHE / f"{term}.json"

        try:
            if cache_file.exists():
                result = read(cache_file)
            else:
                result = fetch(
                    "searchKnowStandards",
                    {"searchText": term},
                )
                if not isinstance(result.get("data"), list):
                    raise ValueError("Search data is not a list")
                save(cache_file, result)

            rows = result["data"]
            if not isinstance(rows, list):
                raise ValueError("Cached search data is not a list")

            total = result.get("totalRecords")
            print(f"{term}: received {len(rows)} / reported {total}")

            if total is None or int(total) != len(rows):
                issues.append({
                    "term": term,
                    "issue": "Search completeness unresolved",
                    "received": len(rows),
                    "reported": total,
                })
                print("  CHECK: results may be incomplete.")

            for item in rows:
                identifier = str(int(item["standardId"]))
                records[identifier] = item
                origins.setdefault(identifier, [])
                if term not in origins[identifier]:
                    origins[identifier].append(term)

        except (requests.RequestException, ValueError, KeyError) as error:
            issues.append({"term": term, "error": str(error)})
            print(f"Search failed for {term}: {error}")

    save(ROOT / "bis_search_origins.json", origins)
    print(f"\nUnique IDs in this batch: {len(records)}")

    for index, (identifier, record) in enumerate(records.items(), 1):
        target = OUTPUT / f"{identifier}.json"

        try:
            data = read(target) if target.exists() else {
                "search_record": record,
                "source_urls": {},
            }

            details_ok = (
                data.get("details_response", {}).get("status") == "SUCCESS"
            )
            references_ok = (
                data.get("references_response", {}).get("status")
                == "SUCCESS"
            )

            if details_ok and references_ok:
                stats["skipped"] += 1
                continue

            payload = {
                "encId": record["standardEncId"],
                "fromPage": "guestUserPage",
            }

            if not details_ok:
                result = fetch("getWebsiteStandardDetails", payload)
                details = result.get("data")

                if not isinstance(details, dict):
                    raise ValueError("Invalid standard details")

                # Verify the returned record identity.
                if str(details.get("rowStandardId")) != identifier:
                    raise ValueError("Returned standard ID does not match")

                data["details_response"] = result
                data["details_fetched_at"] = now()
                data.setdefault("source_urls", {})["details"] = (
                    BASE + "/getWebsiteStandardDetails"
                )
                save(target, data)

            if not references_ok:
                result = fetch("getCrossRefDetails", payload)
                references = result.get("data")

                if not isinstance(references, dict) or any(
                    not isinstance(references.get(field), list)
                    for field in ("crossRefData", "crossFollowRefData")
                ):
                    raise ValueError("Invalid cross-reference structure")

                data["references_response"] = result
                data["references_fetched_at"] = now()
                data.setdefault("source_urls", {})["references"] = (
                    BASE + "/getCrossRefDetails"
                )

            data["retrieved_at"] = now()
            save(target, data)
            stats["completed"] += 1

            print(
                f"[{index}/{len(records)}] Saved "
                f"{record['standardNumber']}"
            )

        except (requests.RequestException, ValueError, KeyError) as error:
            stats["failed"] += 1
            issues.append({"standard_id": identifier, "error": str(error)})
            print(f"FAILED {identifier}: {error}")


try:
    collect()
except RuntimeError as error:
    issues.append({"stopped": str(error)})
    print(error)
except KeyboardInterrupt:
    print("\nStopped by user. Rerun to resume.")
finally:
    save(
        ROOT / "bis_collection_report.json",
        {"finished_at": now(), "stats": stats, "issues": issues},
    )
    print("\nSummary:", stats)
    print("Report: bis_collection_report.json")
    session.close()