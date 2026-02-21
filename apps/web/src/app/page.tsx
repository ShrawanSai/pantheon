"use client";

import { useMemo, useState } from "react";

type ApiCheckResult = {
  ok: boolean;
  status: number | null;
  body: string;
};

const defaultResult: ApiCheckResult = { ok: false, status: null, body: "" };

export default function HomePage() {
  const apiBase = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000",
    []
  );
  const [token, setToken] = useState("");
  const [healthResult, setHealthResult] = useState<ApiCheckResult | null>(null);
  const [authResult, setAuthResult] = useState<ApiCheckResult | null>(null);
  const [loadingHealth, setLoadingHealth] = useState(false);
  const [loadingAuth, setLoadingAuth] = useState(false);

  async function runCheck(path: string, tokenValue?: string): Promise<ApiCheckResult> {
    try {
      const headers: HeadersInit = {};
      if (tokenValue) {
        headers.Authorization = `Bearer ${tokenValue}`;
      }
      const response = await fetch(`${apiBase}${path}`, { method: "GET", headers });
      const body = await response.text();
      return { ok: response.ok, status: response.status, body };
    } catch (error) {
      return {
        ...defaultResult,
        body: error instanceof Error ? error.message : "Unknown network error"
      };
    }
  }

  async function checkHealth() {
    setLoadingHealth(true);
    setHealthResult(await runCheck("/api/v1/health"));
    setLoadingHealth(false);
  }

  async function checkAuth() {
    setLoadingAuth(true);
    setAuthResult(await runCheck("/api/v1/auth/me", token.trim()));
    setLoadingAuth(false);
  }

  return (
    <>
      <h1>Pantheon MVP Connectivity Check</h1>
      <p className="muted">
        Uses <code>NEXT_PUBLIC_API_BASE_URL</code> (<code>{apiBase}</code>) to verify backend routes.
      </p>

      <section className="card">
        <h3>Health Endpoint</h3>
        <p className="muted">Checks <code>/api/v1/health</code>.</p>
        <button onClick={checkHealth} disabled={loadingHealth}>
          {loadingHealth ? "Checking..." : "Check Health"}
        </button>
        {healthResult ? <ResultPanel result={healthResult} /> : null}
      </section>

      <section className="card">
        <h3>Auth Endpoint</h3>
        <p className="muted">Checks <code>/api/v1/auth/me</code> with bearer token.</p>
        <label htmlFor="token-input" className="muted">Supabase access token</label>
        <input
          id="token-input"
          className="text-input"
          value={token}
          onChange={(event) => setToken(event.target.value)}
          placeholder="Paste bearer token here"
        />
        <button onClick={checkAuth} disabled={loadingAuth}>
          {loadingAuth ? "Checking..." : "Check Auth"}
        </button>
        {authResult ? <ResultPanel result={authResult} /> : null}
      </section>
    </>
  );
}

function ResultPanel({ result }: { result: ApiCheckResult }) {
  return (
    <div className="result-panel">
      <div>
        <strong>ok:</strong> {String(result.ok)}
      </div>
      <div>
        <strong>status:</strong> {result.status ?? "n/a"}
      </div>
      <pre>{result.body || "(empty body)"}</pre>
    </div>
  );
}
