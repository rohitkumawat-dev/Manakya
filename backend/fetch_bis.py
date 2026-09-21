import json
from pathlib import Path
import requests

url = "https://standardsadmin.bis.gov.in/review-service//searchKnowStandards"

payload = {
    "searchText": "cement",
    "token": None,
    "refreshToken": None,
    "clientId": None,
    "clientSecret": None,
    "sub": None,
}

try:
    response = requests.post(
        url,
        json=payload,
        headers={"Accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    output = Path(__file__).resolve().parent / "bis_cement_raw.json"
    output.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Response saved to: {output}")
    if isinstance(data, dict):
        print("Response keys:", list(data.keys()))

except requests.RequestException as error:
    print(f"Request failed: {error}")
except ValueError:
    print("BIS returned a response that is not valid JSON.")
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        records = data["data"]

    print("Status:", data.get("status"))
    print("Total matches:", data.get("totalRecords"))
    print("Records received:", len(records))

    for item in records[:5]:
        print(item.get("standardNumber"), "-", item.get("standardName"))
print("DEBUG CHECK")

if isinstance(data, dict):
    print("Status:", data.get("status"))
    print("Total records:", data.get("totalRecords"))
    print("Data type:", type(data.get("data")).__name__)
    print("Data preview:", json.dumps(data.get("data"), ensure_ascii=False)[:1500])
records = data["data"]
print("Records received:", len(records))
print("Total matches:", data["totalRecords"])