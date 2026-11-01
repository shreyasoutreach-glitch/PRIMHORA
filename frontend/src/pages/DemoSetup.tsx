import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Building2, CreditCard, ShieldCheck } from "lucide-react";
import { StepFooter } from "../components/AppShell";

const FIELDS = [
  { key: "business", label: "Business name", wide: true, autoComplete: "organization" },
  { key: "holder", label: "Account holder", autoComplete: "off" },
  { key: "bank", label: "Bank / institution", autoComplete: "off" },
  { key: "account", label: "Account number", autoComplete: "off", inputMode: "numeric" as const },
  { key: "ifsc", label: "IFSC / routing code", autoComplete: "off" },
] as const;

const NEXT_STEPS = [
  {
    number: "01",
    title: "Connect",
    description: "Establish the synthetic financial workspace and review the available data boundary.",
  },
  {
    number: "02",
    title: "Investigate",
    description: "Follow a simulated payment incident through its evidence and transaction history.",
  },
  {
    number: "03",
    title: "Recover",
    description: "Review the findings and prepare a human-reviewed recovery packet.",
  },
];

export default function DemoSetup() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    business: "Arrow Industries",
    holder: "Arrow Industries Pvt. Ltd.",
    bank: "Demo Bank",
    account: "001234567890",
    ifsc: "DEMO0001234",
  });

  const update = (key: keyof typeof form, value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const start = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    // This profile is demo-only. Storage failure must not block the synthetic workflow.
    try {
      sessionStorage.setItem("primhora_demo_account", JSON.stringify(form));
    } catch {
      // The demo can continue without the optional display profile.
    }
    navigate("/connect?mode=demo");
  };

  return (
    <main className="workspace-page">
      <section className="workspace-heading">
        <p className="label-eyebrow workspace-kicker">Demo setup <span aria-hidden="true">/</span> 01 of 03</p>
        <h1 className="font-display workspace-title">
          Give PRIMHORA a financial account to work with.
        </h1>
        <p className="workspace-lede">
          Set up a fictional business profile for the demonstration. PRIMHORA uses a synthetic ledger;
          no bank, payment gateway, or external financial network is contacted.
        </p>
      </section>

      <div className="workspace-layout">
        <form onSubmit={start} className="paper-card workspace-form-card">
          <div className="workspace-card-heading">
            <div className="workspace-card-icon" aria-hidden="true">
              <Building2 size={19} strokeWidth={1.8} />
            </div>
            <div className="min-w-0">
              <h2 className="font-display workspace-card-title">Business workspace</h2>
              <p className="workspace-card-subtitle">Use fictional details for this demo.</p>
            </div>
            <span className="workspace-mode">DEMO MODE</span>
          </div>

          <div className="workspace-fields">
            {FIELDS.map((field) => (
              <label
                key={field.key}
                htmlFor={`demo-${field.key}`}
                className={"wide" in field && field.wide ? "workspace-field workspace-field-wide" : "workspace-field"}
              >
                <span className="label-eyebrow workspace-field-label">{field.label}</span>
                <input
                  id={`demo-${field.key}`}
                  name={field.key}
                  type="text"
                  inputMode={"inputMode" in field ? field.inputMode : "text"}
                  autoComplete={field.autoComplete}
                  value={form[field.key]}
                  onChange={(event) => update(field.key, event.target.value)}
                  maxLength={field.key === "account" ? 18 : 96}
                  spellCheck={false}
                  required
                  className="workspace-input"
                  aria-describedby="demo-data-note"
                />
              </label>
            ))}
          </div>

          <div id="demo-data-note" className="workspace-note" role="note">
            <ShieldCheck size={18} className="workspace-note-icon" aria-hidden="true" />
            <p>
              <strong>Demo data only.</strong> These details are used for the on-screen demonstration.
              PRIMHORA does not validate or connect this account. Never enter real banking credentials.
            </p>
          </div>

          <div className="workspace-form-footer">
            <button className="btn-primary workspace-submit" type="submit">
              Enter the PRIMHORA demo <ArrowRight size={16} />
            </button>
            <span className="workspace-footer-hint">No live financial action will be performed.</span>
          </div>
        </form>

        <aside className="paper-card workspace-steps-card" aria-labelledby="workspace-next-title">
          <div className="workspace-aside-icon" aria-hidden="true">
            <CreditCard size={19} strokeWidth={1.8} />
          </div>
          <p id="workspace-next-title" className="label-eyebrow workspace-aside-kicker">What happens next</p>
          <ol className="workspace-steps-list">
            {NEXT_STEPS.map((step) => (
              <li key={step.number} className="workspace-step">
                <span className="workspace-step-index">{step.number}</span>
                <div className="min-w-0">
                  <h3 className="font-display workspace-step-title">{step.title}</h3>
                  <p className="workspace-step-copy">{step.description}</p>
                </div>
              </li>
            ))}
          </ol>
          <div className="workspace-aside-foot">
            <span className="workspace-aside-status" aria-hidden="true" />
            <span>Isolated synthetic environment</span>
          </div>
        </aside>
      </div>

      <StepFooter current="/connect" />
    </main>
  );
}
