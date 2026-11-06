/** Primhora API client.
 *
 * Demo authentication is issued dynamically by the backend at /demo/session.
 * No static bearer credentials are embedded in the frontend bundle.
 * Production authentication remains an OIDC/JWT integration and must replace
 * the demo session mechanism before real customer data is enabled.
 */
const BASE = import.meta.env.VITE_API_BASE_URL || "/api";

// Render's free instance can sleep after inactivity. Wake it through the
// database-aware health check, then retry transient proxy/startup failures.
// The demo-session POST is idempotent: it returns an existing synthetic user
// token and does not create financial records or mutate customer data.
const TRANSIENT_HTTP_STATUSES = new Set([502, 503, 504, 520, 521, 522, 523, 524]);
const COLD_START_RETRY_DELAYS_MS = [1_000, 2_000, 4_000, 7_000, 10_000, 10_000, 10_000];

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function fetchThroughColdStart(
  url: string,
  init: RequestInit,
): Promise<Response> {
  let lastNetworkError: unknown;

  for (let attempt = 0; attempt <= COLD_START_RETRY_DELAYS_MS.length; attempt += 1) {
    try {
      const response = await fetch(url, { ...init, cache: "no-store" });
      if (!TRANSIENT_HTTP_STATUSES.has(response.status) || attempt === COLD_START_RETRY_DELAYS_MS.length) {
        return response;
      }
      lastNetworkError = new Error(`Temporary API response: HTTP ${response.status}`);
    } catch (error) {
      lastNetworkError = error;
    }

    const retryDelay = COLD_START_RETRY_DELAYS_MS[attempt];
    if (retryDelay !== undefined) await delay(retryDelay);
  }

  throw new Error(
    `PRIMHORA API did not wake successfully. ${lastNetworkError instanceof Error ? lastNetworkError.message : "Network request failed."}`,
  );
}

// Demo credentials are issued by the backend at runtime and are never bundled.
let DEMO_TOKEN = "";
let WORKSPACE_TOKEN = "";
try { WORKSPACE_TOKEN = sessionStorage.getItem("primhora_workspace_token") || ""; } catch {}
const DEMO_TOKENS: Record<string, string> = {};

export async function getDemoToken(role = "ADMINISTRATOR"): Promise<string> {
  if (DEMO_TOKENS[role]) return DEMO_TOKENS[role];

  // A health request wakes a sleeping Render instance before session creation.
  // The retry loop also covers transient 502/503/504 responses during startup.
  const health = await fetchThroughColdStart(`${BASE}/health`, { method: "GET" });
  if (!health.ok) {
    throw new Error(`PRIMHORA API health check failed (HTTP ${health.status}). Try again once the service is awake.`);
  }

  const res = await fetchThroughColdStart(
    `${BASE}/demo/session?role=${encodeURIComponent(role)}`,
    { method: "POST" },
  );
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      detail = typeof body?.detail === "string" ? body.detail : "";
    } catch {
      detail = res.statusText;
    }
    throw new Error(detail || `Demo session could not be established (HTTP ${res.status})`);
  }

  const data = await res.json();
  if (typeof data?.token !== "string" || !data.token) {
    throw new Error("The demo service responded without a session token.");
  }
  DEMO_TOKENS[role] = data.token;
  if (role === "ADMINISTRATOR") DEMO_TOKEN = data.token;
  return data.token;
}

let getAccessToken: (() => Promise<string>) | null = WORKSPACE_TOKEN
  ? async () => WORKSPACE_TOKEN
  : null;
export function setAccessTokenProvider(provider: () => Promise<string>) {
  getAccessToken = provider;
}
export function hasAccessTokenProvider() {
  return Boolean(getAccessToken);
}

export function setWorkspaceToken(token: string) {
  WORKSPACE_TOKEN = token;
  getAccessToken = async () => WORKSPACE_TOKEN;
  try { sessionStorage.setItem("primhora_workspace_token", token); } catch {}
}

export function clearWorkspaceToken() {
  WORKSPACE_TOKEN = "";
  getAccessToken = null;
  try { sessionStorage.removeItem("primhora_workspace_token"); } catch {}
}

export class APIError extends Error {
  constructor(public status: number, public data: any) {
    const detail = typeof data?.detail === "string"
      ? data.detail
      : Array.isArray(data?.detail)
        ? data.detail.map((item: any) => item?.msg || String(item)).join("; ")
        : null;
    super(detail || `Request failed (${status})`);
    this.status = status;
    this.data = data;
    this.name = "APIError";
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  // In production the configured OIDC provider owns authentication. Do not
  // touch the demo-session endpoint when an access-token provider exists.
  if (getAccessToken) return requestAs<T>("", path, options);
  const token = await getDemoToken("ADMINISTRATOR");
  return requestAs<T>(token, path, options);
}

async function requestAs<T>(token: string, path: string, options?: RequestInit): Promise<T> {
  const actualToken = getAccessToken ? await getAccessToken() : token;
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${actualToken}`,
      ...(options?.headers || {}),
    },
  });

  if (!res.ok) {
    let data;
    try {
      data = await res.json();
    } catch {
      data = { detail: res.statusText };
    }
    throw new APIError(res.status, data);
  }

  // 204 No Content
  if (res.status === 204) {
    return {} as T;
  }

  return res.json();
}

export const api = {
  getWorkspace: () => request<any>("/workspace"),
  createWorkspace: (name: string, industry: string) =>
    request<any>("/workspace", {
      method: "POST",
      body: JSON.stringify({ name, industry }),
    }),
  getMerchantConnection: (merchantId: string) =>
    request<any>(`/merchant/${merchantId}/connection`),
  getMerchantBaseline: (merchantId: string) =>
    request<any>(`/merchant/${merchantId}/baseline`),
  syncMerchant: (merchantId: string) =>
    request<any>(`/merchant/${merchantId}/sync`, { method: "POST" }),

  listIncidents: () => request<any[]>(`/incidents`),
  getIncident: (incidentId: string) => request<any>(`/incident/${incidentId}`),
  getTimeline: (incidentId: string) => request<any[]>(`/incident/${incidentId}/timeline`),
  getGraph: (incidentId: string) => request<any>(`/incident/${incidentId}/graph`),
  getExposure: (incidentId: string) => request<any>(`/incident/${incidentId}/exposure`),
  getEvidence: (incidentId: string) => request<any>(`/incident/${incidentId}/evidence`),
  getNextQuestion: (incidentId: string) => request<any>(`/incident/${incidentId}/questions/next`),
  postAttestation: (incidentId: string, body: { question_id: string; answer: string; note?: string }) =>
    request<any>(`/incident/${incidentId}/attestation`, { method: "POST", body: JSON.stringify(body) }),
  getRecoveryPacket: (incidentId: string) => request<any>(`/incident/${incidentId}/recovery-packet`),
  downloadRecoveryPacketPdf: async (incidentId: string) => {
    const token = getAccessToken ? await getAccessToken() : await getDemoToken("ADMINISTRATOR");
    const res = await fetch(`${BASE}/incident/${incidentId}/recovery-packet.pdf`, { headers: { Authorization: `Bearer ${token}` } });
    if (!res.ok) throw new APIError(res.status, { detail: await res.text() });
    return res.blob();
  },
  getAudit: (incidentId: string) => request<any[]>(`/incident/${incidentId}/audit`),

  uploadEvidence: async (file: File, merchantId: string, incidentId: string, sourceLabel: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("merchant_id", merchantId);
    form.append("incident_id", incidentId);
    form.append("source_label", sourceLabel);
    const res = await fetch(`${BASE}/evidence/upload`, {
      method: "POST", body: form,
      headers: { "Authorization": `Bearer ${getAccessToken ? await getAccessToken() : await getDemoToken("ADMINISTRATOR")}` },
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  analyzeEvidence: async (artifactId: string) => {
    const form = new FormData();
    form.append("artifact_id", artifactId);
    const res = await fetch(`${BASE}/evidence/analyze`, {
      method: "POST", body: form,
      headers: { "Authorization": `Bearer ${getAccessToken ? await getAccessToken() : await getDemoToken("ADMINISTRATOR")}` },
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  injectIncident: (scenario: string, merchantId: string) =>
    request<any>(`/demo/inject-incident`, {
      method: "POST",
      body: JSON.stringify({ scenario, merchant_id: merchantId }),
    }),
  resetDemo: async () => {
    const result = await request<any>(`/demo/reset`, { method: "POST" });
    DEMO_TOKEN = "";
    delete DEMO_TOKENS.ADMINISTRATOR;
    return result;
  },

  getMetrics: () => request<any>(`/metrics`),
  getEvaluation: () => request<any>(`/evaluation`),

  // --- Recovery Command (propose/review/approve/reject/execute/verify) ---
  // These accept an explicit acting-role token so the UI can demonstrate
  // real RBAC enforcement (e.g. an Investigator token genuinely cannot
  // approve) rather than always acting as the one admin demo user.
  listRecoveryCommands: (incidentId: string) =>
    request<any[]>(`/incident/${incidentId}/recovery-commands`),
  proposeRecoveryCommand: (incidentId: string, body: any, actingToken: string) =>
    requestAs<any>(actingToken, `/incident/${incidentId}/recovery-commands`, {
      method: "POST", body: JSON.stringify(body),
    }),
  dryRunCommand: (commandId: string, actingToken: string) =>
    requestAs<any>(actingToken, `/recovery-commands/${commandId}/dry-run`, { method: "POST" }),
  reviewCommand: (commandId: string, actingToken: string) =>
    requestAs<any>(actingToken, `/recovery-commands/${commandId}/review`, { method: "POST" }),
  approveCommand: (commandId: string, actingToken: string) =>
    requestAs<any>(actingToken, `/recovery-commands/${commandId}/approve`, { method: "POST" }),
  rejectCommand: (commandId: string, actingToken: string, reason: string) =>
    requestAs<any>(actingToken, `/recovery-commands/${commandId}/reject`, {
      method: "POST", body: JSON.stringify({ reason }),
    }),
  preparePacket: (commandId: string, actingToken: string) =>
    requestAs<any>(actingToken, `/recovery-commands/${commandId}/prepare-packet`, { method: "POST" }),
  verifyCommand: (commandId: string, actingToken: string) =>
    requestAs<any>(actingToken, `/recovery-commands/${commandId}/verify`, { method: "POST" }),
  getConvergence: (commandId: string) =>
    request<any>(`/recovery-commands/${commandId}/convergence`),
  importPayoutCsv: async (file: File, merchantName: string, importMode: "baseline" | "monitor" = "monitor") => {
    const token = getAccessToken ? await getAccessToken() : await getDemoToken("ADMINISTRATOR");
    const form = new FormData();
    form.append("file", file);
    form.append("merchant_name", merchantName);
    form.append("import_mode", importMode);
    const res = await fetch(`${BASE}/import/payouts-csv`, { method: "POST", body: form, headers: { Authorization: `Bearer ${token}` } });
    if (!res.ok) { let data:any; try { data = await res.json(); } catch { data = {detail: res.statusText}; } throw new APIError(res.status, data); }
    return res.json();
  },
};

export const FLAGSHIP_MERCHANT_ID = "MER_ARROW";
export const CHAOS_MERCHANT_ID = "MER_HARBOR";
export const FLAGSHIP_INCIDENT_ID = "INC-001";

