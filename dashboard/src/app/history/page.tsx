"use client";

import { useEffect, useState } from "react";
import RunTable from "@/components/RunTable";
import { fetchHistory, type RunRecord } from "@/lib/api";

export default function HistoryPage() {
  const [items, setItems] = useState<RunRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetchHistory(page, 20)
      .then((data) => {
        setItems(data.items);
        setTotal(data.total);
      })
      .finally(() => setLoading(false));
  }, [page]);

  const totalPages = Math.ceil(total / 20);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Run History</h1>
        <p className="text-sm text-gray-500 mt-0.5">{total} total runs</p>
      </div>

      {loading ? (
        <p className="text-gray-500 text-sm">Loading…</p>
      ) : (
        <RunTable items={items} />
      )}

      {totalPages > 1 && (
        <div className="flex items-center gap-3 text-sm">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-3 py-1.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 disabled:opacity-40"
          >
            Previous
          </button>
          <span className="text-gray-500">
            Page {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="px-3 py-1.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
