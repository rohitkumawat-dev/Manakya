import { useState } from "react";
import TenderReview from "./TenderReview.jsx";

const API = "http://127.0.0.1:8000";
const BIS_CATALOGUE =
  "https://standards.bis.gov.in/website/know-your-standards";

const EXAMPLES = {
  construction: [
    ["Fly ash cement", "We need Portland pozzolana cement made with fly ash."],
    ["White cement", "We need white Portland cement."],
    ["Testing equipment", "We need jolting apparatus for testing cement."],
  ],
  electrical: [
    ["Building cables", "PVC insulated electrical cables for building wiring."],
    ["Circuit breakers", "Circuit breakers for household electrical installations."],
    ["Switches", "Electrical switches for household fixed installations."],
  ],
  plumbing: [
    ["Water pipes", "PVC pipes for drinking water supply."],
    ["Pipe fittings", "Pipe fittings for a building water supply system."],
    ["Water valves", "Valves for water supply installations."],
  ],
};

function dateLabel(value) {
  if (!value) return "Not recorded";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not recorded";

  return date.toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

async function post(path, body) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), body instanceof FormData ? 100000 : 60000);

  try {
    const isFile = body instanceof FormData;

    const response = await fetch(`${API}${path}`, {
      method: "POST",
      headers: isFile
        ? undefined
        : { "Content-Type": "application/json" },
      body: isFile ? body : JSON.stringify(body),
      signal: controller.signal,
    });

    let data;

    try {
      data = await response.json();
    } catch {
      throw new Error(
        `The backend returned an unexpected response (HTTP ${response.status}).`
      );
    }

    if (!response.ok) {
      throw new Error(
        typeof data.detail === "string"
          ? data.detail
          : "Could not process this request."
      );
    }

    return data;
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("The request took too long. Please try again.");
    }

    if (error instanceof TypeError) {
      throw new Error(
        "Cannot reach the backend. Check that it is running."
      );
    }

    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

function References({ records = [] }) {
  if (!records.length) return <p>No records available.</p>;

  return (
    <ul className="reference-list">
      {records.map((record, index) => (
        <li key={`${record.is_number}-${index}`}>
          <strong>
            {record.is_number || "Identifier unavailable"}
          </strong>
          <span>{record.title}</span>
        </li>
      ))}
    </ul>
  );
}


function RankSummary({ standard, rank }) {
  const value = standard.similarity;
  const valid = typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
  const score = valid ? Math.round(value * 100) : null;
  return <div className="rank-summary">
    <div className="rank-position" aria-label={`Result rank ${rank}`}>{rank}</div>
    <div className="rank-score" title="Semantic text similarity, not probability of correctness. Ranking may also use category and product rules.">
      <strong>{standard.exact_match ? "Exact code" : score === null ? "—" : `${score}%`}</strong>
      <span>{standard.exact_match ? "Identifier match" : score === null ? "Score unavailable" : "Text similarity"}</span>
    </div>
    <span className="rank-type">{standard.standard_type || (standard.standard_role && standard.standard_role !== "unclassified" ? standard.standard_role.replaceAll("_", " ") : "Type not recorded")}</span>
  </div>;
}

function CatalogueCard({ standard, rank }) {
  const [copyMessage, setCopyMessage] = useState("");

  async function copyNumber() {
    try {
      await navigator.clipboard.writeText(standard.is_number);
      setCopyMessage("IS number copied.");
    } catch {
      setCopyMessage(
        "Select the IS number above and copy it manually."
      );
    }
  }

  return (
    <article className="standard-card ranked-result">
      <RankSummary standard={standard} rank={rank} />
      <span className="match-label">
        Catalogue candidate · Details not checked
      </span>

      <h3>{standard.is_number}</h3>
      <p className="standard-title">{standard.title}</p>
      <p className="rank-scope">{standard.scope_summary || "Scope summary not available in the collected data."}</p>

      {standard.reason && (
        <div className="reason-box">{standard.reason}</div>
      )}

      <p className="fine-print">
        Catalogue data retrieved: {dateLabel(standard.retrieved_at)}
        <br />
        Category assignment is provisional. Verify the scope and
        current edition on BIS before using this in a tender.
      </p>

      <div className="card-footer">
        <button
          type="button"
          className="text-button"
          onClick={copyNumber}
        >
          Copy IS number
        </button>

        <a
          href={BIS_CATALOGUE}
          target="_blank"
          rel="noopener noreferrer"
        >
          Open BIS catalogue ↗
        </a>
      </div>

      <p className="fine-print" role="status">
        {copyMessage}
      </p>
    </article>
  );
}


function StandardCard({ standard, rank }) {
  if (standard.record_level === "catalogue") {
    return <CatalogueCard standard={standard} rank={rank} />;
  }

  return (
    <article className="standard-card ranked-result">
      <RankSummary standard={standard} rank={rank} />
     <span className="match-label">
  {standard.exact_match
    ? "Exact identifier"
    : "Potential match"}
  {standard.category_verified
    ? " · Category reviewed"
    : ""}
</span>

<p className="fine-print">
  {standard.standard_role &&
    standard.standard_role !== "unclassified" && (
      <>
        Standard role:{" "}
        {standard.standard_role.replaceAll("_", " ")}
        {" · "}
      </>
    )}
  Technical applicability and current edition require verification.
</p>

      <h3>{standard.is_number}</h3>
      <p className="standard-title">{standard.title}</p>
      <p className="rank-scope">{standard.scope_summary || "Scope summary not available in the collected data."}</p>

      {standard.reason && (
        
        <div className="reason-box">{standard.reason}</div>
      )}

      <dl className="record-dates">
        <div>
          <dt>Data retrieved on</dt>
          <dd>{dateLabel(standard.retrieved_at)}</dd>
        </div>
        <div>
          <dt>Reaffirmation recorded</dt>
          <dd>{dateLabel(standard.reaffirmation_date)}</dd>
        </div>
        <div>
          <dt>Amendments checked</dt>
          <dd>{dateLabel(standard.amendments_checked_at)}</dd>
        </div>
      </dl>

      <p className="fine-print">
        Retrieval dates show when our data was collected, not when
        BIS last changed the standard.
      </p>

      <details>
        <summary>Scope and applicability</summary>
        <p>
          {standard.scope_summary ||
            "A scope summary is not available yet."}
        </p>
        <p className="fine-print">
          {standard.scope_verified
            ? "Scope checked against recorded evidence."
            : "Scope evidence has not yet been verified."}
        </p>
      </details>

      <details>
        <summary>Revisions and amendments</summary>

        {(standard.revision_check?.warnings ?? []).map(
          (warning, index) => <p key={index}>{warning}</p>
        )}

        {standard.amendments?.length ? (
          <ul>
            {standard.amendments.map((item, index) => (
              <li key={index}>
                {item.amendmentLabel || "Amendment"}
                {item.amendmentYear
                  ? ` · ${item.amendmentYear}`
                  : ""}
              </li>
            ))}
          </ul>
        ) : (
          <p>
            No amendment records available here. This does not
            establish that none exist.
          </p>
        )}
      </details>

      <details>
        <summary>Certification evidence</summary>
        <p>
          BIS Certification:{" "}
          <strong>
            {standard.certification_check?.bis_metadata_label ||
              "Unknown"}
          </strong>
        </p>
        <p>
          {standard.certification_check?.message ||
            "Certification applicability has not been verified."}
        </p>
      </details>

      <details>
        <summary>
          Related standards (
          {standard.related_standards?.length ?? 0})
        </summary>
        <p className="fine-print">
          BIS cross-references; applicability and current editions
          need verification.
        </p>
        <References records={standard.related_standards ?? []} />
      </details>

      <details>
        <summary>
          Referenced by ({standard.referenced_by?.length ?? 0})
        </summary>
        <References records={standard.referenced_by ?? []} />
      </details>

      
      
      <div className="card-footer">
        <small>
          Similarity:{" "}
          {typeof standard.similarity === "number"
            ? standard.similarity.toFixed(3)
            : "Unavailable"}
          {" · "}Not a confidence score
        </small>

        <a
          href={BIS_CATALOGUE}
          target="_blank"
          rel="noopener noreferrer"
        >
          BIS catalogue ↗
        </a>
      </div>
    </article>
  );
}

export default function App() {
  const [category, setCategory] = useState("construction");
  const [requirement, setRequirement] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [documentInfo, setDocumentInfo] = useState(null);
  const [mode, setMode] = useState("search");
  const [elapsed, setElapsed] = useState(null);
  const [reviewBusy, setReviewBusy] = useState(false);

  const validLength =
    requirement.trim().length >= 2 &&
    requirement.trim().length <= 5000;

  function updateText(text) {
    setRequirement(text);
    setResult(null);
    setError("");
    setElapsed(null);
  }

  function changeCategory(event) {
    setCategory(event.target.value);
    setResult(null);
    setError("");
    setElapsed(null);
    setMode("search");
  }

  async function runSearch() {
  const text = requirement.trim();

  if (text.length < 2 || text.length > 5000) {
    setError("Enter between 2 and 5,000 characters.");
    return;
  }

  setBusy("search");
  setError("");
  setResult(null);
  setElapsed(null);

  const started = performance.now();

  try {
    const data = await post("/api/analyze", {
      requirement: text,
      category,
    });

    setResult(data);
    setElapsed(
      ((performance.now() - started) / 1000).toFixed(1)
    );
  } catch (err) {
    setError(err.message || "Search failed. Please try again.");
  } finally {
    setBusy("");
  }
}

  function analyze(event) {
    event.preventDefault();
    runSearch();
  }


  return (
    <main className="velocia-app">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Velocia home">
          <span className="brand-symbol">V</span>
          Velocia<span className="brand-dot">.</span>
        </a>

        <span className="topbar-caption">
          Indian Standards, made clearer
        </span>
      </header>

      <section
        className="checker-panel"
        aria-labelledby="checker-title"
      >
        <div className="checker-heading">
          <div>
            <p className="eyebrow">
              FROM REQUIREMENT TO RELEVANT STANDARDS
            </p>
            <h1 id="checker-title">Standard Checker</h1>
          </div>

          <div className="category-control" hidden={mode !== "search"}>
            <label htmlFor="category">Category</label>
            <select
              id="category"
              value={category}
              disabled={(!!busy || reviewBusy)}
              onChange={changeCategory}
            >
              <option value="construction">Construction</option>
              <option value="electrical">
                Electrical Equipment
              </option>
              <option value="plumbing">Pipes & Plumbing</option>
            </select>
          </div>
        </div>

        <p className="intro">
          Use Standard Checker for a single product, or Review tender to upload a searchable PDF.
        </p>


        <div className="mode-tabs" aria-label="Checker mode">
          <button
            type="button"
            aria-pressed={mode === "search"}
            onClick={() => setMode("search")}
            disabled={(!!busy || reviewBusy)}
          >
            Find standards
          </button>

          <button
            type="button"
            aria-pressed={mode === "tender"}
            onClick={() => setMode("tender")}
            disabled={(!!busy || reviewBusy)}
            title="Review tender requirements across all three categories."
          >
            Review tender
</button>
        </div>

        <div hidden={mode !== "search"}>
        <form onSubmit={analyze}>
          <label className="sr-only" htmlFor="requirement">
            Your procurement requirement
          </label>

          <textarea
            id="requirement"
            value={requirement}
            onChange={(event) => updateText(event.target.value)}
            placeholder={EXAMPLES[category][0][1]}
            disabled={(!!busy || reviewBusy)}
          />

          <div className="input-meta">
            <span>
              {requirement.length.toLocaleString()} characters
            </span>

            <button
              type="button"
              className="text-button"
              disabled={(!!busy || reviewBusy) || !requirement}
              onClick={() => {
                updateText("");
                setDocumentInfo(null);
              }}
            >
              Clear
            </button>
          </div>

          <div className="checker-actions">


            {mode === "search" && (
              <button
                className="primary-button"
                type="submit"
                disabled={(!!busy || reviewBusy) || !validLength}
              >
                {busy === "search"
                  ? "Finding standards…"
                  : "Find standards ↗"}
              </button>
            )}
          </div>
        </form>

        <p className="fine-print">
          Describe the product, material and intended use.
          {requirement.length > 5000 && " Use Review tender to split long text into individual requirements."}
        </p>

        {documentInfo && (
          <div className="document-note" role="status">
            <strong>{documentInfo.filename}</strong>
            <p>Extraction: {documentInfo.extraction_method || "text"}. Check the wording, units and IS numbers before submitting.</p>

            {(documentInfo.warnings ?? []).map(
              (warning, index) => <p key={index}>{warning}</p>
            )}
          </div>
        )}

        <div className="example-row">
          <span>Try an example</span>

          {EXAMPLES[category].map(([label, text]) => (
            <button
              key={label}
              type="button"
              disabled={(!!busy || reviewBusy)}
              onClick={() => {
                updateText(text);
                setDocumentInfo(null);
                setMode("search");
              }}
            >
              {label}
            </button>
          ))}
        </div>
        </div>
      </section>

      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}

            <div
        hidden={mode !== "tender"}
        className="tender-container"
      >
        <TenderReview
          onBusyChange={setReviewBusy}
          disabled={!!busy}
        />
      </div>

      {mode === "search" && (
        <section
          className="results-section"
          aria-label="Search results"
        >
          <div className="results-heading">
            <h2>Recommendations</h2>
            {elapsed && <span>Completed in {elapsed}s</span>}
          </div>

          <div
            aria-live="polite"
            aria-busy={busy === "search"}
          >
            {busy === "search" ? (
              <div className="empty-state">
                <span className="spinner" aria-hidden="true" />
                <p>
                  Matching your requirement to the available
                  standards…
                </p>
              </div>
            ) : result ? (
              <>
                <p className="result-message">{result.message}</p>

                {result.clarification_question && (
                  <div className="document-note">
                    {result.clarification_question}
                    <p>
                      Add the details to your requirement above and
                      search again.
                    </p>
                  </div>
                )}

                {!!result.corrections?.length && (
                  <p className="fine-print">
                    Searching for: {result.searched_requirement}
                  </p>
                )}

                {(result.standards ?? []).map((standard, index) => (
                  <StandardCard
                    rank={index + 1}
                    key={
                      standard.standard_id ?? standard.is_number
                    }
                    standard={standard}
                  />
                ))}

                {category === "construction" &&
                  result.search_method !== "local_catalogue_search" &&
                  !result.clarification_question && (
                    <button
                      type="button"
                      className="upload-button"
                      disabled={(!!busy || reviewBusy) || !validLength}
                      onClick={() => runSearch(true)}
                    >
                      Search wider catalogue ↗
                    </button>
                  )}

                {!result.standards?.length &&
                  !result.clarification_question && (
                    <div className="empty-state">
                      <h3>No suitable candidate found here.</h3>
                      <p>
                        Our collected catalogue has limited coverage.
                        Try a more specific requirement or search BIS.
                      </p>
                      <a
                        href={BIS_CATALOGUE}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        Open BIS catalogue ↗
                      </a>
                    </div>
                  )}
              </>
            ) : (
              <div className="empty-state">
                <span className="empty-symbol" aria-hidden="true">
                  ↗
                </span>
                <h3>Your next standard starts here.</h3>
                <p>
                  Select a category and enter a requirement to see
                  potential matches and available evidence.
                </p>
              </div>
            )}
          </div>
        </section>
      )}

      <footer className="page-footer">
        <span>
          Velocia · Standards recommendation prototype
        </span>
        <span>
          Selected coverage across three categories · Verify before
          tender use
        </span>
      </footer>
    </main>
  );
}