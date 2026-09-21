import json
from pathlib import Path
import requests

folder = Path(__file__).resolve().parent

# 6875 is the ID in your collected data for IS 1489 Part 1:2015.
source = folder / "bis_collected" / "6875.json"

try:
    record = json.loads(source.read_text(encoding="utf-8"))
    standard = record["search_record"]

    payload = {
        "standardId": standard["standardEncId"],
        "clientId": None,
        "clientSecret": None,
        "refreshToken": None,
        "sub": None,
        "token": None,
    }

    response = requests.post(
        "https://standardsadmin.bis.gov.in/review-service//getAmendmentDetails",
        json=payload,
        headers={"Accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    result = response.json()

    output = folder / "bis_amendments_6875.json"
    output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("Requested:", standard["standardNumber"])
    print(
        "Metadata amendment count:",
        record["details_response"]["data"].get("noOfAmendment"),
    )
    print("Response:", json.dumps(result, indent=2, ensure_ascii=False))
    print("Saved:", output)

except (OSError, ValueError, KeyError, requests.RequestException) as error:
    print("Failed:", error)
    