import { motion, useMotionValue, useSpring, useTransform } from 'framer-motion';
import {
  ArrowRight, CheckCircle2, ChevronDown, FileSearch, Fingerprint, Play,
  ScanLine, ShieldAlert, ShieldCheck, Sparkles, Activity, Database,
} from 'lucide-react';
import { useRef } from 'react';

const PRODUCT_URL = 'https://firsthour-ui-n4cc.onrender.com/';

function TiltCard({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const rotateX = useSpring(useTransform(y, [-0.5, 0.5], [7, -7]), { stiffness: 180, damping: 18 });
  const rotateY = useSpring(useTransform(x, [-0.5, 0.5], [-7, 7]), { stiffness: 180, damping: 18 });
  return (
    <motion.div ref={ref} className={className} style={{ rotateX, rotateY, transformStyle: 'preserve-3d' }}
      onPointerMove={(event) => {
        if (!ref.current) return;
        const rect = ref.current.getBoundingClientRect();
        x.set((event.clientX - rect.left) / rect.width - 0.5);
        y.set((event.clientY - rect.top) / rect.height - 0.5);
      }}
      onPointerLeave={() => { x.set(0); y.set(0); }}>
      {children}
    </motion.div>
  );
}

const layers = [
  { number: '01', icon: FileSearch, title: 'AI interprets', text: 'Unstructured evidence becomes candidate claims with source references. Candidate claims stay untrusted until verified.', accent: 'orange' },
  { number: '02', icon: CheckCircle2, title: 'Code establishes truth', text: 'Reconciliation, timestamps, amounts, identifiers and exposure come from deterministic records and calculations.', accent: 'lime' },
  { number: '03', icon: ShieldCheck, title: 'Humans resolve uncertainty', text: 'Authorization and intent remain human responsibilities. PRIMHORA prepares evidence without executing recovery.', accent: 'bone' },
];

function App() {
  return (
    <div className="site-shell">
      <div className="noise" aria-hidden="true" /><div className="ambient ambient-one" aria-hidden="true" /><div className="ambient ambient-two" aria-hidden="true" />
      <nav className="nav">
        <a className="brand" href="#" aria-label="PRIMHORA home"><span className="brand-mark"><ShieldAlert size={17} /></span><span>PRIMHORA</span></a>
        <div className="nav-meta"><span className="status-dot" /><span>Evidence intelligence system</span></div>
        <a className="nav-cta" href={PRODUCT_URL} target="_blank" rel="noreferrer">Explore product <ArrowRight size={15} /></a>
      </nav>

      <main>
        <section className="hero">
          <div className="hero-grid" aria-hidden="true" />
          <div className="hero-copy">
            <motion.div className="eyebrow" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .7 }}><span className="eyebrow-pulse" />Financial incident investigation</motion.div>
            <motion.h1 initial={{ opacity: 0, y: 35 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .85, delay: .08 }}>When money moves <span>wrong,</span><em>know what you can prove.</em></motion.h1>
            <motion.p className="hero-lede" initial={{ opacity: 0, y: 25 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .8, delay: .18 }}>PRIMHORA reconstructs financial incidents from source records and fragmented evidence, verifies claims deterministically, and prepares an auditable evidence packet for human resolution.</motion.p>
            <motion.div className="hero-actions" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .7, delay: .3 }}>
              <a className="button button-primary" href={PRODUCT_URL} target="_blank" rel="noreferrer">Explore the product <ArrowRight size={17} /></a>
              <a className="button button-ghost" href="#architecture"><Play size={15} /> See the system</a>
            </motion.div>
            <motion.div className="hero-note" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: .55, duration: .7 }}><span>READ-ONLY BY DESIGN</span><span>•</span><span>SYNTHETIC DEMO DATA</span><span>•</span><span>NO MONEY IS MOVED</span></motion.div>
          </div>

          <div className="hero-object-wrap" aria-hidden="true"><motion.div className="hero-object" initial={{opacity:0,scale:.8,rotateY:-25}} animate={{opacity:1,scale:1,rotateY:0}} transition={{duration:1.15,delay:.2,type:'spring',stiffness:65}}><div className="prism-shadow"/><div className="prism"><div className="prism-face prism-front"><Fingerprint size={26}/><strong>PROVENANCE</strong><small>01 / SOURCE</small></div><div className="prism-face prism-back"><Database size={22}/><strong>RECORD</strong><small>02 / STATE</small></div><div className="prism-face prism-right"><CheckCircle2 size={23}/><strong>VERIFY</strong><small>03 / LOGIC</small></div><div className="prism-face prism-left"><ShieldCheck size={23}/><strong>DECIDE</strong><small>04 / HUMAN</small></div><div className="prism-face prism-top"><ScanLine size={24}/><strong>EVIDENCE</strong></div></div><div className="prism-ring ring-one"/><div className="prism-ring ring-two"/><div className="float-tag tag-top"><Activity size={13}/> EVIDENCE GRAPH</div><div className="float-tag tag-right"><Fingerprint size={13}/> SOURCE LOCKED</div><div className="float-tag tag-bottom"><Database size={13}/> AUDIT READY</div></motion.div></div><a className="scroll-cue" href="#architecture" aria-label="Scroll to architecture"><span>SCROLL TO DECODE</span><ChevronDown size={15} /></a>
        </section>

        <section id="architecture" className="section architecture">
          <div className="section-heading"><div><span className="section-kicker">THE AUTHORITY STACK</span><h2>Three layers.<br /><span>One defensible answer.</span></h2></div><p>AI can interpret evidence. It cannot manufacture financial truth. PRIMHORA separates those jobs.</p></div>
          <div className="layer-grid">
            {layers.map((layer, index) => {
              const Icon = layer.icon;
              return <TiltCard key={layer.number} className="layer-card">
                <div className={`layer-accent ${layer.accent}`} /><div className="layer-top"><span className="layer-number">{layer.number}</span><Icon size={21} /></div>
                <div className="layer-content"><h3>{layer.title}</h3><p>{layer.text}</p></div>
                <div className="layer-line"><motion.span initial={{ width: 0 }} whileInView={{ width: index === 0 ? '42%' : index === 1 ? '68%' : '92%' }} viewport={{ once: true }} transition={{ duration: 1, delay: .15 * index }} /></div>
              </TiltCard>;
            })}
          </div>
        </section>

        <section className="section proof-section">
          <div className="proof-frame">
            <div className="proof-orbit" aria-hidden="true" />
            <div className="proof-copy"><span className="section-kicker">THE DIFFERENCE</span><h2>From <span>“something looks wrong”</span> to an evidence packet someone can actually defend.</h2><p>Every conclusion has a trail. Source records establish facts. Calculations expose mismatches. Human review owns the final decision.</p><a className="text-link" href={PRODUCT_URL} target="_blank" rel="noreferrer">Open PRIMHORA <ArrowRight size={16} /></a></div>
            <div className="proof-console" aria-hidden="true">
              <div className="console-bar"><span /><span /><span /><b>incident_042</b></div>
              <div className="console-row"><i>01</i><span>source_payment</span><strong>₹ 48,200</strong></div>
              <div className="console-row"><i>02</i><span>ledger_record</span><strong>₹ 48,200</strong></div>
              <div className="console-row warning"><i>03</i><span>authorization</span><strong>UNRESOLVED</strong></div>
              <div className="console-row"><i>04</i><span>evidence_integrity</span><strong>VERIFIED</strong></div>
              <div className="console-stamp">HUMAN DECISION REQUIRED</div>
            </div>
          </div>
        </section>

        <section className="section closing"><Sparkles size={18} /><span className="section-kicker">THE LAST WORD</span><h2>Financial investigation should feel less like a spreadsheet hunt and more like an instrument panel.</h2><a className="button button-primary" href={PRODUCT_URL} target="_blank" rel="noreferrer">Enter PRIMHORA <ArrowRight size={17} /></a></section>
      </main>

      <footer><span>PRIMHORA © 2026</span><span>Financial incident investigation infrastructure</span><span>READ-ONLY • AUDITABLE • HUMAN-GOVERNED</span></footer>
    </div>
  );
}
export default App;
