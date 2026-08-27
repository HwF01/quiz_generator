"use client";

import type { QuizStub } from "@/lib/quiz-groups";

type Props = {
  quizzes: QuizStub[];
  activeId: string | null;
  onSelect: (id: string | null) => void;
};

/** Pill filter tabs: hover fill + selected tint, no font-weight jump. */
export function QuizFilterTabs({ quizzes, activeId, onSelect }: Props) {
  if (quizzes.length <= 1) return null;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        className="quiz-filter-tab"
        data-active={activeId === null ? "true" : "false"}
        aria-pressed={activeId === null}
        onClick={() => onSelect(null)}
      >
        全部
      </button>
      {quizzes.map((q) => (
        <button
          key={q.id}
          type="button"
          className="quiz-filter-tab"
          data-active={activeId === q.id ? "true" : "false"}
          aria-pressed={activeId === q.id}
          onClick={() => onSelect(q.id)}
        >
          {q.title}
        </button>
      ))}
    </div>
  );
}
