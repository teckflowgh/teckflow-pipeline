"use client";

import { useCallback, useEffect, useState } from "react";
import { Play, RefreshCw, Zap, Youtube } from "lucide-react";
import StatusCard from "@/components/StatusCard";
import { fetchStatus, triggerRun, fetchLogs, type RunRecord } from "@/lib/api";

type VideoMode = "short" | "long";

export default function DashboardPage() {
  const [run, setRun] = useState<RunRecord | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [triggering, setTriggering] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedMode, setSelectedMode] = useState<VideoMode>("short");

  const refresh = useCallback(async () => {
    const [status, logLines] = await Promise.all([fetchStatus(), fetchLogs(50)]);
    setRun(status);
    setLogs(logLines);
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, [refresh]);

  async function handleRunNow() {
    setTriggering(true);
    setError(null);
    try {
      await triggerRun(selectedMode);
      await refresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setTriggering(false);
    }
  }

  const isRunning = run?.status === "running";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Pipeline Dashboard</h1>
          <p className="text-sm text-gray-500 mt-0.5">Auto-refreshes elke 5 seconden</p>
        </div>
        <button
          onClick={refresh}
          className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 transition-colors"
          title="Vernieuwen"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {/* Modus selector */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
          Video modus
        </p>
        <div className="flex gap-3">
          <button
            onClick={() => setSelectedMode("short")}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-lg border text-sm font-medium transition-all ${
              selectedMode === "short"
                ? "bg-brand-600 border-brand-500 text-white"
                : "bg-gray-800 border-gray-700 text-gray-400 hover:text-white"
            }`}
          >
            <Zap className="w-4 h-4" />
            Short / Reel
            <span className="text-xs opacity-70">60 sec · 9:16</span>
          </button>
          <button
            onClick={() => setSelectedMode("long")}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-lg border text-sm font-medium transition-all ${
              selectedMode === "long"
                ? "bg-brand-600 border-brand-500 text-white"
                : "bg-gray-800 border-gray-700 text-gray-400 hover:text-white"
            }`}
          >
            <Youtube className="w-4 h-4" />
            YouTube Long
            <span className="text-xs opacity-70">8-15 min · 16:9</span>
          </button>
        </div>

        <div className="mt-3 flex justify-end">
          <button
            onClick={handleRunNow}
            disabled={triggering || isRunning}
            className="flex items-center gap-2 px-5 py-2 rounded-lg bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium disabled:opacity-50 transition-colors"
          >
            <Play className="w-4 h-4" />
            {isRunning ? "Bezig..." : `Run Now (${selectedMode})`}
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-950/40 border border-red-800 rounded-lg px-4 py-2 text-sm text-red-400">
          {error}
        </div>
      )}

      <StatusCard run={run} />

      {logs.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
            Recente logs
          </h2>
          <pre className="text-xs text-gray-400 overflow-x-auto max-h-48 leading-5">
            {logs.join("\n")}
          </pre>
        </div>
      )}
    </div>
  );
}
