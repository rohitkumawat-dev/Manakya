import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

folder = Path(__file__).resolve().parent
dataset_path = folder / "standards.json"
standards = json.loads(dataset_path.read_text(encoding="utf-8"))

backup = folder / "standards_before_amendments.json"
if not backup.exists():
    backup.write_bytes(dataset_path.read_bytes())

session = requests.Session()

for index, standard in enumerate(standards, 1):
    label = standard["is_number"]

    if standard.get("amendments_checked_at"):
        print(f"[{index}/{len(standards)}] Already saved: {label}")
        continue

    try:
        source = folder / "bis_collected" / f'{standard["standard_id"]}.json'
        raw = json.loads(source.read_text(encoding="utf-8"))

        response = session.post(
            "https://standardsadmin.bis.gov.in/review-service//getAmendmentDetails",
            json={
                "standardId": raw["search_record"]["standardEncId"],
                "clientId": None,
                "clientSecret": None,
                "refreshToken": None,
                "sub": None,
                "token": None,
            },
            headers={"Accept": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()
        amendments = result.get("data")

        if result.get("status") != "SUCCESS":
            raise ValueError(result.get("msg", "Unsuccessful response"))

        if not isinstance(amendments, list):
            raise ValueError("Unexpected amendment response format")

        if int(result["totalAmendments"]) != len(amendments):
            raise ValueError("Response count mismatch; needs investigation")

        if any(
            str(item.get("standardId")) != str(standard["standard_id"])
            for item in amendments
        ):
            raise ValueError("Response contains a different standard ID")

        try:
            expected = int(standard.get("amendment_count_raw"))
        except (TypeError, ValueError):
            expected = None

        standard["amendments"] = amendments
        standard["amendment_count_matches_metadata"] = (
            expected == len(amendments) if expected is not None else None
        )
        standard["amendment_documents_reviewed"] = False
        standard["amendments_checked_at"] = datetime.now(
            timezone.utc
        ).isoformat()

        temporary = dataset_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(standards, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary.replace(dataset_path)

        print(f"[{index}/{len(standards)}] {label}: "
              f"{len(amendments)} amendment record(s) saved")

        if standard["amendment_count_matches_metadata"] is False:
            print("  CHECK: amendment count differs from saved metadata.")

    except requests.HTTPError as error:
        print(f"{label}: {error}")
        if error.response.status_code in (401, 403, 429):
            print("Stopping due to access restriction or rate limit.")
            break
    except (requests.RequestException, OSError, ValueError, KeyError) as error:
        print(f"{label}: FAILED — {error}")
    finally:
        time.sleep(2)

print("Finished. Successful records are saved; rerun to retry failures.")