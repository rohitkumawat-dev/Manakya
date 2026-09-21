import { useState } from "react";

export default function App() {
  const [requirement, setRequirement] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const [extracting, setExtracting] = useState(false);
  const [documentInfo, setDocumentInfo] = useState(null);

  async function handleUpload(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setError("");
    if (file.size > 10 * 1024 * 1024) {
      setError("Choose a file smaller than 10 MB.");
      return;
    }
    setExtracting(true);
    setResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch("http://127.0.0.1:8000/api/extract-document", {
        method: "POST", body: form,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Document extraction failed.");
      setRequirement(data.text);
      setDocumentInfo(data);
    } catch (err) {
      setError(err instanceof TypeError ? "Cannot reach the backend. Check that it is running." : err.message);
    } finally {
      setExtracting(false);
    }
  }

  async function handleAnalyze(event) {
    event.preventDefault();
    setError("");
    setResult(null);

    if (requirement.trim().length < 2 || requirement.trim().length > 5000) {
      setError("Enter a requirement between 2 and 5,000 characters. For a long document, keep the relevant product specification excerpt.");
      return;
    }

    setLoading(true);

    try {
      const response = await fetch(
        "http://127.0.0.1:8000/api/analyze",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            requirement: requirement.trim(),
          }),
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : "Could not process your requirement."
        );
      }

      setResult(data);
    } catch (err) {
      setError(
        err instanceof TypeError
          ? "Cannot reach the backend. Check that it is running."
          : err.message
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main>
      <span className="badge">STANDARDS INTELLIGENCE</span>
      <h1>Velocia<span>.</span></h1>
      <p>Find the right Indian Standards for your procurement.</p>

      <section aria-label="Document upload">
        <label htmlFor="document">Upload a specification (PDF, DOCX or TXT)</label>
        <input id="document" type="file" accept=".pdf,.docx,.txt"
          disabled={loading || extracting} onChange={handleUpload} />
        <p><small>Up to 10 MB; PDFs up to 50 pages. Text extraction only; scanned documents require OCR.</small></p>
        {extracting && <p role="status">Extracting document text…</p>}
        {documentInfo && <div role="status">
          <p>Loaded {documentInfo.filename}. Review and edit the text below before submitting.</p>
          {documentInfo.warnings.map((warning, i) => <p key={i}><small>{warning}</small></p>)}
        </div>}
      </section>
      <form onSubmit={handleAnalyze}>
        <label htmlFor="requirement">
          What are you procuring?
        </label>

        <textarea
          id="requirement"
          placeholder="Example: We need Portland pozzolana cement made with fly ash."
          value={requirement}
          onChange={(event) => setRequirement(event.target.value)}
          minLength={2}
          required
          disabled={loading || extracting}
        />

        <p><small>{requirement.length} / 5,000 characters for analysis.
          {requirement.length > 5000 && " Keep a relevant excerpt before submitting. The full document is not automatically analyzed."}
          {" "}For documents covering multiple products, analyze each product requirement separately.
        </small></p>
        <button type="submit" disabled={loading || extracting || requirement.length > 5000}>
          {loading ? "Submitting..." : "Submit requirement →"}
        </button>
      </form>

      {error && <div className="error" role="alert">{error}</div>}

      {result && (
  <section className="status" aria-live="polite">
    <strong>{result.message}</strong>
    {result.clarification_question && (
      <div role="status">
        <p>{result.clarification_question}</p>
        <p><small>Add the details to your requirement above and submit again.</small></p>
      </div>
    )}
    {result.corrections?.length > 0 && (
  <p>
    Searching for: <strong>{result.searched_requirement}</strong>
  </p>
)}

    {(result.standards ?? []).map((standard) => (
      <article className="standard-card" key={standard.standard_id ?? standard.is_number}>
        <span className="badge">POTENTIAL MATCH</span>
        <h2>{standard.is_number}</h2>
        <p>{standard.title}</p>
        <p>{standard.reason}</p>
        <p>
  <small>
    Semantic similarity: {typeof standard.similarity === "number" ? standard.similarity.toFixed(4) : "Unavailable"}
    {" · "}Not a confidence percentage
  </small>
</p>
        {standard.scope_summary && (
          <p><strong>Scope:</strong> {standard.scope_summary}</p>
        )}
        <p><small>{standard.scope_verified
          ? "Scope checked against recorded evidence."
          : "Scope evidence has not yet been verified."}</small></p>

        <details>
          <summary>Revisions and amendments</summary>
          {(standard.revision_check?.warnings ?? []).map((warning, i) => (
            <p key={i}>{warning}</p>
          ))}
          <ul>
            {(standard.amendments ?? []).map((amendment, i) => (
              <li key={i}>{amendment.amendmentLabel ?? "Amendment"}
                {amendment.amendmentYear ? ` · ${amendment.amendmentYear}` : ""}</li>
            ))}
          </ul>
          {!standard.amendments?.length && (
            <p>No amendment records available here; this does not establish that none exist.</p>
          )}
        </details>

        <details>
          <summary>Certification evidence</summary>
          <p>BIS metadata: <strong>{standard.certification_check?.bis_metadata_label ?? "Unknown"}</strong></p>
          <p>{standard.certification_check?.message ?? "Certification applicability has not been verified."}</p>
        </details>

        <details>
          <summary>Related standards ({standard.related_standards?.length ?? 0})</summary>
          <p>Listed by BIS as cross-references. Applicability and current editions need verification.</p>
          <ul>{(standard.related_standards ?? []).map((ref, i) => (
            <li key={`${ref.is_number}-${i}`}><strong>{ref.is_number ?? "Identifier unavailable"}</strong> — {ref.title}</li>
          ))}</ul>
        </details>

        <details>
          <summary>Referenced by ({standard.referenced_by?.length ?? 0})</summary>
          <ul>{(standard.referenced_by ?? []).map((ref, i) => (
            <li key={`${ref.is_number}-${i}`}><strong>{ref.is_number ?? "Identifier unavailable"}</strong> — {ref.title}</li>
          ))}</ul>
        </details>

        <a
          href="https://standards.bis.gov.in/website/know-your-standards"
          target="_blank"
          rel="noopener noreferrer"
        >
          Search BIS catalogue ↗
        </a>
      </article>
    ))}
  </section>
)}
    </main>
  );
}