const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type RunRecord = {
  run_id: string;
  started_at: string;
  finished_at: string | null;
  status: "running" | "completed" | "failed";
  current_stage: string | null;
  topic: string | null;
  script_preview: string | null;
  pictory_draft_url: string | null;
  stage_timings: Record<string, number>;
  error: string | null;
};

export type Settings = {
  schedule_time: string;
  timezone: string;
  topic_source: string;
  youtube_category_id: string;
  script_language: string;
  alert_email: string;
  alert_webhook_url: string;
  cleanup_days: number;
  history_max_entries: number;
};

export async function fetchStatus(): Promise<RunRecord | null> {
  const res = await fetch(`${BASE}/api/status`, { cache: "no-store" });
  if (!res.ok) return null;
  return res.json();
}

export async function triggerRun(mode?: "short" | "long"): Promise<{ run_id: string; message: string }> {
  const res = await fetch(`${BASE}/api/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode: mode ?? null }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail ?? "Failed to start run");
  }
  return res.json();
}

export async function fetchHistory(page = 1, perPage = 20) {
  const res = await fetch(`${BASE}/api/history?page=${page}&per_page=${perPage}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to fetch history");
  return res.json() as Promise<{ total: number; page: number; per_page: number; items: RunRecord[] }>;
}

export async function fetchSettings(): Promise<Settings> {
  const res = await fetch(`${BASE}/api/settings`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch settings");
  return res.json();
}

export async function saveSettings(payload: Partial<Settings>): Promise<void> {
  const res = await fetch(`${BASE}/api/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail ?? "Failed to save settings");
  }
}

export async function fetchLogs(lines = 200): Promise<string[]> {
  const res = await fetch(`${BASE}/api/logs?lines=${lines}`, { cache: "no-store" });
  if (!res.ok) return [];
  const data = await res.json();
  return data.lines ?? [];
}
