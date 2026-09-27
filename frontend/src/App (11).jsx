import { useEffect, useRef, useState } from "react";
import "./index.css";

const API = (import.meta.env?.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const BIS = "https://standards.bis.gov.in/website/know-your-standards";
const HISTORY_KEY = "specgyan-session-history-v1";
const CATEGORIES = { construction: "Construction", electrical: "Electrical", plumbing: "Plumbing" };
const SEARCH_STEPS = [
  "Checking spelling and common aliases",
  "Comparing semantic similarity",
  "Matching keywords and IS codes",
  "Applying category rules and ranking",
];
const TENDER_STEPS = [
  "Reading the tender PDF",
  "Identifying the product and grade",
  "Matching cited Indian Standards",
  "Loading BIS record and related test methods",
];
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
function route() { const key = window.location.hash.slice(1).split("?")[0]; return ["find", "tender", "history", "how"].includes(key) ? key : "home"; }
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
function ReferenceList({ standard: s }) {
  const combined = [
    ...(s.related_standards || []).map(r => ({ ...r, direction: "References" })),
    ...(s.referenced_by || []).map(r => ({ ...r, direction: "Referenced by" })),
  ];
  const [expanded, setExpanded] = useState(false);
  if (!combined.length) return null;
  const visible = expanded ? combined : combined.slice(0, 3);
  return <div className="sg-related-block">
    <h3 className="sg-related-heading">Related standards and references <span>{combined.length}</span></h3>
    <div className="sg-related-rows">{visible.map((r, i) => <p key={i} className="sg-related-row">
      <strong>{r.is_number || r.standardNumber || "—"}</strong> {r.title || r.standardName}
      <span className="sg-related-tag">{r.reference_group || r.direction}</span>
    </p>)}</div>
    {combined.length > 3 && <button type="button" className="sg-text-button" onClick={() => setExpanded(v => !v)}>
      {expanded ? "Show fewer" : `Show ${combined.length - 3} more`}
    </button>}
  </div>;
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
    <ReferenceList standard={s} />
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
    {standards.length ? <><div className="sg-result-heading"><h2>Recommended standards <span>{standards.length}</span></h2><p>Select a code to explore its details.</p></div><div className="sg-result-list">{standards.map((s,i) => <button key={`${s.standard_id || s.is_number}-${i}`} className="sg-result" onClick={() => open(s)}><span className="sg-rank" aria-label={`Rank ${i + 1}`}>{i + 1}</span><span className="sg-result-content"><strong>{s.is_number}</strong><span className="sg-result-title">{s.title}</span></span><Icon name="arrow" /></button>)}</div></> : !result.clarification_question && <div className="sg-empty"><Icon name="search" size={26} /><h3>No suitable standard found</h3><p>{result.message || "Try adding the material and intended use, or explore the BIS catalogue."}</p><a href={BIS} target="_blank" rel="noopener noreferrer">Explore BIS catalogue ↗</a></div>}
  </div>;
}
function SearchProgress({ step }) {
  return <section className="sg-progress" aria-label="Recommendation search progress" aria-live="polite" aria-atomic="false">
    <div className="sg-progress-heading"><span className="sg-progress-mark"><Icon name="search" size={17} /></span><span><strong>Finding relevant standards</strong><small>Reviewing your description</small></span></div>
    <ol>{SEARCH_STEPS.map((label, index) => <li key={label} className={index < step ? "is-done" : index === step ? "is-active" : ""}>
      <span className="sg-progress-state">{index < step ? <Icon name="check" size={13} /> : index === step ? <span className="sg-spinner" /> : <span className="sg-progress-number">{index + 1}</span>}</span>
      <span>{label}</span>
    </li>)}</ol>
  </section>;
}
function TenderProgress({ step }) {
  return <section className="sg-progress sg-tender-progress" aria-label="Tender review progress" aria-live="polite" aria-atomic="false">
    <div className="sg-progress-heading"><span className="sg-progress-mark"><Icon name="file" size={17} /></span><span><strong>Reviewing your tender</strong><small>Finding the relevant Indian Standards</small></span></div>
    <ol>{TENDER_STEPS.map((label, index) => <li key={label} className={index < step ? "is-done" : index === step ? "is-active" : ""}>
      <span className="sg-progress-state">{index < step ? <Icon name="check" size={13} /> : index === step ? <span className="sg-spinner" /> : <span className="sg-progress-number">{index + 1}</span>}</span>
      <span>{label}</span>
    </li>)}</ol>
  </section>;
}
function visibleTenderItems(items) {
  const rows = Array.isArray(items) ? items : [];
  const withStandards = rows.filter(item => item?.recommendations?.standards?.length);
  return withStandards.length ? withStandards : rows.filter(item => item?.recommendations?.clarification_question);
}
function Spark({ className = "" }) {
  return <svg className={className} width="38" height="38" viewBox="0 0 40 40" fill="none" aria-hidden="true"><path d="M20 3c0 11-6 17-17 17 11 0 17 6 17 17 0-11 6-17 17-17C26 20 20 14 20 3Z" stroke="currentColor" strokeWidth="2.3" strokeLinejoin="round" /></svg>;
}
function HomePreview() {
  return <div className="sg-home-visual" aria-label="Illustrative standards search preview">
    <div className="sg-visual-note">A little clarity.<br />A better decision.<svg viewBox="0 0 92 52" fill="none" aria-hidden="true"><path d="M2 5c10 33 54 29 74 11M61 13l18 1-8 17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg></div>
    <div className="sg-product-window">
      <div className="sg-product-top"><span className="sg-mini-brand"><b>S</b> SpecGyan<span>.</span></span><span className="sg-preview-caption">EXAMPLE PREVIEW</span></div>
      <div className="sg-product-inner">
        <div className="sg-preview-query"><div className="sg-preview-field-label"><Icon name="file" size={16} /> YOUR REQUIREMENT</div><p>Portland pozzolana cement<br />made with <strong>fly ash.</strong></p><span className="sg-preview-category"><Icon name="building" size={13} /> Construction</span></div>
        <div className="sg-match-connector"><span /><span className="sg-match-orb"><Spark /></span><span /><small>CONNECTING THE DETAILS</small></div>
        <div className="sg-preview-answer"><div className="sg-answer-label"><span>RECOMMENDED STANDARD</span><Icon name="arrow" size={18} /></div><strong className="sg-preview-code">IS 1489 (Part 1):2015</strong><p>Portland Pozzolana Cement<br />Part 1: Fly Ash Based</p><div className="sg-preview-reason"><span><Icon name="check" size={17} /></span><div><strong>Why this standard?</strong><p>Its scope covers Portland pozzolana<br className="sg-desktop-break" /> cement using fly ash as pozzolana.</p></div></div></div>
      </div>
      <div className="sg-product-bottom"><span className="sg-live-dot" /> The code. The scope. The reason.</div>
    </div>
    <div className="sg-floating-stamp"><Spark /><span>Know what<br />applies.</span></div>
    <div className="sg-visual-caption"><span>01 /</span> FROM YOUR REQUIREMENT TO A RELEVANT IS CODE</div>
  </div>;
}
function HowPage({ heading, embedded = false }) {
  const Title = embedded ? "h2" : "h1";
  const steps = [
    ["file", "Start with what you need", "Describe your product and choose a category, or upload a searchable tender PDF. Include the material and intended use."],
    ["search", "Find relevant candidates", "Keyword and semantic search compare your requirement with the collected standards catalogue."],
    ["grid", "Bring the best matches forward", "Category filtering and ranking put the most relevant candidates first. More specific requirements help narrow the results."],
    ["check", "Understand before you procure", "Open an IS code to review its scope, the reason for the match, and available amendment and reaffirmation details."],
  ];
  return <div className="sg-workspace sg-how-page"><section className="sg-page-heading"><span className="sg-kicker">A CLEARER WAY TO SEARCH</span><Title ref={heading} tabIndex={-1}>From specification<br />to <em>standard.</em></Title><p>Four steps to a better-informed procurement decision.</p></section><div className="sg-how-grid">{steps.map(([icon,title,body],i)=><article className="sg-how-card" key={title}><div className="sg-how-top"><span>0{i+1}</span><Icon name={icon} size={28} /></div><h2>{title}</h2><p>{body}</p></article>)}</div><div className="sg-how-cta"><span>Have a requirement in mind?</span><a href="#find" className="sg-button sg-primary">Find your standard <Icon name="arrow" size={18} /></a></div></div>;
}

export default function App() {
  const [page, setPage] = useState(route);
  const [category, setCategory] = useState("construction");
  const [query, setQuery] = useState("");
  const [result, setResult] = useState(null);
  const [searchBusy, setSearchBusy] = useState(false);
  const [searchStep, setSearchStep] = useState(-1);
  const searchLock = useRef(false);
  const [searchError, setSearchError] = useState("");
  const [selected, setSelected] = useState(null);
  const [login, setLogin] = useState(false);
  const [history, setHistory] = useState(loadHistory);
  const [historyNotice, setHistoryNotice] = useState("");
  const [tender, setTender] = useState(null);
  const [tenderBusy, setTenderBusy] = useState("");
  const [tenderStep, setTenderStep] = useState(-1);
  const [tenderAccepted, setTenderAccepted] = useState(false);
  const [tenderFileSize, setTenderFileSize] = useState(0);
  const tenderLock = useRef(false);
  const [tenderError, setTenderError] = useState("");
  const [filename, setFilename] = useState("");
  const [pendingPdf, setPendingPdf] = useState(null);
  const [pdfUrl, setPdfUrl] = useState("");
  const [pdfView, setPdfView] = useState("split");
  useEffect(() => {
    if (!pendingPdf) { setPdfUrl(""); return; }
    const url = URL.createObjectURL(pendingPdf);
    setPdfUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [pendingPdf]);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef(null);
  const heading = useRef(null);
  useEffect(() => {
    const change = () => { setPage(route()); setSelected(null); setLogin(false); };
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  useEffect(() => { document.title = `${page === "home" ? "Indian Standards for Procurement" : page === "find" ? "Find Standard" : page === "tender" ? "Upload Tender" : page === "how" ? "How It Works" : "History"} | SpecGyan`; window.scrollTo({ top: 0 }); heading.current?.focus({ preventScroll: true }); }, [page]);
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
    searchLock.current = true; setQuery(value); setSearchBusy(true); setSearchStep(0); setResult(null); setSearchError("");
    const started = performance.now();
    let stopProgress = false;
    const progress = (async () => {
      for (let i = 1; i < SEARCH_STEPS.length; i += 1) {
        await new Promise(resolve => setTimeout(resolve, 450));
        if (stopProgress) return;
        setSearchStep(i);
      }
    })();
    try {
      const response = await request("/api/analyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ requirement: value, category }) });
      const [data] = await Promise.all([response.json(), progress]);
      const remaining = 2200 - (performance.now() - started);
      if (remaining > 0) await new Promise(resolve => setTimeout(resolve, remaining));
      setSearchStep(SEARCH_STEPS.length);
      await new Promise(resolve => setTimeout(resolve, 300));
      setResult(data); remember("search", value, data, category);
    } catch (e) { stopProgress = true; setSearchError(e.message || "Could not complete the search."); }
    finally { stopProgress = true; searchLock.current = false; setSearchBusy(false); setSearchStep(-1); }
  }
  async function selectPdf(files) {
    if (tenderLock.current || !files?.length) return;
    setTenderError("");
    if (files.length !== 1) return setTenderError("Please choose one PDF at a time.");
    const file = files[0];
    if (!/\.pdf$/i.test(file.name) || !file.size || file.size > 10 * 1024 * 1024)
      return setTenderError("Choose a nonempty searchable PDF of up to 10 MB.");
    tenderLock.current = true; setTenderBusy("accept");
    try {
      if (await file.slice(0, 5).text() !== "%PDF-") throw new Error("Choose a valid PDF file.");
      setPendingPdf(file); setPdfView("split"); setFilename(file.name); setTenderFileSize(file.size);
      setTender(null); setTenderAccepted(true);
    } catch (error) { setTenderError(error.message); }
    finally { tenderLock.current = false; setTenderBusy(""); }
  }
  function removePdf() {
    if (tenderLock.current) return;
    setPendingPdf(null); setFilename(""); setTenderAccepted(false);
    setTender(null); setTenderError(""); setTenderFileSize(0);
  }
  async function upload() {
    const files = pendingPdf ? [pendingPdf] : [];
    if (tenderLock.current || !files?.length) return;
    setTenderError(""); setTender(null); setTenderAccepted(false);
    if (files.length !== 1) return setTenderError("Please choose one PDF at a time.");
    const file = files[0];
    if (!/\.pdf$/i.test(file.name)) return setTenderError("Choose a searchable PDF. Images are not supported.");
    if (!file.size || file.size > 10 * 1024 * 1024) return setTenderError("Choose a nonempty PDF no larger than 10 MB.");
    tenderLock.current = true; setTenderBusy("accept"); setTenderStep(0); setFilename(file.name);
    let stopProgress = false;
    let progress;
    try {
      const signature = await file.slice(0, 5).text();
      if (signature !== "%PDF-") throw new Error("This file does not appear to be a valid PDF. Choose a PDF and try again.");
      setTenderAccepted(true); setTenderFileSize(file.size); setTenderBusy("review");
      const started = performance.now();
      progress = (async () => {
        for (let i = 1; i < TENDER_STEPS.length; i += 1) {
          await new Promise(resolve => setTimeout(resolve, 500));
          if (stopProgress) return;
          setTenderStep(i);
        }
      })();
      const body = new FormData(); body.append("file", file);
      const response = await request("/api/tender/upload", { method: "POST", body }, 120000);
      const [data] = await Promise.all([response.json(), progress]);
      const remaining = 2250 - (performance.now() - started);
      if (remaining > 0) await new Promise(resolve => setTimeout(resolve, remaining));
      setTenderStep(TENDER_STEPS.length);
      await new Promise(resolve => setTimeout(resolve, 300));
      setTender(data); remember("tender", file.name, data);
    } catch (e) { stopProgress = true; setTenderError(e.message || "Could not review this PDF."); setTenderAccepted(false); }
    finally { stopProgress = true; tenderLock.current = false; setTenderBusy(""); setTenderStep(-1); }
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
    else { setPendingPdf(null); setTenderAccepted(false); setTender(entry.result); setFilename(entry.query); setTenderError(""); window.location.hash = "tender"; }
  }
  return <div className="sg-app">
    <a className="sg-skip" href="#main-content" onClick={e => { e.preventDefault(); heading.current?.focus(); }}>Skip to content</a>
    <header className="sg-header"><div className="sg-nav-wrap"><a className="sg-brand" href="#home" aria-label="SpecGyan home"><span className="sg-brand-mark">S</span><span>SpecGyan<span className="sg-brand-period"></span></span></a><nav aria-label="Main navigation">{[["home","Home"],["find","Find Standard"],["tender","Upload Tender"],["how","How It Works"],["history","History"]].map(([key,label])=><a key={key} href={`#${key}`} aria-current={page===key?"page":undefined}>{label}</a>)}<button className="sg-login" onClick={() => setLogin(true)}>Login <Icon name="arrow" size={16} /></button></nav></div></header>
    <main id="main-content" className={`sg-main sg-page-${page}`}>
      {page === "home" && <><section className="sg-home">
        <div className="sg-home-grid"><div className="sg-home-copy"><div className="sg-eyebrow"><Spark /> INDIAN STANDARDS, MADE CLEAR</div><h1 ref={heading} tabIndex={-1}>Find the right<br />Indian Standard.<br /><span className="sg-highlight">Before you procure.</span></h1><p className="sg-home-intro">Describe what you’re buying or bring your tender.<br className="sg-desktop-break" /> Find relevant IS codes. Understand why they matter.</p>
          <div className="sg-action-grid"><a className="sg-action-card sg-action-find" href="#find"><div className="sg-action-card-top"><span className="sg-action-icon"><Icon name="search" size={25} /></span><span className="sg-action-number">01</span></div><h2>Find a standard</h2><p>Start with a product description.</p><span className="sg-action-link">Describe your requirement <Icon name="arrow" size={18} /></span></a><a className="sg-action-card sg-action-tender" href="#tender"><div className="sg-action-card-top"><span className="sg-action-icon"><Icon name="upload" size={25} /></span><span className="sg-action-number">02</span></div><h2>Review a tender</h2><p>Let your procurement PDF do the talking.</p><span className="sg-action-link">Upload your PDF <Icon name="arrow" size={18} /></span></a></div>
        </div><HomePreview /></div>
        <div className="sg-domain-strip"><span className="sg-domain-label">THREE DOMAINS.<br /><strong>One place to begin.</strong></span><a href="#find" onClick={()=>setCategory("construction")}><Icon name="building" /> Construction <Icon name="arrow" size={17} /></a><a href="#find" onClick={()=>setCategory("electrical")}><span className="sg-domain-symbol">ϟ</span> Electrical <Icon name="arrow" size={17} /></a><a href="#find" onClick={()=>setCategory("plumbing")}><Icon name="grid" /> Plumbing <Icon name="arrow" size={17} /></a><Spark className="sg-domain-spark" /></div>
      </section><section className="sg-home-how" aria-label="How it works"><HowPage embedded /></section></>}
      {page === "how" && <HowPage heading={heading} />}
      {page === "find" && <div className="sg-workspace"><section className="sg-page-heading"><span className="sg-kicker">FIND STANDARD</span><h1 ref={heading} tabIndex={-1}>Your requirement.<br className="sg-desktop-break" /> <em>The right starting point.</em></h1><p>Tell us what you need, and explore the standards that may apply.</p></section><section className="sg-search-panel" aria-label="Describe your requirement"><form onSubmit={e => { e.preventDefault(); search(); }}><div className="sg-input-heading"><label htmlFor="description">Product description</label><div className="sg-category"><Icon name="grid" size={16} /><label className="sg-sr-only" htmlFor="category">Category</label><select id="category" value={category} disabled={searchBusy} onChange={e => { setCategory(e.target.value); setResult(null); setSearchError(""); }}>{Object.entries(CATEGORIES).map(([key,name]) => <option value={key} key={key}>{name}</option>)}</select></div></div><textarea id="description" placeholder="Describe the product, material and intended use…" value={query} maxLength={5000} disabled={searchBusy} onChange={e => { setQuery(e.target.value); setResult(null); setSearchError(""); }} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); search(); } }} aria-describedby="description-help" /><div className="sg-textarea-bottom"><span>{query.length.toLocaleString()} / 5,000</span><button type="button" className="sg-text-button" disabled={!query || searchBusy} onClick={() => { setQuery(""); setResult(null); setSearchError(""); }}>Clear</button></div><div className="sg-search-actions"><p id="description-help"><Icon name="file" size={15} /> Include material, voltage or intended use. Enter to search · Shift+Enter for a new line.</p><button className="sg-button sg-primary" disabled={searchBusy || query.trim().length < 2}>{searchBusy ? <><span className="sg-spinner" /> Finding standards</> : <>Find Standard <Icon name="arrow" size={18} /></>}</button></div></form><div className="sg-examples"><span>Try a search</span>{EXAMPLES[category].map(([label,text]) => <button key={label} disabled={searchBusy} onClick={() => search(text)}>{label}<Icon name="arrow" size={14} /></button>)}</div></section>{searchError && <div className="sg-error" role="alert">{searchError}</div>}<section aria-live="polite" aria-busy={searchBusy}>{searchBusy && <SearchProgress step={searchStep} />}<Results result={result} open={setSelected} />{!result && !searchBusy && !searchError && <div className="sg-search-hint"><Icon name="search" size={19} /><p>Your recommendations will appear here.<br /><span>Select a code to view its scope and details.</span></p></div>}</section></div>}
      {page === "tender" && <div className="sg-workspace">
        <section className="sg-page-heading">
          <span className="sg-kicker">UPLOAD TENDER</span>
          <h1 ref={heading} tabIndex={-1}>One tender.<br className="sg-desktop-break" /> <em>A clearer set of standards.</em></h1>
          <p>Upload a searchable tender PDF to identify its product requirements and relevant Indian Standards.</p>
        </section>
        <section className={`sg-dropzone ${dragging ? "sg-dragging" : ""} ${tenderAccepted ? "sg-dropzone-accepted" : ""}`}
          aria-label="Upload tender PDF" aria-busy={!!tenderBusy}
          onDragOver={e => { e.preventDefault(); if (!tenderBusy) setDragging(true); }}
          onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget)) setDragging(false); }}
          onDrop={e => { e.preventDefault(); setDragging(false); selectPdf(e.dataTransfer.files); }}>
          {tenderAccepted ? <>
            <div className="sg-accepted-file"><span className="sg-accepted-file-icon"><Icon name="file" size={24} /></span>
              <span className="sg-accepted-file-text"><strong>{filename}</strong><small>{(tenderFileSize / (1024 * 1024)).toFixed(2)} MB · PDF selected</small></span>
              <span className="sg-accepted-check" aria-label="PDF accepted"><Icon name="check" size={19} /></span><button type="button" className="sg-remove-file" aria-label="Remove selected PDF" disabled={!!tenderBusy} onClick={removePdf}><Icon name="close" size={17} /></button>
            </div>
            <p className="sg-dropzone-caption">{tenderBusy === "review" ? "Checking the document and finding relevant standards…" : "PDF ready. Click Find Standard to begin the review."}</p>
          </> : <>
            <div className="sg-drop-art" aria-hidden="true"><span className="sg-paper sg-paper-left"><Icon name="file" size={28} /></span><span className="sg-paper sg-paper-right"><Icon name="file" size={28} /></span><span className="sg-paper sg-paper-front"><Icon name="upload" size={30} /></span></div>
            <h2>{dragging ? "Drop your PDF here" : "Drag & drop your tender PDF"}</h2><p>Or choose a file from your device</p>
          </>}
          <div className="sg-upload-actions"><button type="button" className="sg-button sg-secondary" disabled={!!tenderBusy} onClick={() => fileInput.current?.click()}>
            {tenderBusy === "accept" ? "Accepting PDF…" : tenderBusy === "review" ? "Reviewing tender…" : tenderAccepted ? "Choose another PDF" : "Choose PDF"}
            {!tenderBusy && <Icon name={tenderAccepted ? "upload" : "arrow"} size={18} />}
          </button>
          <button type="button" className="sg-button sg-primary" disabled={!pendingPdf || !!tenderBusy} onClick={upload}>{tenderBusy === "review" ? <><span className="sg-spinner" /> Finding standards</> : <>Find Standard <Icon name="arrow" size={18} /></>}</button></div>
          <input className="sg-sr-only" tabIndex={-1} ref={fileInput} type="file" accept=".pdf,application/pdf" disabled={!!tenderBusy}
            onChange={e => { selectPdf(e.target.files); e.target.value = ""; }} aria-label="Choose tender PDF" />
          <p className="sg-small">Searchable PDF · Up to 10 MB · Scanned PDFs and images are not supported</p>
        </section>
        {tenderError && <div className="sg-error" role="alert">{tenderError}</div>}
        {pdfUrl && <div className="sg-preview-toolbar">
          <div><span className="sg-kicker">DOCUMENT WORKSPACE</span><h2>Read and review</h2></div>
          <div className="sg-view-controls" role="group" aria-label="Document view">
            <button type="button" aria-pressed={pdfView === "full"} onClick={() => setPdfView("full")}>Full view</button>
            <button type="button" aria-pressed={pdfView === "split"} onClick={() => setPdfView("split")}>Split view</button>
            <button type="button" aria-pressed={pdfView === "results"} onClick={() => setPdfView("results")}>Results only</button>
          </div>
        </div>}
        <div className={`sg-review-layout ${pdfUrl ? `sg-view-${pdfView}` : ""}`}>
        {pdfUrl && pdfView !== "results" && <section className="sg-pdf-panel" aria-label="Tender PDF preview">
          <div className="sg-pdf-heading"><strong title={filename}>{filename}</strong><a href={pdfUrl} target="_blank" rel="noopener noreferrer">Open in new tab <Icon name="external" size={14} /></a></div>
          <iframe key={pdfUrl} src={`${pdfUrl}#view=FitH`} title="Uploaded tender PDF" />
          <p className="sg-pdf-help">Preview not displaying? Use Open in new tab to view or download your PDF.</p>
        </section>}
        <div className="sg-review-results" hidden={!!pdfUrl && pdfView === "full"} aria-live="polite" aria-busy={tenderBusy === "review"}>
          {pdfUrl && !tender && !tenderBusy && <div className="sg-empty"><Icon name="search" size={26} /><h3>Your recommendations will appear here</h3><p>Click Find Standard above to review this tender across all three categories.</p></div>}
          {tenderBusy === "review" && <TenderProgress step={tenderStep} />}
          {tender && <section className="sg-tender-results">
            <div className="sg-report-heading"><div><span className="sg-kicker">TENDER REVIEW</span><h2>{tender.source_document || filename}</h2></div>
              <button className="sg-button sg-primary" onClick={exportPdf} disabled={!!tenderBusy || !tender.report_id}>{tenderBusy === "export" ? "Preparing PDF…" : "Export report"}<Icon name="file" size={18} /></button>
            </div>
            {tender.report_notice && <p className="sg-notice">{tender.report_notice}</p>}
            {visibleTenderItems(tender.items).length ? visibleTenderItems(tender.items).map((item, i) => <div className="sg-tender-item" key={i}>
              <div className="sg-item-label">RECOMMENDATION {i + 1}<span>{CATEGORIES[item.category] || "Category to confirm"}</span></div>
              <Results result={item.recommendations} open={setSelected} />
            </div>) : <div className="sg-empty"><Icon name="search" size={26} /><h3>No supported standard match found</h3><p>Try a clearer searchable PDF or enter the product description in Find Standard.</p></div>}
            {tender.limitations && <details className="sg-related"><summary>Review notes</summary><p>{tender.limitations}</p></details>}
          </section>}
        </div>
        </div>
      </div>}
      {page === "history" && <div className="sg-workspace"><section className="sg-page-heading"><span className="sg-kicker">YOUR WORKSPACE</span><h1 ref={heading} tabIndex={-1}>Good work deserves<br /><em>a place to come back to.</em></h1><p>Recent searches and tender reviews from this browser tab. Up to 12 entries.</p></section><div className="sg-history-head"><h2>Session history <span>{history.length}</span></h2>{history.length > 0 && <button className="sg-text-button" onClick={() => { setHistory([]); try { sessionStorage.removeItem(HISTORY_KEY); setHistoryNotice(""); } catch { setHistoryNotice("Could not clear browser storage. History is cleared from this view."); } }}>Clear history</button>}</div>{historyNotice && <p className="sg-notice">{historyNotice}</p>}{history.length ? <div className="sg-history-list">{history.map(entry => <button className="sg-history-row" key={entry.id} onClick={() => openHistory(entry)} disabled={searchBusy || !!tenderBusy}><span className="sg-history-icon"><Icon name={entry.type === "search" ? "search" : "file"} /></span><span className="sg-history-text"><strong>{entry.query}</strong><small>{entry.type === "search" ? CATEGORIES[entry.category] || "Standards search" : "Tender review"} · {date(entry.at)}</small></span><Icon name="arrow" /></button>)}</div> : <div className="sg-empty"><Icon name="clock" size={32} /><h3>A fresh start</h3><p>Your searches and tender reviews will appear here.</p><a className="sg-button sg-primary" href="#find">Find a standard <Icon name="arrow" size={17} /></a></div>}</div>}
    </main>
    <footer className="sg-footer"><a className="sg-footer-brand" href="#home">SpecGyan.</a><span>Clarity before you procure.</span><a href={BIS} target="_blank" rel="noopener noreferrer">Explore BIS <Icon name="external" size={14} /></a></footer>
    {selected && <StandardDialog standard={selected} close={() => setSelected(null)} />}
    {login && <Modal close={() => setLogin(false)} titleId="login-title"><div className="sg-login-panel"><span className="sg-upload-symbol"><Icon name="building" size={28} /></span><span className="sg-kicker">ACCOUNT ACCESS</span><h2 id="login-title">Your workspace, without a login.</h2><p>Standards search and tender review are available now. Account sign-in and cross-device history are not connected in this version.</p><button className="sg-button sg-primary" onClick={() => { setLogin(false); window.location.hash = "find"; }}>Continue to Find Standard <Icon name="arrow" size={17} /></button></div></Modal>}
  </div>;
}
