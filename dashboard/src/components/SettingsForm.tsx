"use client";

import { useState } from "react";
import type { Settings } from "@/lib/api";
import { saveSettings } from "@/lib/api";

type Props = { initial: Settings };

export default function SettingsForm({ initial }: Props) {
  const [form, setForm] = useState<Settings>(initial);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  function set(key: keyof Settings, value: string | number) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMsg(null);
    try {
      await saveSettings(form);
      setMsg({ ok: true, text: "Settings saved successfully." });
    } catch (err: unknown) {
      setMsg({ ok: false, text: err instanceof Error ? err.message : "Unknown error" });
    } finally {
      setSaving(false);
    }
  }

  const field = "block w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-brand-500";
  const label = "block text-xs font-medium text-gray-400 mb-1";

  return (
    <form onSubmit={handleSubmit} className="space-y-6 max-w-lg">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className={label}>Schedule Time (HH:MM)</label>
          <input
            className={field}
            value={form.schedule_time}
            onChange={(e) => set("schedule_time", e.target.value)}
            pattern="\d{2}:\d{2}"
            placeholder="06:00"
          />
        </div>
        <div>
          <label className={label}>Timezone</label>
          <input
            className={field}
            value={form.timezone}
            onChange={(e) => set("timezone", e.target.value)}
            placeholder="Europe/Brussels"
          />
        </div>
      </div>

      <div>
        <label className={label}>Standaard video modus</label>
        <select
          className={field}
          value={(form as any).video_mode ?? "short"}
          onChange={(e) => set("video_mode" as any, e.target.value)}
        >
          <option value="short">Short / Reel (60 sec · 9:16)</option>
          <option value="long">YouTube Long (8-15 min · 16:9)</option>
        </select>
      </div>

      <div>
        <label className={label}>Topic Source</label>
        <select
          className={field}
          value={form.topic_source}
          onChange={(e) => set("topic_source", e.target.value)}
        >
          <option value="youtube">YouTube Data API (recommended)</option>
          <option value="vidiq">VidIQ Scraper</option>
        </select>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className={label}>YouTube Category ID</label>
          <input
            className={field}
            value={form.youtube_category_id}
            onChange={(e) => set("youtube_category_id", e.target.value)}
            placeholder="28 = Science & Tech"
          />
        </div>
        <div>
          <label className={label}>Script Language</label>
          <input
            className={field}
            value={form.script_language}
            onChange={(e) => set("script_language", e.target.value)}
            placeholder="en"
          />
        </div>
      </div>

      <div>
        <label className={label}>Alert Email</label>
        <input
          className={field}
          type="email"
          value={form.alert_email}
          onChange={(e) => set("alert_email", e.target.value)}
          placeholder="you@example.com"
        />
      </div>

      <div>
        <label className={label}>Webhook URL (Slack / Discord / n8n)</label>
        <input
          className={field}
          value={form.alert_webhook_url}
          onChange={(e) => set("alert_webhook_url", e.target.value)}
          placeholder="https://hooks.slack.com/..."
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className={label}>Output cleanup after (days)</label>
          <input
            className={field}
            type="number"
            min={1}
            value={form.cleanup_days}
            onChange={(e) => set("cleanup_days", Number(e.target.value))}
          />
        </div>
        <div>
          <label className={label}>Max history entries</label>
          <input
            className={field}
            type="number"
            min={10}
            value={form.history_max_entries}
            onChange={(e) => set("history_max_entries", Number(e.target.value))}
          />
        </div>
      </div>

      <div className="flex items-center gap-4">
        <button
          type="submit"
          disabled={saving}
          className="px-4 py-2 rounded-lg bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium disabled:opacity-50 transition-colors"
        >
          {saving ? "Saving…" : "Save Settings"}
        </button>
        {msg && (
          <p className={`text-sm ${msg.ok ? "text-green-400" : "text-red-400"}`}>{msg.text}</p>
        )}
      </div>
    </form>
  );
}
