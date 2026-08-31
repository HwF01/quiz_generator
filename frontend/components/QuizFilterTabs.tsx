"use client";

import type { QuizStub } from "@/lib/quiz-groups";

export type FilterTab = { id: string; label: string };

type Props = {
  quizzes: QuizStub[];
  activeId: string | null;
  onSelect: (id: string | null) => void;
  extraTabs?: FilterTab[];
};

/** Pill filter tabs: hover fill + selected tint, no font-weight jump. */
export function QuizFilterTabs({ quizzes, activeId, onSelect, extraTabs = [] }: Props) {
  if (quizzes.length <= 1 && extraTabs.length === 0) return null;

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
      {quizzes.length > 1
        ? quizzes.map((q) => (
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
          ))
        : null}
      {extraTabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          className="quiz-filter-tab"
          data-active={activeId === tab.id ? "true" : "false"}
          aria-pressed={activeId === tab.id}
          onClick={() => onSelect(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
