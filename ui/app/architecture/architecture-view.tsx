"use client";

import { useState } from "react";
import s from "./architecture.module.css";

type Tone = "ing" | "ana" | "out";
type Node = { n: string; title: string; text: string; tone: Tone; chips?: { label: string; key?: boolean }[] };

/* ---------------- Vue d'ensemble ---------------- */
const FEED: Node[] = [
  { n: "01", title: "Firm documents", text: "200 corporate acts (greffe) and 5 templates, exported from the firm's document base.", tone: "ing" },
  { n: "02", title: "Structural ingestion", text: "Each act is split along its legal structure: one decision or article = one unit. 6,410 indexed units.", tone: "ing" },
  { n: "03", title: "Drafting histories", text: "For 129 acts, the path from first draft to final: V1, V2 and the partner's reviews. Synthetic today, the firm's own tomorrow.", tone: "ing" },
];
const REVIEW: Node[] = [
  { n: "04", title: "The junior imports a draft", text: "PDF or .docx, from the workspace. Strictness: standard or max.", tone: "ana" },
  { n: "05", title: "Qualify and score", text: "Operation type, legal form, date. The expected clauses are checked; a key clause missing costs 10 points.", tone: "ana" },
  { n: "06", title: "Closest precedents", text: "Three acts of the same operation and legal form, best coverage, most recent, with what the partner corrected on them.", tone: "ana" },
  { n: "07", title: "Targeted correction", text: "Only the missing clauses are rewritten, from the precedents and the partner's reviews. Unknowns stay in brackets, never invented.", tone: "out" },
  { n: "08", title: "Corrected file, and the why", text: "Score before → after, every change sourced, a .docx with highlights and a change log.", tone: "out" },
];

/* ---------------- Vue technique ---------------- */
const PHASE1: Node[] = [
  { n: "SOURCE", title: "Document base", text: "200 PDFs (text or scanned) and 5 .docx templates.", tone: "ing",
    chips: [{ label: "PDF" }, { label: ".docx" }, { label: "Mistral OCR · cached", key: true }] },
  { n: "01", title: "Extraction", text: "Blocks, tables, removal of footers and tables of contents.", tone: "ing",
    chips: [{ label: "PyMuPDF", key: true }, { label: "python-docx" }] },
  { n: "02", title: "Structural chunking", text: "One decision or article = one unit. Tables in Markdown. Annexes apart.", tone: "ing",
    chips: [{ label: "min 300" }, { label: "max 1500" }, { label: "parent ≤ 6000" }] },
  { n: "03", title: "Embeddings and storage", text: "Small chunks are searched; the whole unit (parent) is handed to the LLM.", tone: "ing",
    chips: [{ label: "mistral-embed · 1024", key: true }, { label: "ChromaDB · cosine", key: true }, { label: "SQLite parents" }] },
  { n: "04", title: "Drafting histories", text: "V1 → partner review → V2 → review → final, reconstructed from each real act.", tone: "ing",
    chips: [{ label: "generate_history.py", key: true }, { label: "129 acts" }, { label: "645 review emails" }, { label: "synthetic" }] },
  { n: "05", title: "Quality index", text: "Per act: operation type, legal form, date, grid coverage. Feeds the precedent ranking.", tone: "ing",
    chips: [{ label: "corpus_index.py", key: true }, { label: "qualify.py" }, { label: "205 acts" }] },
];
const PHASE2: Node[] = [
  { n: "INPUT", title: "The draft", text: "PDF or .docx; training banners stripped.", tone: "ana", chips: [{ label: "sources.py", key: true }] },
  { n: "06", title: "Qualification", text: "Legal form, company, date, nature (regex) and operation category among 13 types.", tone: "ana",
    chips: [{ label: "qualify.py", key: true }, { label: "1 LLM call" }] },
  { n: "07", title: "Grid and score", text: "Expected clauses per operation, each present / partial / absent. Score /100, −10 per missing key clause.", tone: "ana",
    chips: [{ label: "scoring.py", key: true }, { label: "grille.json" }, { label: "mistral-medium · JSON" }] },
  { n: "08", title: "Similar cases", text: "Category → grid family → nature → legal form → coverage → recency. Plus the partner's reviews on each.", tone: "ana",
    chips: [{ label: "similar.py", key: true }, { label: "historique_acte" }, { label: "top 3" }] },
  { n: "09", title: "Targeted redraft", text: "Missing clauses rewritten from precedent units, partner corrections and matter emails.", tone: "ana",
    chips: [{ label: "redraft.py", key: true }, { label: "[à compléter]" }, { label: "facts check" }, { label: "monotonic score" }] },
];
const OUTPUTS: Node[] = [
  { n: "10", title: "Feedback", text: "Summary, priorities, the why per clause, follow-up questions.", tone: "out", chips: [{ label: "respond.py", key: true }] },
  { n: "OUTPUT", title: ".docx + JSON", text: "Highlights, change log with sources, score before → after. Streamed to the workspace.", tone: "out",
    chips: [{ label: "scripts/review.py", key: true }, { label: "SSE" }, { label: "/api/download" }] },
  { n: "11", title: "Tools for agents", text: "The same engine, callable by Claude or a legal platform.", tone: "out",
    chips: [{ label: "mcp_server.py", key: true }, { label: "scorer_pv" }, { label: "search_best_practices" }, { label: "historique_acte" }] },
  { n: "12", title: "Back into the base", text: "Once validated, the corrected act and its history join the corpus.", tone: "out" },
];
const CHOICES: [string, React.ReactNode][] = [
  ["Extraction", <><code>PyMuPDF</code> · <code>Mistral OCR</code> for scans, cached</>],
  ["Chunking", "Legal structure rather than fixed size; parent = whole unit"],
  ["Embeddings", <><code>mistral-embed</code>, 1024 dims</>],
  ["Index", <><code>ChromaDB</code> cosine, filterable metadata; drafts (V1/V2) excluded from best-practice search</>],
  ["LLM", <><code>mistral-medium-latest</code>, JSON output, retries</>],
  ["Histories", "Generated from real acts; marked synthetic everywhere"],
  ["Guardrails", "Brackets instead of invented facts · unsupported-facts detector · after-score never below untouched clauses"],
  ["Interface", <><code>Next.js</code> + <code>shadcn</code>; review streamed over SSE (~2 min)</>],
];
const METADATA = ["source", "categorie", "doc_type", "source_type", "dossier", "societe", "acte_id", "version", "date_acte", "section", "chunk_type", "page", "parent_id"];
const ROUTER = ["decision_president", "decision_associes", "pv_ag", "traite", "document_structure", "generic", "mail", "version"];
const MODULES: [string, string][] = [
  ["ingest · chunking · parents · sources · ocr", "Phase 1 — base"],
  ["generate_history · corpus_index · qualify", "Phase 1 — histories and index"],
  ["scoring · similar · redraft · respond", "Phase 2 — review"],
  ["scripts/review · ui/", "Delivery"],
  ["retrieval · mcp_server", "Tools for agents"],
  ["llm · config", "Mistral calls, settings"],
];

function Flow({ nodes }: { nodes: Node[] }) {
  return (
    <div className={s.flow}>
      {nodes.map((node) => (
        <div key={node.n + node.title} className={`${s.node} ${s[node.tone]}`}>
          <div className={s.n}>{node.n}</div>
          <h3>{node.title}</h3>
          <p>{node.text}</p>
          {node.chips && (
            <div className={s.chips}>
              {node.chips.map((c) => (
                <span key={c.label} className={c.key ? `${s.chip} ${s.chipK}` : s.chip}>{c.label}</span>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function Loop({ children }: { children: React.ReactNode }) {
  return <div className={s.loop}><i />{children}<i /></div>;
}

export function ArchitectureView() {
  const [view, setView] = useState<"v1" | "v2">("v1");
  const [dark, setDark] = useState(false);

  return (
    <div className={s.root} data-theme={dark ? "dark" : "light"}>
      <div className={s.wrap}>
        <section className={s.hero}>
          <div>
            <div className={s.eyebrow}>thread · architecture</div>
            <h1 className={s.title}>From a junior&apos;s first draft<br />to the firm&apos;s standard.</h1>
            <p className={s.sub}>
              Thread qualifies the draft, finds the firm&apos;s closest precedents and what the partner corrected on them,
              rewrites only the missing clauses, and returns a scored file where every change cites its source.
            </p>
          </div>
          <button type="button" className={s.btn} onClick={() => setDark((d) => !d)} aria-label="Toggle theme">
            {dark ? "Light theme" : "Dark theme"}
          </button>
        </section>

        <div className={s.tabs} role="tablist">
          <button type="button" role="tab" aria-selected={view === "v1"} className={`${s.btn} ${view === "v1" ? s.btnOn : ""}`} onClick={() => setView("v1")}>Overview</button>
          <button type="button" role="tab" aria-selected={view === "v2"} className={`${s.btn} ${view === "v2" ? s.btnOn : ""}`} onClick={() => setView("v2")}>Technical view</button>
        </div>

        {view === "v1" ? (
          <section key="v1" className={s.view}>
            <div className={`${s.lane} ${s.big}`}>
              <div className={s.laneH}><span className={s.sq} style={{ background: "var(--ing)" }} />Feeding the base</div>
              <div className={s.pixels}><b className={s.a} /><b /><b className={s.b} /><b /><b className={s.a} /><b /></div>
              <Flow nodes={FEED} />
            </div>

            <div className={s.bridge}><span>the base is queried <b>on every review</b></span></div>

            <div className={`${s.lane} ${s.big}`}>
              <div className={s.laneH}><span className={s.sq} style={{ background: "var(--ana)" }} />Reviewing a junior&apos;s draft</div>
              <Flow nodes={REVIEW} />
              <Loop>once validated, the corrected act and its history join the base</Loop>
            </div>

            <div className={s.legend}>
              <span><i className={s.sq} style={{ background: "var(--ing)" }} />Base</span>
              <span><i className={s.sq} style={{ background: "var(--ana)" }} />Review</span>
              <span><i className={s.sq} style={{ background: "var(--out)" }} />Deliverables</span>
            </div>
          </section>
        ) : (
          <section key="v2" className={s.view}>
            <div className={s.lane}>
              <div className={s.laneH}><span className={s.sq} style={{ background: "var(--ing)" }} />Phase 1 — Base (ingest.py · generate_history.py · corpus_index.py)</div>
              <Flow nodes={PHASE1} />
              <Loop>resumable: file fingerprint, OCR cache, errors isolated per document</Loop>
            </div>

            <div className={s.bridge}><span>tools <b>search_best_practices · historique_acte · scorer_pv</b> · drafts excluded from search</span></div>

            <div className={s.lane}>
              <div className={s.laneH}><span className={s.sq} style={{ background: "var(--ana)" }} />Phase 2 — Review (scripts/review.py · 8 streamed steps · ~2 min)</div>
              <Flow nodes={PHASE2} />
              <Loop>the LLM judges clause states and writes; the score itself is computed, never generated</Loop>
              <div style={{ marginTop: 14 }}><Flow nodes={OUTPUTS} /></div>
            </div>

            <div className={s.cols}>
              <div className={s.card}>
                <h4>Technical choices</h4>
                <table className={s.table}>
                  <thead><tr><th>Component</th><th>Choice</th></tr></thead>
                  <tbody>{CHOICES.map(([k, v]) => <tr key={k}><td>{k}</td><td>{v}</td></tr>)}</tbody>
                </table>
              </div>
              <div className={s.card}>
                <h4>Metadata per chunk</h4>
                <div className={s.chips} style={{ marginTop: 0 }}>
                  {METADATA.map((m) => <span key={m} className={s.chip}>{m}</span>)}
                </div>
                <h4 style={{ marginTop: 22 }}>Document type router</h4>
                <div className={s.chips} style={{ marginTop: 0 }}>
                  {ROUTER.map((m) => <span key={m} className={s.chip}>{m}</span>)}
                </div>
              </div>
              <div className={s.card}>
                <h4>Modules</h4>
                <table className={s.table}>
                  <tbody>{MODULES.map(([k, v]) => <tr key={k}><td>{k}</td><td>{v}</td></tr>)}</tbody>
                </table>
              </div>
            </div>
          </section>
        )}

        <footer className={s.footer}>thread · architecture diagram · the style is inspired by the corti.ai identity, without reusing its logo.</footer>
      </div>
    </div>
  );
}
