"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api, downloadAuth, getToken } from "@/lib/api";
import { formatOptionLabel } from "@/lib/options";
import { FavoriteButton } from "@/components/FavoriteButton";
import { QuestionEditDialog, type QuestionPatch } from "@/components/QuestionEditDialog";

type Question = {
  id: string;
  type: string;
  content: string;
  options: { key: string; text: string }[] | null;
  answer: { keys?: string[]; texts?: string[] };
  explanation?: string;
  distractor_rationale?: Record<string, string>;
  difficulty: string;
  micro_skill: string;
  source_span?: { quote?: string };
  quality_scores?: { usability?: number; answer_exists?: boolean };
  needs_review: boolean;
  favorited?: boolean;
};

type Quiz = {
  id: string;
  title: string;
  status: string;
  visibility: string;
  category: string;
  subject: string;
  creator_id: string;
  is_builtin: boolean;
  questions: Question[];
  generation_job_id?: string;
};

export default function QuizEditPage() {
  const { id } = useParams<{ id: string }>();
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [msg, setMsg] = useState("");
  const [editing, setEditing] = useState<Question | null>(null);
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState("");

  async function load() {
    const data = await api<Quiz>(`/quizzes/${id}?purpose=review`);
    setQuiz(data);
  }

  useEffect(() => {
    load().catch((e) => setMsg(e.message));
  }, [id]);

  const sorted = useMemo(() => {
    if (!quiz) return [];
    return [...quiz.questions].sort((a, b) => Number(b.needs_review) - Number(a.needs_review));
  }, [quiz]);

  async function saveMeta(patch: Partial<Quiz>) {
    await api(`/quizzes/${id}`, { method: "PATCH", body: JSON.stringify(patch) });
    load();
  }

  async function saveQuestion(q: Question, patch: Partial<Question>) {
    await api(`/quizzes/questions/${q.id}`, { method: "PATCH", body: JSON.stringify(patch) });
    load();
  }

  function openEdit(q: Question) {
    setEditError("");
    setEditing(q);
  }

  async function saveEdit(patch: QuestionPatch) {
    if (!editing) return;
    setSaving(true);
    setEditError("");
    try {
      await api(`/quizzes/questions/${editing.id}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      });
      setEditing(null);
      setMsg("已保存修改");
      await load();
    } catch (e) {
      setEditError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function toggleFav(q: Question) {
    try {
      const data = await api<{ favorited: boolean }>(`/quizzes/questions/${q.id}/favorite`, {
        method: "POST",
      });
      setQuiz((prev) =>
        prev
          ? {
              ...prev,
              questions: prev.questions.map((item) =>
                item.id === q.id ? { ...item, favorited: data.favorited } : item
              ),
            }
          : prev
      );
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "收藏失败");
    }
  }

  if (!quiz) return <p>{msg || "加载中…"}</p>;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold break-words">{quiz.title}</h1>
          <p className="text-sm text-slate-500">
            {quiz.category} · {quiz.subject} · {quiz.status}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link className="btn-primary" href={`/practice/${quiz.id}`}>
            开始刷题
          </Link>
          <button
            className="btn-ghost"
            onClick={() => downloadAuth(`/export/${quiz.id}.xlsx`, `${quiz.title}.xlsx`)}
          >
            导出 Excel
          </button>
          <button
            className="btn-ghost"
            onClick={() => downloadAuth(`/export/${quiz.id}.json`, `${quiz.title}.json`)}
          >
            导出 JSON
          </button>
          {getToken() && (
            <button
              className="btn-ghost"
              onClick={() => saveMeta({ visibility: quiz.visibility === "public" ? "private" : "public" })}
            >
              {quiz.visibility === "public" ? "设为私密" : "公开到广场"}
            </button>
          )}
        </div>
      </div>
      {msg && <p className="text-sm text-brand-700">{msg}</p>}
      <div className="space-y-4">
        {sorted.map((q, idx) => (
          <article key={q.id} className={`card p-5 ${q.needs_review ? "border-amber-400" : ""}`}>
            <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
              <span className="badge">第 {idx + 1} 题</span>
              <span className="badge">{q.type}</span>
              <span className="badge">{q.micro_skill}</span>
              <span className="badge">{q.difficulty}</span>
              {q.needs_review && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-amber-800">待审校</span>}
              {q.quality_scores?.usability && <span className="badge">可用性 {q.quality_scores.usability}/5</span>}
              <FavoriteButton
                className="ml-auto"
                favorited={Boolean(q.favorited)}
                onToggle={() => void toggleFav(q)}
              />
            </div>
            <p className="whitespace-pre-wrap break-words text-sm leading-6">{q.content}</p>
            {q.options && (
              <ul className="mt-3 space-y-1 text-sm">
                {q.options.map((o) => (
                  <li key={o.key} className="break-words">
                    {q.type === "true_false" ? (
                      <strong className="mr-2">{formatOptionLabel(o, q.type, q.options)}</strong>
                    ) : (
                      <>
                        <strong className="mr-2">{o.key}.</strong>
                        {o.text}
                      </>
                    )}
                    {q.answer?.keys?.includes(o.key) && <span className="ml-2 text-green-700">正解</span>}
                    {q.distractor_rationale?.[o.key] && (
                      <span className="ml-2 text-slate-400">（{q.distractor_rationale[o.key]}）</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {q.type === "fill_blank" && q.answer?.texts && q.answer.texts.length > 0 && (
              <p className="mt-3 text-sm text-green-700">正解：{q.answer.texts.join(" / ")}</p>
            )}
            {q.source_span?.quote && (
              <p className="mt-3 break-words rounded-lg bg-slate-50 p-2 text-xs text-slate-600">原文：{q.source_span.quote}</p>
            )}
            <p className="mt-2 break-words text-sm text-slate-600">解析：{q.explanation}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <button className="btn-ghost" onClick={() => openEdit(q)}>
                手动修改
              </button>
              <button className="btn-ghost" onClick={() => saveQuestion(q, { needs_review: !q.needs_review })}>
                {q.needs_review ? "标记已审" : "标记待审"}
              </button>
              <button
                className="btn-ghost text-red-600"
                onClick={async () => {
                  await api(`/quizzes/questions/${q.id}`, { method: "DELETE" });
                  load();
                }}
              >
                删除
              </button>
            </div>
          </article>
        ))}
      </div>
      {editing && (
        <QuestionEditDialog
          question={editing}
          busy={saving}
          error={editError}
          onClose={() => {
            if (!saving) setEditing(null);
          }}
          onSave={(patch) => void saveEdit(patch)}
        />
      )}
    </div>
  );
}
