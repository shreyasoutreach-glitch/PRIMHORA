import React, { useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  CheckCircle2, Database, FileCheck2, History, ShieldCheck, UploadCloud,
  X, ArrowUpRight, AlertCircle, ChevronRight
} from "lucide-react";
import { api, hasAccessTokenProvider } from "../lib/api";

export default function SaaSDataSources() {
  const workspace = sessionStorage.getItem("primhora_workspace");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<{ rows: number; columns: string[] } | null>(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<any>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [merchantName, setMerchantName] = useState(() => sessionStorage.getItem("primhora_last_merchant") || "");
  const [importMode, setImportMode] = useState<"baseline" | "monitor">("baseline");
  const inputRef = useRef<HTMLInputElement>(null);
  const lastImport = sessionStorage.getItem("primhora_last_import_at");
  const connectedSources = Number(sessionStorage.getItem("primhora_connected_sources") || 0);

  const inspect = (next: File | null) => {
    setFile(next);
    setPreview(null);
    setImportResult(null);
    setImportError(null);
    if (!next || !next.name.toLowerCase().endsWith(".csv")) return;
    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result || "");
      const lines = text.split(/\r?\n/).filter(Boolean);
      const columns = (lines[0] || "").split(",").map(x => x.trim()).filter(Boolean);
      setPreview({ rows: Math.max(0, lines.length - 1), columns });
    };
    reader.readAsText(next.slice(0, 1024 * 1024));
  };

  const importCsv = async () => {
    if (!file || !merchantName.trim() || !hasAccessTokenProvider()) return;
    setImporting(true);
    setImportError(null);
    setImportResult(null);
    try {
      const result = await api.importPayoutCsv(file, merchantName.trim(), importMode);
      setImportResult(result);
      sessionStorage.setItem("primhora_last_merchant", result.merchant_name || merchantName.trim());
      sessionStorage.setItem("primhora_last_import_at", new Date().toISOString());
      sessionStorage.setItem("primhora_connected_sources", String(Math.max(1, connectedSources + 1)));
    } catch (e: any) {
      setImportError(e?.message || "Import failed");
    } finally {
      setImporting(false);
    }
  };

  if (!workspace) {
    return (
      <div className="min-h-[calc(100vh-72px)] bg-grid">
        <div className="mx-auto max-w-[1100px] px-5 py-16 sm:px-8">
          <div className="panel max-w-2xl p-10">
            <Database size={20} />
            <h1 className="font-display text-3xl mt-5">Create your organization first.</h1>
            <p className="text-sm text-text_primary/45 mt-3">Data sources belong to an organization.</p>
            <Link to="/app" className="inline-flex mt-6 rounded-xl bg-text_primary text-graphite px-5 py-3 text-sm font-medium">Set up workspace</Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-[calc(100vh-72px)] bg-graphite text-text_primary">
      <div className="mx-auto max-w-[1500px] px-5 py-9 sm:px-8">
        <div className="flex flex-wrap items-end justify-between gap-5">
          <div>
            <div className="flex items-center gap-2">
              <span className="status-dot bg-emerald" />
              <span className="label-eyebrow text-emerald/70">CONFIGURATION · DATA SOURCES</span>
            </div>
            <h1 className="font-display text-4xl mt-2 tracking-tight">Financial data</h1>
            <p className="text-sm text-text_primary/45 mt-3 max-w-2xl">
              Every source has an explicit state. PRIMHORA only calls something connected after the backend accepts the data.
            </p>
          </div>
          <Link to="/app/incidents" className="btn-secondary">View queue <ArrowUpRight size={14} /></Link>
        </div>

        <div className="grid sm:grid-cols-3 gap-3 mt-7">
          <SummaryCard label="Accepted imports" value={String(connectedSources)} sub="This browser session" />
          <SummaryCard label="Live providers" value="0" sub="No credentials configured" />
          <SummaryCard label="Last accepted import" value={lastImport ? new Date(lastImport).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "Never"} sub={lastImport ? new Date(lastImport).toLocaleDateString() : "No source accepted yet"} />
        </div>

        <div className="grid xl:grid-cols-[.9fr_1.1fr] gap-5 mt-5">
          <section className="panel p-6">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-surface_border bg-white/[0.02]"><ShieldCheck size={17} /></span>
                <div><p className="font-medium">Payment provider</p><p className="text-xs text-text_primary/35 mt-1">Live connection</p></div>
              </div>
              <span className="status-pill border-surface_border text-text_primary/40">NOT CONNECTED</span>
            </div>
            <div className="mt-7 rounded-xl border border-dashed border-surface_border p-5">
              <div className="flex items-start gap-3">
                <AlertCircle size={16} className="text-amber/70 mt-0.5 shrink-0" />
                <div>
                  <p className="text-sm">No provider credentials configured</p>
                  <p className="text-xs text-text_primary/40 leading-relaxed mt-2">
                    The current build supports a Razorpay-shaped adapter boundary, but this workspace has no live provider connection. No green status is shown.
                  </p>
                </div>
              </div>
              <div className="mt-5 pt-5 border-t border-surface_border">
                <p className="text-[11px] uppercase tracking-[0.12em] text-text_primary/25">Required before live sync</p>
                <p className="text-xs text-text_primary/40 mt-2">Server-side credentials · tenant-aware routing · webhook verification</p>
              </div>
            </div>
          </section>

          <section className="panel overflow-hidden">
            <div className="px-6 py-5 border-b border-surface_border">
              <div className="flex items-center justify-between gap-4">
                <div><p className="label-eyebrow text-text_primary/25">READ-ONLY IMPORT</p><h2 className="font-display text-xl mt-1">Import a payout ledger</h2></div>
                <span className="status-pill border-amber/25 text-amber/70">CSV</span>
              </div>
              <p className="text-xs text-text_primary/40 mt-3">Inspect locally first. Nothing leaves the browser until you explicitly import it.</p>
            </div>

            <div className="p-6">
              <div
                onDragOver={e => { e.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onDrop={e => { e.preventDefault(); setDragging(false); inspect(e.dataTransfer.files?.[0] || null); }}
                onClick={() => inputRef.current?.click()}
                className={`rounded-2xl border border-dashed p-8 text-center cursor-pointer transition ${dragging ? "border-text_primary/40 bg-white/[0.04]" : "border-surface_border hover:border-text_primary/20 hover:bg-white/[0.02]"}`}
              >
                <UploadCloud size={22} className="mx-auto text-text_primary/35" />
                <p className="text-sm mt-4">{file ? file.name : "Drop a CSV here or choose a file"}</p>
                <p className="text-xs text-text_primary/30 mt-2">Payout ledger · local preview · no upload yet</p>
                <input ref={inputRef} type="file" accept=".csv,text/csv" className="hidden" onChange={e => inspect(e.target.files?.[0] || null)} />
              </div>

              {file && (
                <div className="mt-4 rounded-xl border border-surface_border p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="text-sm font-medium">{file.name}</p>
                      <p className="text-[11px] text-text_primary/30 mt-1">{(file.size / 1024).toFixed(1)} KB · local inspection</p>
                    </div>
                    <button aria-label="Clear file" onClick={() => { setFile(null); setPreview(null); }} className="text-text_primary/30 hover:text-text_primary"><X size={14} /></button>
                  </div>
                  {preview ? (
                    <div className="mt-4">
                      <div className="flex items-center gap-2 text-xs text-emerald"><CheckCircle2 size={13} /> {preview.rows.toLocaleString()} data rows detected</div>
                      <div className="flex flex-wrap gap-1.5 mt-3">
                        {preview.columns.slice(0, 10).map(column => <span key={column} className="status-pill border-surface_border text-text_primary/40 normal-case tracking-normal">{column}</span>)}
                      </div>
                    </div>
                  ) : (
                    <p className="text-xs text-amber/70 mt-3">Preview unavailable. The file remains local and has not been imported.</p>
                  )}
                </div>
              )}

              <label className="block text-xs text-text_primary/45 mt-5">Merchant / business represented by this ledger
                <input value={merchantName} onChange={e => setMerchantName(e.target.value)} placeholder="Northstar Finance" className="mt-2 w-full rounded-xl border border-surface_border bg-graphite px-3 py-3 text-sm focus-ring" />
              </label>

              <label className="block text-xs text-text_primary/45 mt-5">Import purpose
                <select value={importMode} onChange={e => setImportMode(e.target.value as "baseline" | "monitor")} className="mt-2 w-full rounded-xl border border-surface_border bg-graphite px-3 py-3 text-sm focus-ring">
                  <option value="baseline">Historical baseline</option>
                  <option value="monitor">New payout activity</option>
                </select>
                <p className="mt-2 text-[11px] leading-relaxed text-text_primary/35">{importMode === "baseline" ? "Use a prior, known-good payout period to establish currency-specific behaviour. This import will not create anomaly cases." : "Use a later period to compare each payout against earlier same-currency history. At least 10 earlier observations are required before a score is produced."}</p>
              </label>

              {importError && <div className="mt-4 rounded-xl border border-vermillion/25 bg-vermillion/[0.04] p-4 text-xs text-vermillion">{importError}</div>}

              {importResult && (
                <div className="mt-4 rounded-xl border border-emerald/20 bg-emerald/[0.03] p-4">
                  <div className="flex items-center gap-2 text-sm text-emerald"><CheckCircle2 size={14} /> Source accepted by backend</div>
                  <div className="grid sm:grid-cols-3 gap-3 mt-4">
                    <Mini label="Imported" value={String(importResult.imported_rows || 0)} />
                    <Mini label="Incidents" value={String(importResult.incident_count || 0)} />
                    <Mini label="Mode" value={String(importResult.import_mode || importMode).toUpperCase()} />
                  </div>
                  {importResult.monitoring_note && <p className="mt-4 text-[11px] leading-relaxed text-text_primary/45">{importResult.monitoring_note}</p>}
                  <Link to="/app/incidents" className="inline-flex items-center gap-2 mt-4 text-xs text-text_primary/55 hover:text-text_primary">Open incident queue <ChevronRight size={13} /></Link>
                </div>
              )}

              <div className="mt-5 flex flex-wrap items-center gap-3">
                <button disabled={!file || !preview || !merchantName.trim() || importing || !hasAccessTokenProvider()} onClick={importCsv} className="btn-primary">
                  {importing ? "Importing…" : importMode === "baseline" ? "Establish baseline" : "Monitor this period"}
                </button>
                {!hasAccessTokenProvider() && <span className="text-[11px] text-amber/60">Workspace identity must be established first.</span>}
              </div>
            </div>
          </section>
        </div>

        <section className="panel p-6 mt-5">
          <div className="flex items-center gap-2"><History size={16}/><div><p className="label-eyebrow text-text_primary/25">SOURCE HISTORY</p><h2 className="font-display text-xl mt-1">Recent acceptance</h2></div></div>
          {lastImport ? (
            <div className="mt-5 flex items-center justify-between gap-4 rounded-xl border border-surface_border p-4">
              <div className="flex items-center gap-3">
                <CheckCircle2 size={15} className="text-emerald" />
                <div><p className="text-sm">{sessionStorage.getItem("primhora_last_merchant") || "Imported ledger"}</p><p className="text-xs text-text_primary/35 mt-1">CSV accepted at {new Date(lastImport).toLocaleString()}</p></div>
              </div>
              <span className="status-pill border-emerald/20 text-emerald">ACCEPTED</span>
            </div>
          ) : (
            <div className="mt-5 rounded-xl border border-dashed border-surface_border p-8 text-center">
              <p className="text-sm text-text_primary/40">No source has been accepted into this workspace yet.</p>
            </div>
          )}
        </section>

        <p className="text-[11px] text-text_primary/25 mt-6">
          Provider credentials, webhook secrets and other sensitive configuration remain server-side. The UI is not a security boundary.
        </p>
      </div>
    </div>
  );
}

function SummaryCard({ label, value, sub }: { label: string; value: string; sub: string }) {
  return <div className="panel p-5"><p className="label-eyebrow text-text_primary/25">{label}</p><p className="font-display text-2xl mt-3">{value}</p><p className="text-[11px] text-text_primary/30 mt-1">{sub}</p></div>;
}

function Mini({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl border border-surface_border p-3"><p className="text-[10px] uppercase tracking-wide text-text_primary/25">{label}</p><p className="font-mono text-xs mt-2">{value}</p></div>;
}
