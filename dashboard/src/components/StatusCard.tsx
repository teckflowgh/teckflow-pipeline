"use client";

import { ExternalLink } from "lucide-react";
import type { RunRecord } from "@/lib/api";
import StageProgress from "./StageProgress";
import { formatDistanceToNow } from "date-fns";

type Props = { run: RunRecord | null };

export default function StatusCard({ run }: Props) {
  if (!run) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 text-gray-500 text-sm">
        No pipeline runs yet. Click <strong className="text-white">Run Now</strong> to start.
      </div>
    );
  }

  const statusColor =
    run.status === "completed"
      ? "text-green-400"
      : run.status === "failed"
      ? "text-red-400"
      : "text-blue-400";

  const startedAgo = formatDistanceToNow(new Date(run.started_at), { addSuffix: true });

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs text-gray-500 mb-1">Latest run · {startedAgo}</p>
          <h2 className="text-lg font-semibold text-white">
            {run.topic ?? "Fetching topic…"}
          </h2>
          {run.script_preview && (
            <p className="text-sm text-gray-400 mt-1 line-clamp-2">{run.script_preview}</p>
          )}
        </div>
        <span className={`text-sm font-medium capitalize ${statusColor}`}>{run.status}</span>
      </div>

      <StageProgress
        currentStage={run.current_stage}
        status={run.status}
        timings={run.stage_timings}
      />

      {run.pictory_draft_url && (
        <a
          href={run.pictory_draft_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 text-sm text-brand-500 hover:text-brand-400 transition-colors"
        >
          <ExternalLink className="w-3.5 h-3.5" />
          Open Pictory Draft
        </a>
      )}

      {run.status === "failed" && run.error && (
        <details className="text-xs text-red-400 bg-red-950/30 rounded-lg p-3">
          <summary className="cursor-pointer font-medium">Error details</summary>
          <pre className="mt-2 whitespace-pre-wrap break-all">{run.error}</pre>
        </details>
      )}
    </div>
  );
}
