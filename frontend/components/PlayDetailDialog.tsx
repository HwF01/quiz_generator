"use client";

import { useEffect } from "react";
import { formatOptionLabel } from "@/lib/options";

export type PlayDetailItem = {
  question_id: string;
  missing: boolean;
  content: string;
  type: string | null;
  options: { key: string; text: string }[] | null;
  user_answer: unknown;
  answer: {
    keys?: string[];
    texts?: string[];
    subparts?: { id: string; texts?: string[]; expected_points?: string[] }[];
  } | null;
  correct: boolean | null;
  explanation?: string | null;
  micro_skill?: string | null;
  subparts?: {
    id: string;
    prompt: string;
    rubric?: { max_score?: number; criteria?: { description: string; points: number }[] };
  }[] | null;
  external_sources?: { id: string; title: string; url: string; excerpt: string; used?: boolean }[] | null;
  ai_grade?: {
    status: "pending" | "graded" | "needs_review";
    score?: number;
    max_score?: number;
    percent?: number;
    exact_match?: boolean | null;
    subparts?: { id: string; score: number; max_score: number; evidence: string; feedback: string }[];
    overall_feedback?: string;
  } | null;
};

export type PlayDetail = {
  id: string;
  quiz_id: string;
  title: string;
  score: number;
  time_spent: number;
  mode: string;
  created_at: string | null;
  correct: number;
  total: number;
  graded_total?: number;
  pending_ai_grading?: number;
  details: PlayDetailItem[];
};

type Props = {
  detail: PlayDetail;
  onClose: () => void;
};

function typeLabel(type: string | null): string {
  if (type === "single_choice") return "单选";
  if (type === "multi_choice") return "多选";
  if (type === "true_false") return "判断";
  if (type === "fill_blank") return "填空";
  if (type === "application") return "应用";
  if (type === "proof") return "证明";
  if (type === "short_answer") return "简答";
  return type || "未知题型";
}

function pickedKeys(userAnswer: unknown): string[] {
  if (userAnswer == null || userAnswer === "") return [];
  return Array.isArray(userAnswer) ? userAnswer.map(String) : [String(userAnswer)];
}

function formatAnswerText(
  type: string | null,
  options: { key: string; text: string }[] | null,
  value: unknown,
): string {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const values = Object.values(value).filter((item): item is string => typeof item === "string");
    return values.length > 0 ? values.join(" / ") : "未作答";
  }
  const keys = pickedKeys(value);
  if (keys.length === 0) return "未作答";
  if (type === "fill_blank") return keys.join(" / ");
  if (options && options.length > 0) {
    return keys
      .map((k) => {
        const option = options.find((o) => o.key === k);
        return option ? formatOptionLabel(option, type ?? undefined, options) : k;
      })
      .join("、");
  }
  return keys.join("、");
}

function isConstructed(type: string | null): boolean {
  return ["fill_blank", "application", "proof", "short_answer"].includes(type || "");
}

export function PlayDetailCards({
  details,
  onGrade,
  gradingQuestionId,
}: {
  details: PlayDetailItem[];
  onGrade?: (questionId: string) => void;
  gradingQuestionId?: string | null;
}) {
  if (details.length === 0) {
    return <p className="text-sm text-slate-500">没有可展示的题目（题目可能已删除）。</p>;
  }
  return (
    <div className="space-y-3">
      {details.map((item, idx) => {
        const grade = item.ai_grade;
        const pending = grade?.status === "pending";
        const needsReview = grade?.status === "needs_review";
        return (
          <article
            key={item.question_id}
            className={`rounded-xl border p-4 ${
              item.missing || item.correct === null
                ? "border-slate-200 bg-slate-50"
                : item.correct
                  ? "border-emerald-200 bg-emerald-50/40"
                  : "border-rose-200 bg-rose-50/40"
            }`}
          >
          <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
            <span className="badge">第 {idx + 1} 题</span>
            <span className="badge">{typeLabel(item.type)}</span>
            {item.micro_skill && <span className="badge">{item.micro_skill}</span>}
            <span
              className={`rounded-full px-2 py-0.5 ${
                item.missing
                  ? "bg-slate-200 text-slate-600"
                  : item.correct === null
                    ? "bg-slate-200 text-slate-600"
                  : item.correct
                    ? "bg-emerald-100 text-emerald-800"
                    : "bg-rose-100 text-rose-800"
              }`}
            >
              {item.missing ? "题目缺失" : pending ? "待 AI 批改" : needsReview ? "待人工复核" : item.correct ? "正确" : "错误"}
            </span>
          </div>
          <p className="whitespace-pre-wrap break-words text-sm leading-6">{item.content}</p>
          {isConstructed(item.type) && item.subparts?.length ? (
            <div className="mt-3 space-y-3 text-sm">
              {item.subparts?.map((part, partIndex) => {
                const answer = item.answer?.subparts?.find((entry) => entry.id === part.id);
                const score = grade?.subparts?.find((entry) => entry.id === part.id);
                return (
                  <div key={part.id} className="rounded-lg bg-white/70 p-3">
                    <p className="font-medium">第 {partIndex + 1} 问：{part.prompt}</p>
                    <p className="mt-1">
                      <span className="text-slate-500">你的答案：</span>
                      {typeof item.user_answer === "object" && item.user_answer && !Array.isArray(item.user_answer)
                        ? String((item.user_answer as Record<string, unknown>)[part.id] || "未作答")
                        : formatAnswerText(item.type, item.options, item.user_answer)}
                    </p>
                    {answer?.texts?.length ? <p className="text-emerald-700">可接受答案：{answer.texts.join(" / ")}</p> : null}
                    {answer?.expected_points?.length ? <p className="text-emerald-700">正解要点：{answer.expected_points.join("；")}</p> : null}
                    {part.rubric?.criteria?.length ? (
                      <ul className="mt-1 list-inside list-disc text-slate-600">
                        {part.rubric.criteria.map((criterion) => (
                          <li key={`${part.id}-${criterion.description}`}>
                            {criterion.description}（{criterion.points} 分）
                          </li>
                        ))}
                      </ul>
                    ) : null}
                    {score ? (
                      <p className="mt-1 text-brand-700">
                        得分 {score.score}/{score.max_score} · {score.evidence}
                        {score.feedback ? ` ${score.feedback}` : ""}
                      </p>
                    ) : null}
                  </div>
                );
              })}
              {grade?.status === "graded" ? (
                <p className="font-medium text-brand-700">
                  AI 辅助评分：{grade.score}/{grade.max_score}（{grade.percent}%）
                  {grade.overall_feedback ? ` · ${grade.overall_feedback}` : ""}
                </p>
              ) : null}
              {item.type === "fill_blank" && typeof grade?.exact_match === "boolean" ? (
                <p className={grade.exact_match ? "text-emerald-700" : "text-amber-700"}>
                  {grade.exact_match ? "已匹配到可接受答案。" : "未完全匹配可接受答案，可继续请求 AI 批改。"}
                </p>
              ) : null}
              {(pending || needsReview) && onGrade ? (
                <button
                  type="button"
                  className="btn-primary"
                  disabled={gradingQuestionId === item.question_id}
                  onClick={() => onGrade(item.question_id)}
                >
                  {gradingQuestionId === item.question_id ? "AI 批改中…" : "AI 批改"}
                </button>
              ) : null}
              <p className="text-xs text-slate-500">AI 批改仅作练习参考，可结合量规自行复核。</p>
            </div>
          ) : item.type === "fill_blank" ? (
            <div className="mt-3 space-y-1 text-sm">
              <p>
                <span className="text-slate-500">你的答案：</span>
                {formatAnswerText(item.type, item.options, item.user_answer)}
              </p>
              <p className="text-emerald-700">正解：{(item.answer?.texts || []).join(" / ") || "—"}</p>
            </div>
          ) : (
            <ul className="mt-3 space-y-1.5">
              {(item.options || []).map((o) => {
                const userPicked = pickedKeys(item.user_answer).includes(o.key);
                const isAnswer = Boolean(item.answer?.keys?.includes(o.key));
                return (
                  <li
                    key={o.key}
                    className={`rounded-lg border px-3 py-2 text-sm break-words ${
                      isAnswer
                        ? "border-emerald-300 bg-emerald-50"
                        : userPicked
                          ? "border-rose-300 bg-rose-50"
                          : "border-slate-200 bg-white"
                    }`}
                  >
                    {formatOptionLabel(o, item.type ?? undefined, item.options)}
                    {isAnswer && <span className="ml-2 text-emerald-700">正解</span>}
                    {userPicked && !isAnswer && <span className="ml-2 text-rose-700">你的选择</span>}
                    {userPicked && isAnswer && <span className="ml-2 text-emerald-700">你的选择</span>}
                  </li>
                );
              })}
            </ul>
          )}
          {!item.missing && (item.options || []).length === 0 && !isConstructed(item.type) && (
            <p className="mt-3 text-sm text-slate-600">
              你的答案：{formatAnswerText(item.type, item.options, item.user_answer)}
            </p>
          )}
          {item.explanation && (
            <p className="mt-3 break-words text-sm text-slate-600">解析：{item.explanation}</p>
          )}
          {item.external_sources?.length ? (
            <section className="mt-3 rounded-lg bg-sky-50 p-3 text-sm">
              <p className="font-medium text-sky-900">外部参考来源</p>
              <ul className="mt-1 space-y-1">
                {item.external_sources.map((source) => (
                  <li key={source.id}>
                    <a className="text-brand-700 underline" href={source.url} target="_blank" rel="noreferrer">
                      {source.title}
                    </a>
                    {source.used ? "（已用于本题）" : ""}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
          </article>
        );
      })}
    </div>
  );
}

export function PlayDetailDialog({ detail, onClose }: Props) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/40 p-0 sm:items-center sm:p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="play-detail-title"
        className="card flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-t-2xl sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="border-b border-slate-100 px-5 py-4">
          <h2 id="play-detail-title" className="text-lg font-semibold break-words">
            {detail.title || "刷题详情"}
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            {detail.score} 分 · 答对 {detail.correct}/{detail.total}
          </p>
        </div>
        <div className="overflow-y-auto px-5 py-4">
          <PlayDetailCards details={detail.details} />
        </div>
        <div className="flex justify-end border-t border-slate-100 px-5 py-3">
          <button type="button" className="btn-ghost" onClick={onClose}>
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}
