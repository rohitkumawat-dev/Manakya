import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://standardsadmin.bis.gov.in/review-service/"
FOLDER = Path(__file__).resolve().parent
OUTPUT = FOLDER / "bis_collected"
OUTPUT.mkdir(exist_ok=True)

raw = json.loads(
    (FOLDER / "bis_cement_raw.json").read_text(encoding="utf-8")
)

# Start with 5 records. Change to None after checking the output.
LIMIT = None
candidates = [
    record for record in raw["data"]
    if record.get("committeeId") == 190
]
records = candidates[:LIMIT]
print(f"Selected {len(records)} Cement and Concrete records")
session = requests.Session()
session.headers.update({"Accept": "application/json"})


def fetch(endpoint, enc_id):
    payload = {
        "encId": enc_id,
        "fromPage": "guestUserPage",
        "clientId": None,
        "clientSecret": None,
        "refreshToken": None,
        "sub": None,
        "token": None,
    }
    try:
        response = session.post(
            BASE + "/" + endpoint, json=payload, timeout=30
        )
        response.raise_for_status()
        result = response.json()
        if result.get("status") != "SUCCESS":
            raise ValueError(result.get("msg", "BIS request unsuccessful"))
        return result
    finally:
        time.sleep(2)


for index, record in enumerate(records, 1):
    target = OUTPUT / f'{record["standardId"]}.json'

    if target.exists():
        print(f'[{index}/{len(records)}] Already saved: '
              f'{record["standardNumber"]}')
        continue

    print(f'[{index}/{len(records)}] Fetching: '
          f'{record["standardNumber"]}')

    try:
        enc_id = record["standardEncId"]
        details = fetch("getWebsiteStandardDetails", enc_id)
        references = fetch("getCrossRefDetails", enc_id)

        collected = {
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "search_record": record,
            "details_response": details,
            "references_response": references,
            "source_urls": {
                "details": BASE + "/getWebsiteStandardDetails",
                "references": BASE + "/getCrossRefDetails",
            },
        }

        temporary = target.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(collected, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary.replace(target)
        print("Saved.")

    except requests.HTTPError as error:
        print("HTTP error:", error)
        if error.response.status_code in (401, 403, 429):
            print("Stopping: access restriction or rate limit.")
            break
    except (requests.RequestException, ValueError, KeyError) as error:
        print("Not saved; rerun to retry:", error)

print("Finished. Files:", OUTPUT)