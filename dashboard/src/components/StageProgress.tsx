"use client";

import { CheckCircle, Circle, Loader, XCircle } from "lucide-react";

const STAGES = [
  { key: "stage1_research", label: "Research" },
  { key: "stage2_voice", label: "Voice" },
  { key: "stage3_avatar", label: "Avatar" },
  { key: "stage4_pictory", label: "Pictory" },
  { key: "done", label: "Done" },
];

type Props = {
  currentStage: string | null;
  status: string;
  timings: Record<string, number>;
};

export default function StageProgress({ currentStage, status, timings }: Props) {
  const currentIdx = STAGES.findIndex((s) => s.key === currentStage);

  return (
    <div className="flex items-center gap-1 flex-wrap">
      {STAGES.map((stage, i) => {
        const isDone = currentIdx > i || (status === "completed" && stage.key === "done");
        const isCurrent = stage.key === currentStage && status === "running";
        const isFailed = status === "failed" && stage.key === currentStage;
        const timing = timings[stage.key];

        return (
          <div key={stage.key} className="flex items-center">
            <div className="flex flex-col items-center gap-1">
              <div
                className={`flex items-center gap-1 px-3 py-1.5 rounded-full text-xs font-medium border transition-all
                  ${isDone ? "bg-green-900/40 border-green-700 text-green-400" : ""}
                  ${isCurrent ? "bg-blue-900/40 border-blue-600 text-blue-300 animate-pulse" : ""}
                  ${isFailed ? "bg-red-900/40 border-red-700 text-red-400" : ""}
                  ${!isDone && !isCurrent && !isFailed ? "bg-gray-800 border-gray-700 text-gray-500" : ""}
                `}
              >
                {isDone && <CheckCircle className="w-3 h-3" />}
                {isCurrent && <Loader className="w-3 h-3 animate-spin" />}
                {isFailed && <XCircle className="w-3 h-3" />}
                {!isDone && !isCurrent && !isFailed && <Circle className="w-3 h-3" />}
                {stage.label}
              </div>
              {timing !== undefined && (
                <span className="text-[10px] text-gray-600">{timing}s</span>
              )}
            </div>
            {i < STAGES.length - 1 && (
              <div className={`h-px w-4 mx-1 ${isDone ? "bg-green-700" : "bg-gray-700"}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}
