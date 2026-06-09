"use client";

import { ExternalLink } from "lucide-react";
import type { RunRecord } from "@/lib/api";
import { format } from "date-fns";

type Props = { items: RunRecord[] };

const STATUS_BADGE: Record<string, string> = {
  completed: "bg-green-900/50 text-green-400 border-green-800",
  failed: "bg-red-900/50 text-red-400 border-red-800",
  running: "bg-blue-900/50 text-blue-400 border-blue-800",
};

function duration(run: RunRecord): string {
  if (!run.finished_at) return "—";
  const secs = Math.round(
    (new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()) / 1000
  );
  if (secs < 60) return `${secs}s`;
  return `${Math.floor(secs / 60)}m ${secs % 60}s`;
}

export default function RunTable({ items }: Props) {
  if (items.length === 0) {
    return <p className="text-gray-500 text-sm">No runs recorded yet.</p>;
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-800">
      <table className="w-full text-sm">
        <thead className="bg-gray-900 text-gray-400 text-xs uppercase tracking-wider">
          <tr>
            <th className="px-4 py-3 text-left">Date</th>
            <th className="px-4 py-3 text-left">Topic</th>
            <th className="px-4 py-3 text-left">Duration</th>
            <th className="px-4 py-3 text-left">Status</th>
            <th className="px-4 py-3 text-left">Draft</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800">
          {items.map((run) => (
            <tr key={run.run_id} className="bg-gray-950 hover:bg-gray-900 transition-colors">
              <td className="px-4 py-3 text-gray-400 whitespace-nowrap">
                {format(new Date(run.started_at), "dd MMM yyyy HH:mm")}
              </td>
              <td className="px-4 py-3 text-gray-200 max-w-xs truncate">
                {run.topic ?? "—"}
              </td>
              <td className="px-4 py-3 text-gray-400 whitespace-nowrap">{duration(run)}</td>
              <td className="px-4 py-3">
                <span
                  className={`px-2 py-0.5 rounded-full border text-xs font-medium capitalize ${
                    STATUS_BADGE[run.status] ?? "bg-gray-800 text-gray-400 border-gray-700"
                  }`}
                >
                  {run.status}
                </span>
              </td>
              <td className="px-4 py-3">
                {run.pictory_draft_url ? (
                  <a
                    href={run.pictory_draft_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-brand-500 hover:text-brand-400"
                  >
                    <ExternalLink className="w-3 h-3" />
                    Open
                  </a>
                ) : (
                  <span className="text-gray-600">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
