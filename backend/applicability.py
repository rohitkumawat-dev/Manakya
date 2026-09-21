"""Initial requirement rules; not verified technical applicability."""

import re


CEMENT_ATTRIBUTES = (
    "white",
    "fly ash",
    "calcined clay",
    "slag",
    "composite",
    "masonry",
    "hydrophobic",
    "low heat",
    "rapid hardening",
    "microfine",
)


def normalize(text):
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def contains(text, term):
    return bool(re.search(r"\b" + re.escape(term) + r"\b", text))


def requirement_context(query):
    q = normalize(query)
    context = {
        "intent": "general",
        "clarification": None,
        "cement_attributes": [],
    }

    if re.match(r"^is\s*\d", q):
        context["intent"] = "identifier"
        return context

    if contains(q, "jolting") and re.search(
        r"\b(apparatus|equipment|machine)\b", q
    ):
        context["intent"] = "jolting_equipment"
        return context

    if contains(q, "cement"):
        specific = re.search(
            r"\b(fly ash|calcined clay|portland|pozzolana|slag|"
            r"composite|masonry|white|hydrophobic|sulphate|sulfate|"
            r"low heat|rapid hardening|alumina|microfine|clinker|"
            r"test|testing|apparatus|equipment|chemical|physical|"
            r"33|43|53)\b",
            q,
        )

        if not specific:
            context["intent"] = "cement_unspecified"
            context["clarification"] = (
                "Which cement type or technical requirement do you need? "
                "For example: ordinary Portland cement, fly-ash-based "
                "Portland pozzolana cement, or Portland slag cement. "
                "If unsure, describe the intended use and required properties."
            )
            return context

        # These simple rules do not interpret negation or testing requests.
        skip_attributes = re.search(
            r"\b(not|without|except|excluding|test|testing|"
            r"apparatus|equipment)\b",
            q,
        )

        if not skip_attributes:
            context["cement_attributes"] = [
                term for term in CEMENT_ATTRIBUTES if contains(q, term)
            ]

    return context


def rank_candidates(candidates, context, limit=3):
    primary = []
    supporting = []

    for original in candidates:
        item = dict(original)
        title = normalize(item.get("title", ""))
        item["recommendation_role"] = "candidate"
        item["applicability_verified"] = False

        # Preserve exact standard-number matches.
        if item.get("exact_match"):
            primary.append(item)
            continue

        if context["intent"] == "jolting_equipment":
            equipment_match = contains(title, "jolting") and any(
                contains(title, word)
                for word in ("apparatus", "equipment", "machine")
            )

            if not equipment_match:
                item["recommendation_role"] = "other_candidate"
                supporting.append(item)
                continue

            item["recommendation_role"] = "equipment"

        attributes = context.get("cement_attributes", [])

        if attributes:
            matched = [
                term for term in attributes if contains(title, term)
            ]
            item["matched_product_attributes"] = matched

            if len(matched) != len(attributes):
                item["recommendation_role"] = "attribute_not_confirmed"
                supporting.append(item)
                continue

            item["reason"] = (
                item.get("reason", "")
                + " Explicit product attributes matched in the title: "
                + ", ".join(matched)
                + ". Scope applicability remains unverified."
            ).strip()

        primary.append(item)

    # Preserve semantic ranking within the accepted candidates.
    return primary[:limit], supporting[:limit]