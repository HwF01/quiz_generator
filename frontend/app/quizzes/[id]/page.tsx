"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api, downloadAuth, getToken } from "@/lib/api";
import { formatOptionLabel } from "@/lib/options";
import { FavoriteButton } from "@/components/FavoriteButton";
import { QuestionEditDialog, type QuestionPatch } from "@/components/QuestionEditDialog";
import { ListSkeleton } from "@/components/ListSkeleton";
import { microSkillLabel, quizStatusLabel } from "@/lib/labels";

type Question = {
  id: string;
  type: string;
  content: string;
  options: { key: string; text: string }[] | null;
  answer: {
    keys?: string[];
    texts?: string[];
    subparts?: { id: string; texts?: string[]; expected_points?: string[] }[];
  };
  explanation?: string;
  distractor_rationale?: Record<string, string>;
  difficulty: string;
  micro_skill: string;
  source_span?: { quote?: string };
  subparts?: {
    id: string;
    prompt: string;
    rubric?: { max_score?: number; criteria?: { description: string; points: number }[] };
  }[] | null;
  external_sources?: { id: string; title: string; url: string; excerpt: string; used?: boolean }[] | null;
  quality_scores?: {
    usability?: number;
    accuracy?: number;
    answer_exists?: boolean;
    comment?: string;
    review_reasons?: string[];
  };
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

const REVIEW_REASON_LABELS: Record<string, string> = {
  distractors_insufficient: "干扰项不足",
  critic_error: "质量审校服务异常",
  adversarial_replacement_rejected: "替换干扰项未通过校验",
  invalid_choice_structure: "选项或正解结构不完整",
  answer_not_in_source: "正解缺乏原文依据",
  non_unique_correct: "存在多个可能正确选项",
  stem_leak: "题干泄露正解",
  low_usability: "可用性偏低",
  low_accuracy: "准确性不足",
  controversial: "题目可能有争议",
  guessable: "干扰项过易猜",
  invalid_distractor: "干扰项不确定错误或语义等价",
  invalid_grading_rubric: "评分量规不完整",
  rubric_critic_error: "评分量规生成异常",
  invalid_external_source: "外部来源引用无效",
  unsupported_question_type: "题型与学科标签不匹配",
  difficulty_mismatch: "目标难度不匹配",
};

function reviewReasonLabel(reason: string): string {
  return REVIEW_REASON_LABELS[reason] ?? "需要人工审校";
}

function questionTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    single_choice: "单选题",
    multi_choice: "多选题",
    true_false: "判断题",
    fill_blank: "填空题",
    application: "应用题",
    proof: "证明题",
    short_answer: "简答题",
  };
  return labels[type] || type;
}

function difficultyLabel(difficulty: string): string {
  const labels: Record<string, string> = { easy: "基础", medium: "进阶", hard: "挑战" };
  return labels[difficulty] || difficulty;
}

export default function QuizEditPage() {
  const { id } = useParams<{ id: string }>();
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [msg, setMsg] = useState("");
  const [editing, setEditing] = useState<Question | null>(null);
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState("");
  const [onlyNeedsReview, setOnlyNeedsReview] = useState(false);
  const [hardeningId, setHardeningId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState("");

  async function load() {
    const data = await api<Quiz>(`/quizzes/${id}?purpose=review`);
    setQuiz(data);
    setLoadError("");
  }

  useEffect(() => {
    load().catch((e) => setLoadError(e instanceof Error ? e.message : "加载失败"));
  }, [id]);

  const sorted = useMemo(() => {
    if (!quiz) return [];
    return [...quiz.questions].sort((a, b) => Number(b.needs_review) - Number(a.needs_review));
  }, [quiz]);
  const visibleQuestions = useMemo(
    () => (onlyNeedsReview ? sorted.filter((question) => question.needs_review) : sorted),
    [onlyNeedsReview, sorted]
  );
  const pendingCount = useMemo(
    () => quiz?.questions.filter((question) => question.needs_review).length ?? 0,
    [quiz]
  );

  async function saveMeta(patch: Partial<Quiz>) {
    await api(`/quizzes/${id}`, { method: "PATCH", body: JSON.stringify(patch) });
    load();
  }

  async function saveQuestion(q: Question, patch: Partial<Question>) {
    await api(`/quizzes/questions/${q.id}`, { method: "PATCH", body: JSON.stringify(patch) });
    load();
  }

  async function toggleReview(q: Question) {
    try {
      await saveQuestion(q, { needs_review: !q.needs_review });
      setMsg(q.needs_review ? "已标记为已审" : "已标记待审");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "更新审校状态失败");
    }
  }

  async function hardenQuestion(q: Question) {
    setHardeningId(q.id);
    try {
      await api(`/quizzes/questions/${q.id}/harden`, { method: "POST" });
      setMsg("已重新生成干扰项，请核对审校结果");
      await load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "重新生成干扰项失败");
    } finally {
      setHardeningId(null);
    }
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

  if (!quiz) {
    if (loadError) {
      return (
        <div className="card space-y-3 p-4 sm:p-6">
          <p className="text-sm text-red-600">{loadError}</p>
          <Link className="btn-ghost" href="/profile">
            返回我的题库
          </Link>
        </div>
      );
    }
    return <ListSkeleton columns={false} cards={3} label="正在加载题库" />;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold break-words">{quiz.title}</h1>
          <p className="text-sm text-slate-500">
            {quiz.category} · {quiz.subject} · {quizStatusLabel(quiz.status)}
          </p>
          <p className="mt-1 text-sm text-amber-700">待审校 {pendingCount} / {quiz.questions.length} 题</p>
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
      <div className="flex items-center gap-2">
        <button
          type="button"
          className="btn-ghost"
          aria-pressed={onlyNeedsReview}
          onClick={() => setOnlyNeedsReview((current) => !current)}
        >
          {onlyNeedsReview ? "查看全部题目" : "仅看待审校"}
        </button>
      </div>
      <div className="space-y-4">
        {visibleQuestions.map((q, idx) => (
          <article key={q.id} className={`card p-5 ${q.needs_review ? "border-amber-400" : ""}`}>
            <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
              <span className="badge">第 {idx + 1} 题</span>
              <span className="badge">{questionTypeLabel(q.type)}</span>
              <span className="badge">{microSkillLabel(q.micro_skill)}</span>
              <span className="badge">{difficultyLabel(q.difficulty)}</span>
              {q.needs_review && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-amber-800">待审校</span>}
              {q.quality_scores?.usability != null && <span className="badge">可用性 {q.quality_scores.usability}/5</span>}
              {q.quality_scores?.accuracy != null && <span className="badge">准确性 {q.quality_scores.accuracy}/5</span>}
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
            {!q.options && q.type === "single_choice" && (
              <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
                此题尚无可用选项。请手动补全 3 个确定错误的干扰项，或重新生成干扰项。
              </p>
            )}
            {q.needs_review && (q.quality_scores?.review_reasons?.length || q.quality_scores?.comment) && (
              <div className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
                <p className="font-medium">审校原因</p>
                {q.quality_scores?.review_reasons?.length ? (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {q.quality_scores.review_reasons.map((reason) => (
                      <span key={reason} className="rounded-full bg-amber-100 px-2 py-0.5 text-xs">
                        {reviewReasonLabel(reason)}
                      </span>
                    ))}
                  </div>
                ) : null}
                {q.quality_scores?.comment && <p className="mt-2 text-slate-700">{q.quality_scores.comment}</p>}
              </div>
            )}
            {q.type === "fill_blank" && q.answer?.texts && q.answer.texts.length > 0 && (
              <p className="mt-3 text-sm text-green-700">正解：{q.answer.texts.join(" / ")}</p>
            )}
            {q.subparts?.map((part, partIndex) => {
              const answer = q.answer.subparts?.find((item) => item.id === part.id);
              return (
                <div key={part.id} className="mt-3 rounded-lg bg-slate-50 p-3 text-sm">
                  <p className="font-medium">
                    第 {partIndex + 1} 问：{part.prompt}
                  </p>
                  {answer?.texts?.length ? (
                    <p className="mt-1 text-emerald-700">可接受答案：{answer.texts.join(" / ")}</p>
                  ) : null}
                  {answer?.expected_points?.length ? (
                    <p className="mt-1 text-emerald-700">正解要点：{answer.expected_points.join("；")}</p>
                  ) : null}
                  {part.rubric?.criteria?.length ? (
                    <ul className="mt-2 list-inside list-disc text-slate-600">
                      {part.rubric.criteria.map((criterion) => (
                        <li key={`${part.id}-${criterion.description}`}>
                          {criterion.description}（{criterion.points} 分）
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              );
            })}
            {q.external_sources?.length ? (
              <section className="mt-3 rounded-lg bg-sky-50 p-3 text-sm text-slate-700">
                <p className="font-medium text-sky-900">外部参考来源</p>
                <ul className="mt-1 space-y-1">
                  {q.external_sources.map((source) => (
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
            {q.source_span?.quote && (
              <p className="mt-3 break-words rounded-lg bg-slate-50 p-2 text-xs text-slate-600">原文：{q.source_span.quote}</p>
            )}
            <p className="mt-2 break-words text-sm text-slate-600">解析：{q.explanation}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <button className="btn-ghost" onClick={() => openEdit(q)}>
                手动修改
              </button>
              {q.type === "single_choice" && (
                <button
                  className="btn-ghost"
                  disabled={hardeningId === q.id}
                  onClick={() => void hardenQuestion(q)}
                >
                  {hardeningId === q.id ? "生成中…" : "重新生成干扰项"}
                </button>
              )}
              <button className="btn-ghost" onClick={() => void toggleReview(q)}>
                {q.needs_review ? "标记已审" : "标记待审"}
              </button>
              <button
                className="btn-danger"
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
