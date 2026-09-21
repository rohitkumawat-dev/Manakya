import json
import re
from pathlib import Path
from standard_numbers import (
    parse_standard_number,
    matches_standard_number,
)

import faiss
from sentence_transformers import SentenceTransformer


class StandardsSearch:
    def __init__(self):
        data_path = Path(__file__).parent / "standards.json"

        with data_path.open("r", encoding="utf-8") as file:
            self.standards = json.load(file)

        if not self.standards:
            raise ValueError(
                "standards.json must contain at least one record."
            )

        print("Loading semantic model...")

        self.model = SentenceTransformer(
            "sentence-transformers/all-MiniLM-L6-v2",
            device="cpu",
        )

        documents = [
            (
                f"{item['is_number']}. {item['title']}. "
                f"{item.get('scope_summary', '')}"
            )
            for item in self.standards
        ]

        embeddings = self.model.encode(
            documents,
            normalize_embeddings=True,
            convert_to_numpy=True,
        ).astype("float32")

        self.index = faiss.IndexFlatIP(embeddings.shape[1])
        self.index.add(embeddings)

        print(f"Search ready: {len(documents)} record(s).")

    def search(self, query, top_k=3):
        if not query.strip() or top_k < 1:
            return []

        def normalize(text):
            return re.sub(
                r"[^a-z0-9]+", " ", text.lower()
            ).strip()

        normalized_query = normalize(query)

        query_vector = self.model.encode(
            [query.strip()],
            normalize_embeddings=True,
            convert_to_numpy=True,
        ).astype("float32")

        scores, positions = self.index.search(
            query_vector, len(self.standards)
        )

        results = []

        for score, position in zip(scores[0], positions[0]):
            standard = self.standards[int(position)]

            exact_match = matches_standard_number(
                query, standard["is_number"]
            )

            # A specific IS-number search must not return other numbers.
            if parse_standard_number(query) and not exact_match:
                continue

            keywords = [
                keyword
                for keyword in standard.get("keywords", [])
                if (
                    f" {normalize(keyword)} "
                    in f" {normalized_query} "
                )
            ]

            similarity = float(score)
            ranking_score = similarity + (0.05 if keywords else 0)

            if exact_match:
                reason = "Exact standard identifier match."
            elif keywords:
                reason = (
                    "Semantic retrieval with matching product terms: "
                    + ", ".join(keywords)
                    + ". Confirm the standard's scope before use."
                )
            else:
                reason = (
                    "Retrieved by semantic similarity. "
                    "Confirm the standard's scope before use."
                )

            results.append({
                **standard,
                "similarity": round(similarity, 4),
                "ranking_score": round(ranking_score, 4),
                "exact_match": exact_match,
                "matched_keywords": keywords,
                "reason": reason,
            })

        results.sort(
            key=lambda item: (
                item["exact_match"],
                item["ranking_score"],
            ),
            reverse=True,
        )

        return results[:top_k]


if __name__ == "__main__":
    engine = StandardsSearch()

    queries = [
        "IS 1239 (Part 1): 2004",
        "We need steel pipes for a building.",
        "We need laptops for a computer laboratory.",
    ]

    for query in queries:
        print(f"\nQuery: {query}")

        for result in engine.search(query):
            print(
                f"{result['is_number']} | "
                f"Similarity: {result['similarity']} | "
                f"Exact match: {result['exact_match']}"
            )