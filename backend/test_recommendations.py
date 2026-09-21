import json
from pathlib import Path
import requests

tests = [
    ("Fly ash cement",
     "We need Portland pozzolana cement made with fly ash.",
     "fly ash"),
    ("Calcined clay cement",
     "We need Portland pozzolana cement made with calcined clay.",
     "calcined clay"),
    ("White cement",
     "We need white Portland cement.",
     "white portland"),
    ("Slag cement",
     "We need Portland slag cement.",
     "portland slag"),
    ("Testing equipment",
     "We need a jolting apparatus for testing cement.",
     "jolting"),
    ("Spelling mistakes",
     "We need portlnd pozolana cemnt made with fly ash.",
     "fly ash"),
    ("Ambiguous requirement",
     "We need cement for building construction.",
     "CLARIFY"),
    ("Outside dataset",
     "We need laptops for a college computer laboratory.",
     "NO_MATCH"),
    ("Exact identifier",
     "IS 1489 (Part 1):2015.",
     "EXACT"),
]

results = []

for name, query, expected in tests:
    try:
        response = requests.post(
            "http://127.0.0.1:8000/api/analyze",
            json={"requirement": query},
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        standards = data.get("standards", [])
        first = standards[0] if standards else {}

        if expected == "CLARIFY":
            passed = bool(data.get("clarification_question"))
        elif expected == "NO_MATCH":
            passed = not standards
        elif expected == "EXACT":
            passed = (
                len(standards) == 1
                and first.get("exact_match") is True
                and first.get("standard_id") == 6875
            )
        else:
            title = " ".join(first.get("title", "").lower().split())
            passed = expected in title

        results.append({
            "test": name,
            "query": query,
            "passed": passed,
            "response": data,
        })
        print(
            f"{'PASS' if passed else 'CHECK'} | {name} | "
            f"{first.get('is_number', data.get('message', ''))}"
        )

    except (requests.RequestException, ValueError) as error:
        results.append({"test": name, "passed": False, "error": str(error)})
        print(f"ERROR | {name} | {error}")

output = Path(__file__).with_name("recommendation_test_results.json")
output.write_text(
    json.dumps(results, indent=2, ensure_ascii=False),
    encoding="utf-8",
)
print(f"\nPassed: {sum(r['passed'] for r in results)}/{len(results)}")
print(f"Saved: {output}")