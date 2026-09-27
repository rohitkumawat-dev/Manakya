import { useEffect, useRef, useState } from "react";
import "./index.css";

const API = (import.meta.env?.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const BIS = "https://standards.bis.gov.in/website/know-your-standards";
const HISTORY_KEY = "specgyan-session-history-v1";
const CATEGORIES = { construction: "Construction", electrical: "Electrical", plumbing: "Plumbing" };
const EXAMPLES = {
  construction: [["Fly ash cement", "Portland pozzolana cement made with fly ash."], ["White cement", "White Portland cement for architectural finishes."], ["Cement testing", "Jolting apparatus used for testing cement."]],
  electrical: [["Building cables", "PVC insulated electrical cables for building wiring."], ["Circuit breakers", "AC circuit breakers for household electrical installations."], ["Electrical switches", "Electrical switches for household fixed installations."]],
  plumbing: [["Drinking water pipes", "Unplasticized PVC pipes for potable water supplies."], ["Hot water pipes", "CPVC pipes for potable hot and cold water distribution."], ["Water storage tanks", "Rotational moulded polyethylene water storage tanks."]],
};

function Icon({ name = "arrow", size = 20, ...props }) {
  const paths = {
    arrow: <path d="M5 12h14m-6-6 6 6-6 6" />,
    search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></>,
    upload: <><path d="M12 16V3m-5 5 5-5 5 5M4 16v4h16v-4" /></>,
    file: <><path d="M14 3H5v18h14V8l-5-5Z" /><path d="M14 3v5h5M8 12h8m-8 4h6" /></>,
    close: <path d="m6 6 12 12M6 18 18 6" />,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    external: <><path d="M14 3h7v7m0-7L10 14M10 5H4v15h15v-6" /></>,
    grid: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    copy: <><rect x="8" y="8" width="12" height="13" rx="2" /><path d="M16 8V3H3v13h5" /></>,
    building: <><path d="M4 21V5h10v16m0-12h6v12M2 21h20M7 9h4m-4 4h4m-4 4h4m6-4h1m-1 4h1" /></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths[name] || paths.arrow}</svg>;
}
function date(value) {
  if (value === null || value === undefined || value === "") return "Not recorded";
  if (/^\d{4}$/.test(String(value))) return String(value);
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "Not recorded" : d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}
function sourceUrl(value) {
  try { const u = new URL(value); return u.protocol === "https:" ? u.href : BIS; } catch { return BIS; }
}
function route() { const key = window.location.hash.slice(1).split("?")[0]; return ["find", "tender", "history"].includes(key) ? key : "home"; }
function loadHistory() {
  try {
    const data = JSON.parse(sessionStorage.getItem(HISTORY_KEY) || "[]");
    return Array.isArray(data) ? data.filter(x => x && typeof x.id === "string" && typeof x.query === "string" && x.result && ["search", "tender"].includes(x.type)).slice(0, 12) : [];
  } catch { return []; }
}
async function request(path, options, timeout = 60000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(`${API}${path}`, { ...options, signal: controller.signal });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(typeof data.detail === "string" ? data.detail : `Request failed (${response.status}). Please try again.`);
    }
    return response;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("This request took too long. Please try again with a shorter requirement or PDF.");
    if (error instanceof TypeError) throw new Error("Cannot reach the backend. Check that it is running on port 8000.");
    throw error;
  } finally { clearTimeout(timer); }
}

function Modal({ children, titleId, close, wide = false }) {
  const ref = useRef(null);
  useEffect(() => {
    const dialog = ref.current;
    const previous = document.activeElement;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.showModal();
    return () => { dialog.close(); document.body.style.overflow = overflow; previous?.focus?.(); };
  }, []);
  return <dialog ref={ref} className={`sg-modal ${wide ? "sg-modal-wide" : ""}`} aria-labelledby={titleId}
    onCancel={e => { e.preventDefault(); close(); }} onClick={e => { if (e.target === ref.current) { const b = ref.current.getBoundingClientRect(); if (e.clientX < b.left || e.clientX > b.right || e.clientY < b.top || e.clientY > b.bottom) close(); } }}>
    <button className="sg-icon-button sg-modal-close" onClick={close} aria-label="Close dialog"><Icon name="close" /></button>
    {children}
  </dialog>;
}
function StandardDialog({ standard: s, close }) {
  const m = s.manual_details || {};
  const [copied, setCopied] = useState("");
  const count = m.amendment_count_as_shown ?? s.revision_check?.amendment_count ?? s.amendment_count_raw;
  const manualYear = m.reaffirmation_year_as_shown;
  const conflict = manualYear != null && s.reaffirmation_date && String(s.reaffirmation_date).slice(0, 4) !== String(manualYear);
  async function copy() { try { await navigator.clipboard.writeText(s.is_number); setCopied("Code copied"); } catch { setCopied("Select the code above to copy it."); } }
  return <Modal close={close} titleId="standard-dialog-title" wide>
    <div className="sg-dialog-head"><span className="sg-kicker">STANDARD OVERVIEW</span><h2 id="standard-dialog-title">{s.is_number}</h2><p>{s.title}</p></div>
    <dl className="sg-detail-list">
      <div><dt>Scope</dt><dd>{s.scope_summary || m.scope_text || "Open the BIS source to review the scope for this standard."}</dd></div>
      <div className="sg-detail-highlight"><dt>Why recommended</dt><dd>{s.why_recommended || "The standard title is related to your description. Review its scope for the intended use."}</dd></div>
      <div><dt>Amendments</dt><dd>{count !== null && count !== undefined && count !== "" ? `${count} listed` : "Not recorded"}
        {Array.isArray(s.amendments) && s.amendments.length > 0 && <ul>{s.amendments.map((a, i) => <li key={i}>{a.amendmentLabel || "Amendment"}{a.amendmentYear ? ` · ${a.amendmentYear}` : ""}</li>)}</ul>}</dd></div>
      <div><dt>Reaffirmed</dt><dd>{date(manualYear ?? s.reaffirmation_date)}{conflict && <span className="sg-source-conflict">Scope source: {manualYear}; catalogue: {date(s.reaffirmation_date)}. Confirm the current reaffirmation on BIS.</span>}</dd></div>
      {(m.standard_type || s.standard_type) && <div><dt>Standard type</dt><dd>{m.standard_type || s.standard_type}</dd></div>}
      {m.status_as_shown && <div><dt>Status shown</dt><dd>{m.status_as_shown}</dd></div>}
      {m.certification_as_shown && <div><dt>Certification</dt><dd>{m.certification_as_shown}<span className="sg-detail-note">Applicability depends on the product and relevant order.</span></dd></div>}
      {m.replacement_standard && <div><dt>Replacement</dt><dd>{m.replacement_standard}</dd></div>}
      {s.scope_checked_on && <div><dt>Source checked on</dt><dd>{date(s.scope_checked_on)}</dd></div>}
      {s.retrieved_at && <div><dt>Catalogue retrieved</dt><dd>{date(s.retrieved_at)}</dd></div>}
    </dl>
    {(s.related_standards?.length > 0 || s.referenced_by?.length > 0) && <details className="sg-related"><summary>Related standards and references</summary>{[...(s.related_standards || []), ...(s.referenced_by || [])].map((r,i) => <p key={i}><strong>{r.is_number || r.standardNumber}</strong> {r.title || r.standardName}</p>)}</details>}
    <p className="sg-dialog-note">Confirm technical applicability and the current edition before citing a standard in a tender.</p>
    <div className="sg-dialog-actions"><button className="sg-button sg-secondary" onClick={copy}><Icon name="copy" size={17} /> Copy IS code</button><a className="sg-button sg-primary" href={sourceUrl(s.scope_source_url)} target="_blank" rel="noopener noreferrer">View BIS source <Icon name="external" size={16} /></a></div>
    <span className="sg-copy-status" role="status">{copied}</span>
  </Modal>;
}
function Results({ result, open }) {
  if (!result) return null;
  const standards = Array.isArray(result.standards) ? result.standards : [];
  return <div className="sg-results">
    {result.clarification_question && <div className="sg-notice"><strong>A little more detail will help.</strong><p>{result.clarification_question}</p></div>}
    {result.corrections?.length > 0 && <p className="sg-muted sg-small">Searching for: {result.searched_requirement}</p>}
    {standards.length ? <><div className="sg-result-heading"><h2>Recommended standards <span>{standards.length}</span></h2><p>Select a code to explore its details.</p></div><div className="sg-result-list">{standards.map((s,i) => <button key={`${s.standard_id || s.is_number}-${i}`} className="sg-result" onClick={() => open(s)}><span><strong>{s.is_number}</strong><span className="sg-result-title">{s.title}</span></span><Icon name="arrow" /></button>)}</div></> : !result.clarification_question && <div className="sg-empty"><Icon name="search" size={26} /><h3>No suitable standard found</h3><p>{result.message || "Try adding the material and intended use, or explore the BIS catalogue."}</p><a href={BIS} target="_blank" rel="noopener noreferrer">Explore BIS catalogue ↗</a></div>}
  </div>;
}
function Preview() {
  const [kind, setKind] = useState("find");
  return <section className="sg-preview" aria-label="Product preview">
    <div className="sg-preview-toolbar"><span className="sg-preview-label"><span className="sg-status-dot" /> A closer look at SpecGyan</span><div className="sg-preview-tabs" aria-label="Preview mode"><button aria-pressed={kind === "find"} onClick={() => setKind("find")}>Find a standard</button><button aria-pressed={kind === "tender"} onClick={() => setKind("tender")}>Review a tender</button></div></div>
    <div className="sg-preview-body"><div className="sg-preview-copy"><span className="sg-kicker">{kind === "find" ? "FROM DESCRIPTION TO DIRECTION" : "FROM DOCUMENT TO REQUIREMENTS"}</span><h2>{kind === "find" ? <>Less searching.<br />More understanding.</> : <>One tender.<br />A clearer starting point.</>}</h2><p>{kind === "find" ? "Describe what you need. Explore matching IS codes, read their scope, and understand why they were suggested." : "Upload a tender PDF to review requirements across Construction, Electrical and Plumbing, then export a report."}</p><a href={kind === "find" ? "#find" : "#tender"}>Explore {kind === "find" ? "standards search" : "tender review"} <Icon size={17} /></a></div>
      <div className="sg-preview-window"><div className="sg-window-bar"><div><i /><i /><i /></div><span>Illustrative preview</span></div>{kind === "find" ? <div className="sg-mock-content"><span className="sg-mock-label">YOUR REQUIREMENT</span><div className="sg-mock-input"><Icon name="search" size={18} /><span>Portland pozzolana cement using fly ash</span></div><div className="sg-mock-section"><span>Suggested standard</span><span className="sg-mock-chip">Construction</span></div><div className="sg-mock-result"><Icon name="file" size={27} /><div><strong>IS 1489 (Part 1):2015</strong><p>Portland Pozzolana Cement<br />Part 1: Fly Ash Based</p></div></div><div className="sg-mock-evidence"><span className="sg-evidence-icon"><Icon name="check" size={15} /></span><p><strong>Understand the match</strong><br />Scope, explanation and source in one view.</p></div></div> : <div className="sg-mock-content"><div className="sg-mock-upload"><Icon name="upload" size={27} /><strong>Building-tender.pdf</strong><span>Searchable PDF</span></div><div className="sg-mock-section"><span>Review across three categories</span></div>{Object.values(CATEGORIES).map(x => <div className="sg-mock-category" key={x}><Icon name="file" size={16} />{x}<Icon name="arrow" size={16} /></div>)}</div>}</div>
    </div>
  </section>;
}

export default function App() {
  const [page, setPage] = useState(route);
  const [category, setCategory] = useState("construction");
  const [query, setQuery] = useState("");
  const [result, setResult] = useState(null);
  const [searchBusy, setSearchBusy] = useState(false);
  const searchLock = useRef(false);
  const [searchError, setSearchError] = useState("");
  const [selected, setSelected] = useState(null);
  const [login, setLogin] = useState(false);
  const [history, setHistory] = useState(loadHistory);
  const [historyNotice, setHistoryNotice] = useState("");
  const [tender, setTender] = useState(null);
  const [tenderBusy, setTenderBusy] = useState("");
  const tenderLock = useRef(false);
  const [tenderError, setTenderError] = useState("");
  const [filename, setFilename] = useState("");
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef(null);
  const heading = useRef(null);
  useEffect(() => {
    const change = () => { setPage(route()); setSelected(null); setLogin(false); };
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  useEffect(() => { document.title = `${page === "home" ? "Indian Standards for Procurement" : page === "find" ? "Find Standard" : page === "tender" ? "Upload Tender" : "History"} | SpecGyan`; window.scrollTo({ top: 0 }); heading.current?.focus({ preventScroll: true }); }, [page]);
  function remember(type, queryText, data, cat = null) {
    const entry = { id: `${Date.now()}-${Math.random().toString(36).slice(2)}`, type, query: queryText, category: cat, at: new Date().toISOString(), result: data };
    setHistory(previous => {
      const next = [entry, ...previous].slice(0, 12);
      try { sessionStorage.setItem(HISTORY_KEY, JSON.stringify(next)); } catch { setHistoryNotice("History is available until this page is refreshed; browser storage is unavailable."); }
      return next;
    });
  }
  async function search(text = query) {
    const value = text.trim();
    if (searchLock.current || value.length < 2 || value.length > 5000) return;
    searchLock.current = true; setQuery(value); setSearchBusy(true); setResult(null); setSearchError("");
    try {
      const response = await request("/api/analyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ requirement: value, category }) });
      const data = await response.json(); setResult(data); remember("search", value, data, category);
    } catch (e) { setSearchError(e.message || "Could not complete the search."); }
    finally { searchLock.current = false; setSearchBusy(false); }
  }
  async function upload(files) {
    if (tenderLock.current || !files?.length) return;
    setTenderError("");
    if (files.length !== 1) return setTenderError("Please choose one PDF at a time.");
    const file = files[0];
    if (!/\.pdf$/i.test(file.name)) return setTenderError("Choose a searchable PDF. Images are not supported.");
    if (!file.size || file.size > 10 * 1024 * 1024) return setTenderError("Choose a nonempty PDF no larger than 10 MB.");
    tenderLock.current = true; setTenderBusy("review"); setTender(null); setFilename(file.name);
    try {
      const body = new FormData(); body.append("file", file);
      const response = await request("/api/tender/upload", { method: "POST", body }, 120000);
      const data = await response.json(); setTender(data); remember("tender", file.name, data);
    } catch (e) { setTenderError(e.message || "Could not review this PDF."); }
    finally { tenderLock.current = false; setTenderBusy(""); }
  }
  async function exportPdf() {
    if (!tender?.report_id || tenderLock.current) return;
    tenderLock.current = true; setTenderBusy("export"); setTenderError("");
    try {
      const response = await request(`/api/reports/${encodeURIComponent(tender.report_id)}/pdf`, { method: "GET" });
      const url = URL.createObjectURL(await response.blob());
      const a = document.createElement("a"); a.href = url; a.download = "SpecGyan-tender-report.pdf"; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch (e) { setTenderError(e.message || "Could not export this report."); }
    finally { tenderLock.current = false; setTenderBusy(""); }
  }
  function openHistory(entry) {
    if (searchLock.current || tenderLock.current) return;
    if (entry.type === "search") { setCategory(CATEGORIES[entry.category] ? entry.category : "construction"); setQuery(entry.query); setResult(entry.result); setSearchError(""); window.location.hash = "find"; }
    else { setTender(entry.result); setFilename(entry.query); setTenderError(""); window.location.hash = "tender"; }
  }
  return <div className="sg-app">
    <a className="sg-skip" href="#main-content" onClick={e => { e.preventDefault(); heading.current?.focus(); }}>Skip to content</a>
    <header className="sg-header"><div className="sg-nav-wrap"><a className="sg-brand" href="#home" aria-label="SpecGyan home"><span className="sg-brand-mark"><svg width="25" height="27" viewBox="0 0 25 27" fill="none" aria-hidden="true"><path d="M5 4h15v5H10v4h10v10H5v-5h10v-4H5V4Z" fill="currentColor"/></svg></span><span>SpecGyan<span className="sg-brand-period">.</span></span></a><nav aria-label="Main navigation"><a href="#find" aria-current={page === "find" ? "page" : undefined}>Find Standard</a><a href="#tender" aria-current={page === "tender" ? "page" : undefined}>Upload Tender</a><a href="#history" aria-current={page === "history" ? "page" : undefined}>History</a><button className="sg-login" onClick={() => setLogin(true)}>Login <Icon name="arrow" size={16} /></button></nav></div></header>
    <main id="main-content" className={`sg-main sg-page-${page}`}>
      {page === "home" && <><section className="sg-hero"><h1 ref={heading} tabIndex={-1}>Find the Right Indian Standard<br /><span>Before you Procure.</span></h1><p>Turn product requirements into informed decisions.<br className="sg-desktop-break" /> Discover relevant IS codes and understand what they cover.</p><div className="sg-hero-actions"><a href="#find" className="sg-button sg-primary">Find Standard <Icon name="arrow" size={18} /></a><a href="#tender" className="sg-button sg-secondary"><Icon name="upload" size={18} /> Upload Tender</a></div><div className="sg-hero-categories">Construction<span />Electrical<span />Plumbing</div></section><Preview /><section className="sg-feature-strip" aria-label="Features"><div><Icon name="search" /><span><strong>Search in your own words</strong><p>Start with a product description.</p></span></div><div><Icon name="file" /><span><strong>See the reason behind a match</strong><p>Explore scope and source details.</p></span></div><div><Icon name="upload" /><span><strong>Bring your tender along</strong><p>Review a PDF across three categories.</p></span></div></section></>}
      {page === "find" && <div className="sg-workspace"><section className="sg-page-heading"><span className="sg-kicker">FIND STANDARD</span><h1 ref={heading} tabIndex={-1}>Find Indian Standards applicable<br className="sg-desktop-break" /> to your product description.</h1><p>Tell us what you need, and explore the standards that may apply.</p></section><section className="sg-search-panel" aria-label="Describe your requirement"><form onSubmit={e => { e.preventDefault(); search(); }}><div className="sg-input-heading"><label htmlFor="description">Product description</label><div className="sg-category"><Icon name="grid" size={16} /><label className="sg-sr-only" htmlFor="category">Category</label><select id="category" value={category} disabled={searchBusy} onChange={e => { setCategory(e.target.value); setResult(null); setSearchError(""); }}>{Object.entries(CATEGORIES).map(([key,name]) => <option value={key} key={key}>{name}</option>)}</select></div></div><textarea id="description" placeholder="Describe the product, material and intended use…" value={query} maxLength={5000} disabled={searchBusy} onChange={e => { setQuery(e.target.value); setResult(null); setSearchError(""); }} aria-describedby="description-help" /><div className="sg-textarea-bottom"><span>{query.length.toLocaleString()} / 5,000</span><button type="button" className="sg-text-button" disabled={!query || searchBusy} onClick={() => { setQuery(""); setResult(null); setSearchError(""); }}>Clear</button></div><div className="sg-search-actions"><p id="description-help"><Icon name="file" size={15} /> Include details such as material, voltage or intended use.</p><button className="sg-button sg-primary" disabled={searchBusy || query.trim().length < 2}>{searchBusy ? <><span className="sg-spinner" /> Finding standards</> : <>Find Standard <Icon name="arrow" size={18} /></>}</button></div></form><div className="sg-examples"><span>Try a search</span>{EXAMPLES[category].map(([label,text]) => <button key={label} disabled={searchBusy} onClick={() => search(text)}>{label}<Icon name="arrow" size={14} /></button>)}</div></section>{searchError && <div className="sg-error" role="alert">{searchError}</div>}<section aria-live="polite" aria-busy={searchBusy}>{searchBusy && <p className="sg-loading">Matching your description to the collected standards…</p>}<Results result={result} open={setSelected} />{!result && !searchBusy && !searchError && <div className="sg-search-hint"><Icon name="search" size={19} /><p>Your recommendations will appear here.<br /><span>Select a code to view its scope and details.</span></p></div>}</section></div>}
      {page === "tender" && <div className="sg-workspace"><section className="sg-page-heading"><span className="sg-kicker">UPLOAD TENDER</span><h1 ref={heading} tabIndex={-1}>Your tender. A clearer view<br className="sg-desktop-break" /> of the standards it needs.</h1><p>Review requirements across all three categories. No category selection needed.</p></section><section className={`sg-dropzone ${dragging ? "sg-dragging" : ""}`} aria-label="Upload tender PDF" aria-busy={!!tenderBusy} onDragOver={e => { e.preventDefault(); if (!tenderBusy) setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); upload(e.dataTransfer.files); }}><div className="sg-upload-symbol"><Icon name="upload" size={30} /></div><h2>Drop your tender PDF here</h2><p>Or choose a file from your device</p><button className="sg-button sg-primary" disabled={!!tenderBusy} onClick={() => fileInput.current?.click()}>{tenderBusy === "review" ? "Reviewing tender…" : "Choose PDF"}<Icon name="arrow" size={18} /></button><input className="sg-sr-only" tabIndex={-1} ref={fileInput} type="file" accept=".pdf,application/pdf" disabled={!!tenderBusy} onChange={e => { upload(e.target.files); e.target.value = ""; }} aria-label="Choose tender PDF" /><p className="sg-small">Searchable PDF · Up to 10 MB · Scanned PDFs and images are not supported</p></section>{tenderError && <div className="sg-error" role="alert">{tenderError}</div>}<div aria-live="polite">{tenderBusy === "review" && <p className="sg-loading"><span className="sg-spinner" /> Reviewing {filename}…</p>}{tender && <section className="sg-tender-results"><div className="sg-report-heading"><div><span className="sg-kicker">TENDER REVIEW</span><h2>{tender.source_document || filename}</h2></div><button className="sg-button sg-primary" onClick={exportPdf} disabled={!!tenderBusy || !tender.report_id}>{tenderBusy === "export" ? "Preparing PDF…" : "Export report"}<Icon name="file" size={18} /></button></div>{tender.report_notice && <p className="sg-notice">{tender.report_notice}</p>}{(tender.items || []).map((item,i) => <div className="sg-tender-item" key={i}><div className="sg-item-label">ITEM {i+1}<span>{CATEGORIES[item.category] || "Category to confirm"}</span></div>{(item.requirement || item.text) && <h3>{item.requirement || item.text}</h3>}<Results result={item.recommendations || { standards: [], message: "No recommendations recorded for this item." }} open={setSelected} /></div>)}{!tender.items?.length && <p className="sg-notice">No individual requirements were returned. Try a PDF with clearly listed procurement items.</p>}{tender.limitations && <details className="sg-related"><summary>Review notes</summary><p>{tender.limitations}</p></details>}</section>}</div></div>}
      {page === "history" && <div className="sg-workspace"><section className="sg-page-heading"><span className="sg-kicker">YOUR WORKSPACE</span><h1 ref={heading} tabIndex={-1}>Pick up where you left off.</h1><p>Recent searches and tender reviews from this browser tab. Up to 12 entries.</p></section><div className="sg-history-head"><h2>Session history <span>{history.length}</span></h2>{history.length > 0 && <button className="sg-text-button" onClick={() => { setHistory([]); try { sessionStorage.removeItem(HISTORY_KEY); setHistoryNotice(""); } catch { setHistoryNotice("Could not clear browser storage. History is cleared from this view."); } }}>Clear history</button>}</div>{historyNotice && <p className="sg-notice">{historyNotice}</p>}{history.length ? <div className="sg-history-list">{history.map(entry => <button className="sg-history-row" key={entry.id} onClick={() => openHistory(entry)} disabled={searchBusy || !!tenderBusy}><span className="sg-history-icon"><Icon name={entry.type === "search" ? "search" : "file"} /></span><span className="sg-history-text"><strong>{entry.query}</strong><small>{entry.type === "search" ? CATEGORIES[entry.category] || "Standards search" : "Tender review"} · {date(entry.at)}</small></span><Icon name="arrow" /></button>)}</div> : <div className="sg-empty"><Icon name="clock" size={32} /><h3>A fresh start</h3><p>Your searches and tender reviews will appear here.</p><a className="sg-button sg-primary" href="#find">Find a standard <Icon name="arrow" size={17} /></a></div>}</div>}
    </main>
    <footer className="sg-footer"><a className="sg-footer-brand" href="#home">SpecGyan.</a><span>Clarity before you procure.</span><a href={BIS} target="_blank" rel="noopener noreferrer">Explore BIS <Icon name="external" size={14} /></a></footer>
    {selected && <StandardDialog standard={selected} close={() => setSelected(null)} />}
    {login && <Modal close={() => setLogin(false)} titleId="login-title"><div className="sg-login-panel"><span className="sg-upload-symbol"><Icon name="building" size={28} /></span><span className="sg-kicker">ACCOUNT ACCESS</span><h2 id="login-title">Your workspace, without a login.</h2><p>Standards search and tender review are available now. Account sign-in and cross-device history are not connected in this version.</p><button className="sg-button sg-primary" onClick={() => { setLogin(false); window.location.hash = "find"; }}>Continue to Find Standard <Icon name="arrow" size={17} /></button></div></Modal>}
  </div>;
}
