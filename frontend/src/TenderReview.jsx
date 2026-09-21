import { useEffect, useRef, useState } from "react";

const API = "http://127.0.0.1:8000";


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

export default function TenderReview({ disabled, onBusyChange }) {
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [filename, setFilename] = useState("");
  const [dragging, setDragging] = useState(false);
  const input = useRef(null);
  const pending = useRef(null);
  const locked = !!busy || disabled;

  useEffect(() => () => pending.current?.abort(), []);
  useEffect(() => {
    onBusyChange?.(!!busy);
    return () => onBusyChange?.(false);
  }, [busy, onBusyChange]);

  async function run(operation, task) {
    if (pending.current || disabled) return;
    const controller = new AbortController();
    pending.current = controller;
    setBusy(operation);
    setError("");
    const timeout = setTimeout(() => controller.abort(), 120000);
    try {
      await task(controller.signal);
    } catch (err) {
      setError(err.name === "AbortError"
        ? "The request timed out. Try a shorter tender PDF."
        : err.message || "Could not reach the backend.");
    } finally {
      clearTimeout(timeout);
      pending.current = null;
      setBusy("");
    }
  }

  async function check(response) {
    if (response.ok) return;
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === "string" ? data.detail : "The request failed. Please try again.");
  }

  function upload(files) {
    if (locked || pending.current || !files.length) return;
    setResult(null);
    setError("");
    if (files.length !== 1) return setError("Choose one PDF at a time.");
    const file = files[0];
    if (!file.name.toLowerCase().endsWith(".pdf")) return setError("Upload a searchable PDF only. Images are not supported.");
    if (!file.size || file.size > 10 * 1024 * 1024) return setError("Choose a nonempty PDF of up to 10 MB.");
    setFilename(file.name);
    run("review", async (signal) => {
      const body = new FormData();
      body.append("file", file);
      const response = await fetch(`${API}/api/tender/upload`, { method: "POST", body, signal });
      await check(response);
      setResult(await response.json());
    });
  }

  function exportPdf() {
    if (!result?.report_id) return;
    run("export", async (signal) => {
      const response = await fetch(`${API}/api/reports/${encodeURIComponent(result.report_id)}/pdf`, { signal });
      await check(response);
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = "Velocia-tender-report.pdf";
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    });
  }

  return (
    <section className="status" aria-label="Tender review">
      <h2>Review your tender</h2>
      <p>Upload a searchable PDF. We check its requirements across Construction, Electrical and Plumbing automatically.</p>
      <div className={`tender-dropzone${dragging ? " is-dragging" : ""}`}
        onDragOver={(event) => { event.preventDefault(); if (!locked) setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => { event.preventDefault(); setDragging(false); upload(event.dataTransfer.files); }}>
        <p>Drop your tender PDF here</p>
        <button type="button" className="upload-button" disabled={locked} onClick={() => input.current?.click()}>
          Choose PDF
        </button>
        <input ref={input} type="file" accept=".pdf,application/pdf" hidden disabled={locked}
          onChange={(event) => { upload(event.target.files); event.target.value = ""; }} />
        <p className="fine-print">PDF only · Up to 10 MB · Selectable text required · No scanned documents</p>
      </div>
      {busy === "review" && <p role="status">Reviewing {filename} across all three categories…</p>}
      {error && <p role="alert">{error}</p>}
      {result && <div aria-live="polite">
        <div className="report-export-bar">
          <div><h3>Recommended IS codes</h3><p>{result.source_document}</p></div>
          <button type="button" className="primary-button" disabled={locked || !result.report_id} onClick={exportPdf}>
            {busy === "export" ? "Preparing PDF…" : "Export detailed PDF"}
          </button>
        </div>
        {result.report_notice && <p role="alert">{result.report_notice}</p>}
        <p className="fine-print">{result.limitations}</p>
        {(result.items ?? []).map((item, index) => {
          const recommendation = item.recommendations ?? {};
          return <article className="standard-card" key={index}>
            <span className="match-label">{item.category === "unresolved" ? "Needs clarification" : item.category} · Item {index + 1}</span>
            <p>{recommendation.message}</p>
            {recommendation.clarification_question && <p className="reason-box">{recommendation.clarification_question}</p>}
            {(recommendation.standards ?? []).map((standard, i) => <div className="ranked-result tender-ranked-result" key={`${standard.is_number}-${i}`}>
              <RankSummary standard={standard} rank={i + 1} />
              <h3>{standard.is_number}</h3>
              <p>{standard.title}</p>
              <p className="reason-box">{standard.reason || "Potential candidate. Technical applicability needs review."}</p>
              <p className="fine-print">Data retrieved: {standard.retrieved_at || "Not recorded"}</p>
              <details><summary>Evidence and limitations</summary>
                <p>{standard.scope_summary || "No scope summary available."}</p>
                {(standard.revision_check?.warnings ?? []).map((warning, j) => <p key={j}>{warning}</p>)}
                <p>{standard.certification_check?.message}</p>
              </details>
            </div>)}
          </article>;
        })}
      </div>}
    </section>
  );
}
