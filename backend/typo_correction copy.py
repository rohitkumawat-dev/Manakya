import json
import re
from difflib import SequenceMatcher
from pathlib import Path


# General procurement words, plus vocabulary from our dataset.
WORDS = {
    "drinking", "water", "supply", "supplies",
    "building", "buildings", "procure", "procurement",
    "steel", "pipe", "pipes", "tube", "tubes",
    "unplasticized", "laboratory", "computer", "laptops",
}

data_path = Path(__file__).parent / "standards.json"

with data_path.open("r", encoding="utf-8") as file:
    for item in json.load(file):
        text = " ".join([
            item["title"],
            item.get("scope_summary", ""),
            *item.get("keywords", []),
        ])
        WORDS.update(re.findall(r"[a-z]{4,}", text.lower()))


def correct_query(query):
    corrections = []

    # Preserve standard identifier queries exactly.
    if re.search(r"\bIS\s*[-:]?\s*\d", query, re.IGNORECASE):
        return query, corrections

    def replace_word(match):
        original = match.group()
        word = original.lower()

        # Preserve known words, short words, and uppercase abbreviations.
        if len(word) < 4 or word in WORDS or original.isupper():
            return original

        candidates = []

        for candidate in WORDS:
            if candidate[0] != word[0]:
                continue

            if abs(len(candidate) - len(word)) > 2:
                continue

            score = SequenceMatcher(None, word, candidate).ratio()
            candidates.append((score, candidate))

        candidates.sort(key=lambda item: (-item[0], item[1]))

        if not candidates or candidates[0][0] < 0.80:
            return original

        # Leave ambiguous spellings unchanged.
        if (
            len(candidates) > 1
            and candidates[0][0] - candidates[1][0] < 0.05
        ):
            return original

        replacement = candidates[0][1]

        corrections.append({
            "original": original,
            "corrected": replacement,
        })

        return replacement

    # Match whole alphabetic words, avoiding parts of codes like PE100.
    corrected = re.sub(r"\b[a-zA-Z]+\b", replace_word, query)

    return corrected, corrections


if __name__ == "__main__":
    for query in [
        "We need stel pips for a building.",
        "UPVC pips for drinkng watr",
        "IS 4985: 2021",
    ]:
        corrected, changes = correct_query(query)
        print(f"\nOriginal:  {query}")
        print(f"Searching: {corrected}")
        print(f"Changes:   {changes}")