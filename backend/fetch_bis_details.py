import json
from pathlib import Path
import requests

folder = Path(__file__).resolve().parent
raw = json.loads((folder / "bis_cement_raw.json").read_text(encoding="utf-8"))

# Select one cement-related standard.
record = next(
    item for item in raw["data"]
    if "cement" in item.get("standardName", "").lower().split()
)

payload = {
    "encId": record["standardEncId"],
    "fromPage": "guestUserPage",
    "clientId": None,
    "clientSecret": None,
    "refreshToken": None,
    "sub": None,
    "token": None,
}

try:
    response = requests.post(
        "https://standardsadmin.bis.gov.in/review-service//getWebsiteStandardDetails",
        json=payload,
        headers={"Accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    result = response.json()

    output = folder / "bis_single_details.json"
    output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("Requested:", record["standardNumber"])
    print("Status:", result.get("status"))
    print("Message:", result.get("msg"))

    details = result.get("data")
    if isinstance(details, dict):
        print("Detail fields:", list(details.keys()))
        print("Returned standard:", details.get("standardNumber"))

    print("Saved:", output)

except (requests.RequestException, ValueError) as error:
    print("Failed:", error)