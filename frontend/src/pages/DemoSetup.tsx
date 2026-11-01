import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Building2, CheckCircle2, CreditCard, ShieldCheck } from "lucide-react";
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
    description: "Create a simulated financial workspace from the details on this screen.",
  },
  {
    number: "02",
    title: "Investigate",
    description: "Explore a synthetic payment incident and follow the evidence trail.",
  },
  {
    number: "03",
    title: "Recover",
    description: "Review the findings and prepare a simulated, human-approved recovery packet.",
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
    setForm((current) => ({ ...current, [key]: value }))¶»§q«^