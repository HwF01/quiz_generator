"use client";

import type { QuizStub } from "@/lib/quiz-groups";

type Props = {
  quizzes: QuizStub[];
  activeId: string | null;
  onSelect: (id: string | null) => void;
};

const tabBase =
  "min-h-8 border-b-2 border-transparent px-1 pb-1 text-sm text-slate-600 transition hover:text-slate-900";
const tabActive = "border-brand-600 font-medium text-brand-700";

/** Text tabs (not badges): active state is underline. */
export function QuizFilterTabs({ quizzes, activeId, onSelect }: Props) {
  if (quizzes.length <= 1) return null;

  return (
    <div className="flex flex-wrap items-end gap-x-4 gap-y-2">
      <button
        type="button"
        className={`${tabBase} ${activeId === null ? tabActive : ""}`}
        onClick={() => onSelect(null)}
      >
        全部
      </button>
      {quizzes.map((q) => (
        <button
          key={q.id}
          type="button"
          className={`${tabBase} ${activeId === q.id ? tabActive : ""}`}
          onClick={() => onSelect(q.id)}
        >
          {q.title}
        </button>
      ))}
    </div>
  );
}
