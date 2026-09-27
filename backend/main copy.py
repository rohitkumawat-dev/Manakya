from contextlib import asynccontextmanager
from fastapi.responses import Response
from report_pdf import save_report, get_report
from tender_review import split_requirements, load_snapshot, audit_citations, recommendation_text
from standard_numbers import parse_standard_number
from fastapi import FastAPI, HTTPException, UploadFile, File
from document_extract import extract_document, MAX_BYTES
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from catalogue_search import CatalogueSearch
import re
from catalogue_search import identifier, identifier_matches

from semantic_search import StandardsSearch
from typo_correction import correct_query
from applicability import requirement_context, rank_candidates


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.search_engine = StandardsSearch()
    app.state.catalogue = None
    try:
        app.state.catalogue = CatalogueSearch(app.state.search_engine.model)
    except Exception as error:
        # Keep the existing detailed search available if PostgreSQL fails.
        print(f"Wider catalogue unavailable: {type(error).__name__}")
    app.state.citation_snapshot = load_snapshot()
    yield


app = FastAPI(
    title="Velocia API",
    version="0.3.1",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    requirement: str = Field(min_length=2, max_length=5000)
    category: str = "construction"

@app.get("/")
def home():
    return {"message": "Velocia backend is running"}


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "project": "Velocia",
        "search": "semantic_with_exact_identifier_filter",
    }


CATEGORY_LABELS = {
    "construction": "Construction",
    "electrical": "Electrical",
    "plumbing": "Plumbing",
}


def indicated_categories(text):
    """Conservative routing hints, not verified BIS classification."""
    q = re.sub(r"[^a-z0-9]+", " ", text.lower())

    def has(pattern):
        return bool(re.search(pattern, q))

    electrical = has(
        r"\b(electrical|electric|cables?|wiring|switchgear|rccb|rcbo)\b"
        r"|\bcircuit breakers?\b|\bsocket outlets?\b"
    )

    pipe_product = has(
        r"\b(pipes?|tubes?|fittings?|valves?|taps?)\b"
    )

    water_context = has(
        r"\b(water|potable|drinking|plumbing|sanitary|sewage|"
        r"sewerage|drainage|cpvc|upvc|ppr)\b"
    )

    plumbing = (
        has(r"\b(plumbing|sanitary|faucets?)\b")
        or (pipe_product and water_context)
    )

    construction = has(
        r"\b(cement|concrete|aggregates?|mortar|bricks?|masonry|"
        r"reinforcement|rebar|structural|tiles?)\b"
    )

    # Water pipes/fittings belong to Plumbing in this application's
    # category structure, even when made from concrete or using cement.
    if plumbing and pipe_product:
        construction = False

    if electrical and not has(r"\b(cement|concrete|bricks?|rebar)\b"):
        construction = False

    return {
        category
        for category, present in (
            ("construction", construction),
            ("electrical", electrical),
            ("plumbing", plumbing),
        )
        if present
    }


def candidate_category_allowed(record, category):
    assigned = set(record.get("categories") or [])

    if category not in assigned:
        return False

    # Reviewed database profiles override keyword discovery tags.
    if record.get("category_verified"):
        return True

    hints = indicated_categories(record.get("title", ""))

    # Discovery tags alone cannot establish category relevance.
    # Ambiguous/unclassified catalogue entries are withheld here.
    return hints == {category}


def unified_search(requirement, category):
    query = requirement.strip()

    if len(query) < 2:
        raise HTTPException(
            status_code=422,
            detail="Enter a product description or an IS number.",
        )

    if category not in CATEGORY_LABELS:
        raise HTTPException(
            status_code=422,
            detail="Unsupported category.",
        )

    catalogue = app.state.catalogue
    if catalogue is None:
        raise HTTPException(
            status_code=503,
            detail="Catalogue unavailable. Check the PostgreSQL connection.",
        )

    result = {
        "requirement": query,
        "searched_requirement": query,
        "category": category,
        "corrections": [],
        "clarification_question": None,
        "suggested_category": None,
        "standards": [],
        "search_method": "bm25_dense_rrf",
        "message": "",
    }

    def clarify(message, suggested=None):
        result["message"] = "More information or a category change is needed."
        result["clarification_question"] = message
        result["suggested_category"] = suggested
        return result

    exact_query = identifier(query)

    # Exact identifiers are preserved without spelling changes.
    if exact_query:
        result["search_method"] = "exact_identifier"
        corrected = query
    else:
        corrected, corrections = correct_query(query)
        result["searched_requirement"] = corrected
        result["corrections"] = corrections

        # Use the original wording where it already provides a clear
        # category signal. Otherwise inspect the corrected query.
        hints = indicated_categories(query)
        if not hints:
            hints = indicated_categories(corrected)

        if len(hints) > 1:
            return clarify(
                "This description may cover more than one category. "
                "Enter one product requirement at a time and select "
                "its category."
            )

        if hints and category not in hints:
            suggested = next(iter(hints))
            return clarify(
                f"This requirement appears to concern "
                f"{CATEGORY_LABELS[suggested]}. Select that category "
                "and search again. If this is a different use, "
                "describe the intended application.",
                suggested,
            )

        # Bare pipe/fitting requests can refer to plumbing,
        # structural products, or electrical conduits.
        if not hints and re.search(
            r"\b(pipes?|tubes?|fittings?)\b", corrected, re.I
        ):
            return clarify(
                "What will the pipe or fitting carry or support? "
                "Specify water supply/drainage, electrical conduit, "
                "or structural use, plus the material."
            )

        if re.search(
            r"\b(without|excluding|except)\b|\bmust not\b"
            r"|\bnot suitable\b",
            corrected,
            re.I,
        ):
            return clarify(
                "This requirement contains an exclusion that the "
                "current matcher cannot reliably evaluate. State "
                "the required product and material positively; "
                "the exclusion still needs a technical review."
            )

    # Retrieve from PostgreSQL-backed records for EVERY category.
    # Apply final rules before limiting the displayed results.
    candidates = catalogue.search(
        corrected,
        category,
        limit=max(1, len(catalogue.records)),
    )

    candidates = [
        item for item in candidates
        if candidate_category_allowed(item, category)
    ]

    if category == "construction" and not exact_query:
        context = requirement_context(corrected)

        if context.get("clarification"):
            return clarify(context["clarification"])

        matches, _ = rank_candidates(
            candidates,
            context,
            limit=5,
        )
    else:
        matches = candidates[:5]

    # An identifier found under another supported category must
    # not be replaced by a vaguely similar standard.
    if exact_query and not matches:
        other_categories = {
            candidate_category
            for record in catalogue.records
            if identifier_matches(query, record["is_number"])
            for candidate_category in CATEGORY_LABELS
            if candidate_category != category
            and candidate_category_allowed(record, candidate_category)
        }

        if len(other_categories) == 1:
            suggested = next(iter(other_categories))
            return clarify(
                f"This identifier is available under "
                f"{CATEGORY_LABELS[suggested]} in our collection. "
                "Switch category to view it.",
                suggested,
            )

    result["standards"] = matches

    if matches:
        result["message"] = (
            f"Found {len(matches)} potential candidate(s) within "
            f"{CATEGORY_LABELS[category]}. "
            "Technical applicability and current edition "
            "remain unverified."
        )
    else:
        result["message"] = (
            "No sufficiently supported match in this category. "
            "Add the product, material and intended use, "
            "or check the BIS catalogue."
        )

    return result


@app.post("/api/analyze")
def analyze_requirement(request: AnalyzeRequest):
    return unified_search(request.requirement, request.category)


@app.post("/api/extract-document")
def extract_uploaded_document(file: UploadFile = File(...)):
    try:
        content = file.file.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise HTTPException(status_code=413, detail="Choose a file smaller than 10 MB.")
        return extract_document(file.filename or "", content)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    finally:
        file.file.close()


class TenderPreviewRequest(BaseModel):
    text: str = Field(min_length=2, max_length=100000)


class TenderReviewRequest(BaseModel):
    items: list[str] = Field(min_length=1, max_length=20)
    category: str = "construction"
    categories: list[str] | None = None
    source_document: str | None = Field(default=None, max_length=255)


@app.post("/api/tender/preview")
def tender_preview(request: TenderPreviewRequest):
    try:
        items = split_requirements(request.text)

        if not items:
            raise ValueError("Enter at least one requirement.")

        return {
            "items": items,
            "message": (
                "Review the suggested split. Keep each product with "
                "its specifications and citations."
            ),
        }
    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error


@app.post("/api/tender/review")
def tender_review(request: TenderReviewRequest):
    if any(
        not 2 <= len(item.strip()) <= 5000
        for item in request.items
    ):
        raise HTTPException(
            status_code=422,
            detail="Each item must contain 2–5,000 characters.",
        )

    categories = request.categories
    if categories is None:
        categories = [request.category] * len(request.items)

    if len(categories) != len(request.items):
        raise HTTPException(
            status_code=422,
            detail="Select one category for every requirement.",
        )

    if any(category not in CATEGORY_LABELS for category in categories):
        raise HTTPException(
            status_code=422,
            detail="Unsupported category.",
        )

    if app.state.catalogue is None:
        raise HTTPException(
            status_code=503,
            detail="Catalogue unavailable. Check PostgreSQL.",
        )

    output = []

    for item, category in zip(request.items, categories):
        item = item.strip()
        citations = audit_citations(
            item,
            app.state.citation_snapshot,
        )
        product_text = recommendation_text(item)

        # A citation alone is not a product specification.
        descriptive_words = re.findall(
            r"[A-Za-z]+", product_text.lower()
        )
        filler = {
            "as", "per", "is", "standard", "standards",
            "according", "to", "with", "comply", "compliance",
            "shall", "be", "the", "and", "or",
        }
        has_description = any(
            word not in filler for word in descriptive_words
        )

        if has_description and len(product_text) >= 2:
            result = unified_search(product_text, category)
        else:
            result = {
                "category": category,
                "standards": [],
                "message": (
                    "The citation was checked separately. Add a product "
                    "description and intended use for recommendations."
                ),
                "clarification_question": None,
                "suggested_category": None,
            }

        output.append({
            "requirement": item,
            "category": category,
            "citation_checks": citations,
            "recommendations": result,
        })

    response = {
        "items": output,
        "limitations": (
            "Recommendations use the loaded PostgreSQL catalogue. "
            "Citation checks use a separate, limited older snapshot; "
            "a missing citation is not necessarily invalid. "
            "Unsupported citation formats require manual review. "
            "Technical applicability and latest-edition status "
            "remain unverified."
        ),
    }

    try:
        response["report_id"] = save_report(response, request.source_document)
        response["report_notice"] = "PDF available for up to one hour while this backend session is running."
    except ValueError as error:
        response["report_notice"] = str(error)
    return response


@app.get("/api/reports/{report_id}/pdf")
def download_report(report_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", report_id):
        raise HTTPException(status_code=404, detail="Report not found.")
    try:
        pdf = get_report(report_id)
    except KeyError:
        raise HTTPException(status_code=410, detail="Report expired or backend restarted. Review the items again.")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="Velocia-tender-report.pdf"',
            "Cache-Control": "no-store",
        },
    )


class CatalogueRequest(BaseModel):
    requirement: str = Field(min_length=2, max_length=5000)
    category: str = "construction"


@app.post("/api/catalogue-search")
def catalogue_search(request: CatalogueRequest):
    return unified_search(request.requirement, request.category)

@app.post("/api/tender/upload")
def review_tender_pdf(file: UploadFile = File(...)):
    from io import BytesIO
    from pypdf import PdfReader
    try:
        if not (file.filename or "").lower().endswith(".pdf"):
            raise HTTPException(422, "Upload a searchable PDF file only.")
        content = file.file.read(MAX_BYTES + 1)
        if not content or len(content) > MAX_BYTES:
            raise HTTPException(422, "Choose a nonempty PDF of up to 10 MB.")
        try:
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted:
                raise ValueError("Upload an unlocked, searchable PDF.")
            if not 1 <= len(reader.pages) <= 50:
                raise ValueError("Upload a PDF containing 1 to 50 pages.")
            pages = []
            total = 0
            for number, page in enumerate(reader.pages, 1):
                value = (page.extract_text() or "").strip()
                if sum(c.isalnum() for c in value) < 30:
                    raise ValueError(
                        f"Page {number} has insufficient selectable text. "
                        "Upload a searchable PDF; remove blank or image-only pages. OCR is disabled."
                    )
                pages.append(value)
                total += len(value)
                if total > 100000:
                    raise ValueError("Upload a shorter tender section: maximum 100,000 characters.")
            items = split_requirements("\n\n".join(pages))
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        except Exception as error:
            raise HTTPException(422, "Could not read this PDF. Upload an unlocked, searchable PDF.") from error
        if not items:
            raise HTTPException(422, "No tender requirements could be extracted.")
        if app.state.catalogue is None:
            raise HTTPException(503, "Catalogue unavailable. Check PostgreSQL.")
        output = []
        skipped = 0
        for item in items:
            product = recommendation_text(item)
            citations = audit_citations(item, app.state.citation_snapshot)
            hints = indicated_categories(product)
            # Exclude only short heading-like fragments without citations.
            if not hints and not citations and len(re.findall(r"[A-Za-z]+", product)) < 4:
                skipped += 1
                continue
            searches = {
                category: unified_search(product, category)
                for category in CATEGORY_LABELS
                if len(product.strip()) >= 2
            }
            matches = {
                category: result
                for category, result in searches.items()
                if result.get("standards")
            }
            if len(matches) == 1:
                category, result = next(iter(matches.items()))
            elif len(hints) == 1:
                category = next(iter(hints))
                result = searches.get(category) or {
                    "standards": [], "message": "Add a product description for this citation."
                }
            else:
                category = "unresolved"
                result = {
                    "standards": [],
                    "message": "No sufficiently supported recommendation for this requirement.",
                    "clarification_question": (
                        "This item may describe several products or applications. "
                        "Clarify it using the Standard Checker."
                        if len(hints) > 1 or len(matches) > 1
                        else "Specify the product, material and intended use using the Standard Checker."
                    ),
                }
            output.append({"requirement": item, "category": category,
                           "citation_checks": citations, "recommendations": result})
        if not output:
            raise HTTPException(422, "No product requirements detected. Upload a PDF with product specifications.")
        response = {
            "items": output,
            "source_document": (file.filename or "tender.pdf").replace("\\", "/").split("/")[-1],
            "limitations": (
                "Automatically extracted requirements were searched across Construction, Electrical and Plumbing. "
                "PDF tables, reading order and embedded images may be incomplete. "
                "Category routing and recommendations are provisional; technical applicability is unverified. "
                "Citation checks use a limited older snapshot."
            ),
            "skipped_short_fragments": skipped,
        }
        try:
            response["report_id"] = save_report(response, response["source_document"])
        except ValueError as error:
            response["report_notice"] = str(error)
        return response
    finally:
        file.file.close()
