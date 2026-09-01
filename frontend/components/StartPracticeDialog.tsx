"use client";

import { useEffect, useState } from "react";

export type PracticeMode = "sequential" | "random";

export function parsePracticeMode(value: string | null): PracticeMode | null {
  if (value === "sequential" || value === "random") return value;
  return null;
}

export function practiceHref(quizId: string, mode: PracticeMode): string {
  return `/practice/${quizId}?mode=${mode}`;
}

type Props = {
  open: boolean;
  onConfirm: (mode: PracticeMode) => void;
  onCancel: () => void;
};

const OPTIONS: { value: PracticeMode; label: string; hint: string }[] = [
  { value: "sequential", label: "顺序", hint: "按题库原有顺序作答" },
  { value: "random", label: "随机", hint: "打乱题目顺序后作答" },
];

export function StartPracticeDialog({ open, onConfirm, onCancel }: Props) {
  const [selected, setSelected] = useState<PracticeMode>("sequential");

  useEffect(() => {
    if (open) setSelected("sequential");
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onCancel();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/40 p-0 sm:items-center sm:p-4"
      onClick={onCancel}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="start-practice-title"
        className="card w-full max-w-md rounded-t-2xl p-5 sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="start-practice-title" className="text-lg font-semibold">
          选择刷题顺序
        </h2>
        <p className="mt-2 text-sm text-slate-600">进入练习后不能更改。</p>
        <div role="radiogroup" aria-labelledby="start-practice-title" className="mt-4 space-y-2">
          {OPTIONS.map((option) => {
            const checked = selected === option.value;
            return (
              <label
                key={option.value}
                className={`flex min-h-11 cursor-pointer items-start gap-2 rounded-xl border px-3 py-3 ${
                  checked ? "border-brand-600 bg-brand-50" : "border-slate-200"
                }`}
              >
                <input
                  className="mt-1 shrink-0"
                  type="radio"
                  name="start-practice-mode"
                  value={option.value}
                  checked={checked}
                  onChange={() => setSelected(option.value)}
                />
                <span className="min-w-0">
                  <span className="block text-sm font-medium text-slate-800">{option.label}</span>
                  <span className="block text-xs text-slate-500">{option.hint}</span>
                </span>
              </label>
            );
          })}
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" className="btn-ghost" onClick={onCancel}>
            取消
          </button>
          <button type="button" className="btn-primary" onClick={() => onConfirm(selected)}>
            开始刷题
          </button>
        </div>
      </div>
    </div>
  );
}
