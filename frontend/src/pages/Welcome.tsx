import React from "react";
import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import {
  ArrowRight, Activity, AlertTriangle, CheckCircle2, Database,
  Fingerprint, GitBranch, Play, ShieldCheck, Sparkles, Terminal,
  TimerReset, Workflow
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

const signalRows = [
  { label: "PAYOUT", value: "₹18.42L", note: "recipient cluster", tone: "hot" },
  { label: "LEDGER", value: "11 events", note: "03:14 → 03:19", tone: "warm" },
  { label: "EVIDENCE", value: "7 artifacts", note: "6 verified", tone: "good" },
];

const steps: Array<[string, string, string, LucideIcon]> = [
  ["01", "Detect", "Surface the break before the trail goes cold.", Activity],
  ["02", "Reconstruct", "Turn scattered records into one deterministic timeline.", GitBranch],
  ["03", "Decide", "Keep humans in control of every material action.", ShieldCheck],
];

export default function Welcome() {
  return (
    <div className="landing-page relative overflow-hidden text-white">
      <div className="landing-noise" />
      <div className="landing-grid" />
      <div className="landing-orb landing-orb-one" />
      <div className="landing-orb landing-orb-two" />
      <div className="landing-orb landing-orb-three" />

      <section className="relative mx-auto max-w-canvas px-6 pb-24 pt-16 sm:px-10 sm:pb-32 sm:pt-24">
        <div className="grid gap-14 lg:grid-cols-[1.03fr_.97fr] lg:items-center">
          <div>
            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.65 }}
              className="landing-kicker">
              <span className="landing-pulse-dot" />
              <span>PRIMHORA / FINANCIAL INCIDENT INTELLIGENCE</span>
            </motion.div>

            <motion.h1 initial={{ opacity: 0, y: 22 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08, duration: 0.75 }}
              className="mt-7 max-w-[980px] font-display text-[58px] leading-[0.88] tracking-[-0.055em] sm:text-[88px]">
              Money moved.
              <br />
              <span className="landing-gradient-text">Now reconstruct why.</span>
            </motion.h1>

            <motion.p initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.16, duration: 0.7 }}
              className="mt-8 max-w-[700px] text-[18px] leading-relaxed text-white/58 sm:text-[20px]">
              PRIMHORA converts fractured payment evidence into a source-backed incident record,
              so your team can see what happened, what can be proven, what is exposed, and what
              still needs a human answer.
            </motion.p>

            <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.24, duration: 0.65 }}
              className="mt-9 flex flex-wrap gap-3">
              <Link to="/demo/setup" className="landing-cta landing-cta-primary"><Play size={15} /> Run the synthetic case <ArrowRight size={15} /></Link>
              <Link to="/app" className="landing-cta landing-cta-secondary">Open workspace <ArrowRight size={15} /></Link>
            </motion.div>

            <div className="mt-10 flex flex-wrap items-center gap-x-7 gap-y-3 text-[11px] text-white/36">
              <span className="inline-flex items-center gap-2"><ShieldCheck size={13} className="text-cyan-300" /> Human approval stays in the loop</span>
              <span>Deterministic financial truth</span>
              <span>Read-only by design</span>
            </div>
          </div>

          <motion.div initial={{ opacity: 0, scale: 0.97, y: 16 }} animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={{ delay: 0.18, duration: 0.85 }} className="relative min-h-[520px]">
            <div className="landing-console absolute inset-0">
              <div className="landing-console-bar">
                <div className="flex items-center gap-3">
                  <div className="flex gap-1.5"><span className="landing-window-dot landing-window-red" /><span className="landing-window-dot landing-window-yellow" /><span className="landing-window-dot landing-window-green" /></div>
                  <span className="font-label text-[9px] uppercase tracking-[0.18em] text-white/42">Live reconstruction</span>
                </div>
                <span className="landing-status">Read-only</span>
              </div>

              <div className="grid gap-4 p-5 sm:p-6">
                <div className="grid gap-3 sm:grid-cols-3">
                  {signalRows.map((row, i) => (
                    <motion.div key={row.label} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.45 + i * 0.1, duration: 0.45 }} className={"landing-mini-card landing-mini-"+row.tone}>
                      <div className="flex items-center justify-between">
                        <span className="font-label text-[9px] tracking-[0.16em] text-white/30">{row.label}</span>
                        <span className="landing-signal-dot" />
                      </div>
                      <p className="mt-3 font-display text-[25px] text-white/94">{row.value}</p>
                      <p className="mt-1 text-[10px] text-white/34">{row.note}</p>
                    </motion.div>
                  ))}
                </div>

                <div className="landing-graph-card">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-label text-[9px] uppercase tracking-[0.18em] text-white/30">Incident graph</p>
                      <p className="mt-1 text-xs text-white/56">Entity correlation + evidence chain</p>
                    </div>
                    <span className="landing-verified"><CheckCircle2 size={11} /> VERIFIED</span>
                  </div>

                  <div className="relative mt-6 h-[228px] overflow-hidden rounded-xl border border-white/[0.07] bg-[#080811]/80">
                    <div className="absolute inset-0 opacity-80" style={{backgroundImage:"radial-gradient(circle at 50% 50%, rgba(139,92,246,.15), transparent 42%), linear-gradient(rgba(255,255,255,.035) 1px,transparent 1px), linear-gradient(90deg,rgba(255,255,255,.035) 1px,transparent 1px)",backgroundSize:"auto,28px 28px,28px 28px"}} />
                    <div className="absolute inset-x-8 top-1/2 h-px bg-gradient-to-r from-transparent via-violet-400/30 to-transparent" />
                    <div className="absolute left-[13%] top-[30%] h-px w-[38%] rotate-[15deg] bg-cyan-300/28" />
                    <div className="absolute right-[13%] top-[54%] h-px w-[36%] -rotate-[24deg] bg-fuchsia-300/25" />
                    <div className="absolute left-[31%] top-[31%] h-[110px] w-px rotate-[10deg] bg-violet-300/18" />
                    <div className="absolute left-[67%] top-[38%] h-[95px] w-px -rotate-[14deg] bg-cyan-300/14" />

                    {[
                      ["origin", "16%", "50%", "PAYMENT", "cyan"], ["event", "43%", "29%", "LEDGER", "violet"],
                      ["entity", "69%", "58%", "ENTITY", "pink"], ["evidence", "84%", "27%", "EVIDENCE", "amber"],
                    ].map(([key, left, top, label, tone], i) => (
                      <motion.div key={key} animate={{ y: [0, -6, 0], opacity: [0.72, 1, 0.72], scale: [1, 1.03, 1] }}
                        transition={{ duration: 3.2 + i * 0.35, repeat: Infinity, ease: "easeInOut", delay: i * 0.35 }}
                        className="absolute" style={{ left, top }}>
                        <div className={"landing-node landing-node-"+tone}>
                          <span className="landing-node-core" />
                          <span className="absolute -bottom-5 whitespace-nowrap font-label text-[8px] tracking-[0.14em] text-white/28">{label}</span>
                        </div>
                      </motion.div>
                    ))}

                    <motion.div animate={{ x: ["-15%", "115%"] }} transition={{ duration: 4.6, repeat: Infinity, ease: "linear" }}
                      className="absolute inset-y-0 w-[24%] bg-gradient-to-r from-transparent via-cyan-300/[0.07] to-transparent blur-xl" />
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-[1.1fr_.9fr]">
                  <div className="landing-log-card">
                    <div className="flex items-center gap-2 text-white/38"><Terminal size={12} className="text-cyan-300/70" /><span className="font-label text-[9px] tracking-[0.16em]">TRACE</span></div>
                    <div className="mt-4 space-y-2 font-mono text-[10px] text-white/44">
                      <p><span className="text-cyan-200/45">03:14:22</span> payout.created <span className="text-white/22">#PX-1842</span></p>
                      <p><span className="text-violet-200/48">03:16:08</span> recipient.clustered <span className="text-white/22">+4</span></p>
                      <p><span className="text-fuchsia-200/46">03:19:41</span> evidence.verified <span className="text-emerald-300/75">true</span></p>
                    </div>
                  </div>
                  <div className="landing-recovery-card">
                    <div className="flex items-center justify-between"><span className="font-label text-[9px] tracking-[0.16em] text-white/28">NEXT</span><TimerReset size={13} className="text-violet-200/60" /></div>
                    <p className="mt-3 font-display text-[22px] text-white/88">Human review</p>
                    <p className="mt-1 text-[10px] leading-relaxed text-white/30">Recovery stays blocked until an authorized person decides.</p>
                  </div>
                </div>
              </div>
            </div>

            <motion.div animate={{ y: [0, 9, 0], rotate: [0, 1.5, 0] }} transition={{ duration: 7, repeat: Infinity, ease: "easeInOut" }}
              className="landing-float-card landing-float-evidence">
              <Workflow size={15} className="text-cyan-300" /><div><p>Evidence chain intact</p><span>7 artifacts · 6 verified</span></div>
            </motion.div>

            <motion.div animate={{ y: [0, -7, 0], rotate: [0, -1.2, 0] }} transition={{ duration: 6.2, repeat: Infinity, ease: "easeInOut", delay: 0.4 }}
              className="landing-float-card landing-float-exposure">
              <AlertTriangle size={15} className="text-amber-300" /><div><p>Exposure identified</p><span>₹18.42L across 5 entities</span></div>
            </motion.div>
          </motion.div>
        </div>

        <div className="mt-24 grid gap-3 border-y border-white/10 py-5 sm:grid-cols-3">
          {steps.map(([num, title, copy, Icon], i) => {
            const StepIcon = Icon;
            return <motion.div key={title} initial={{ opacity: 0, y: 10 }} whileInView={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.08, duration: 0.45 }} viewport={{ once: true, margin: "-40px" }}
              className="group flex gap-4 rounded-2xl p-4 transition hover:bg-white/[0.025]">
              <span className="font-label pt-1 text-[10px] text-white/20">{num}</span>
              <div className="flex-1"><div className="flex items-center gap-2"><StepIcon size={14} className="text-cyan-200/70" /><p className="font-display text-[22px]">{title}</p></div><p className="mt-2 max-w-sm text-[12px] leading-relaxed text-white/42">{copy}</p></div>
            </motion.div>;
          })}
        </div>

        <div id="how-it-works" className="mt-24 grid gap-4 lg:grid-cols-[1.05fr_.95fr]">
          <motion.div initial={{ opacity: 0, y: 14 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} className="landing-principle-card">
            <div className="flex items-center gap-2 text-white/48"><Sparkles size={15} className="text-violet-300" /><span className="label-eyebrow text-white/40">THE OPERATING PRINCIPLE</span></div>
            <h2 className="mt-5 max-w-2xl font-display text-[38px] leading-[0.94] tracking-tight sm:text-[52px]">AI can interpret.<br /><span className="landing-gradient-text">It cannot declare truth.</span></h2>
            <p className="mt-6 max-w-xl text-[14px] leading-relaxed text-white/45">Deterministic records anchor the case. Evidence shows where the claim came from. Humans decide what matters. The system keeps the chain intact.</p>
          </motion.div>

          <div className="grid gap-4">
            {([
              [Database, "Source-backed", "Financial events stay tied to their originating records."],
              [Fingerprint, "Evidence-native", "Artifacts, hashes and verification states travel with the case."],
              [ShieldCheck, "Human-governed", "Material recovery actions remain intentionally blocked in the product."],
            ] as Array<[LucideIcon, string, string]>).map(([Icon, title, copy], i) => {
              const ItemIcon = Icon;
              return <motion.div key={title} initial={{ opacity: 0, x: 10 }} whileInView={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.08, duration: 0.45 }} viewport={{ once: true }}
                className="landing-feature-card">
                <div className="flex items-start gap-4"><div className="landing-feature-icon"><ItemIcon size={16} /></div><div><h3 className="font-display text-[23px]">{title}</h3><p className="mt-2 text-[12px] leading-relaxed text-white/42">{copy}</p></div></div>
              </motion.div>;
            })}
          </div>
        </div>

        <motion.div initial={{ opacity: 0, y: 14 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}
          className="mt-24 landing-final-cta">
          <div><p className="label-eyebrow text-cyan-200/55">NEXT MOVE</p><h2 className="mt-2 font-display text-[30px] tracking-tight">See an incident rebuilt from the inside.</h2><p className="mt-2 max-w-2xl text-[12px] leading-relaxed text-white/36">Synthetic data only. No money is moved. Every recovery action in the demo is simulated.</p></div>
          <Link to="/demo/setup" className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-white px-5 py-3 text-sm font-medium text-[#090611] transition hover:-translate-y-0.5 hover:bg-cyan-50">Enter synthetic demo <ArrowRight size={14} /></Link>
        </motion.div>
      </section>
    </div>
  );
}
