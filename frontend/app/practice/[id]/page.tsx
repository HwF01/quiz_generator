"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import { formatOptionLabel } from "@/lib/options";
import Link from "next/link";
import { Star } from "lucide-react";
import { FavoriteButton } from "@/components/FavoriteButton";
import { PlayDetailCards, type PlayDetail } from "@/components/PlayDetailDialog";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ErrorDialog } from "@/components/ErrorDialog";
import { CardSkeleton } from "@/components/ListSkeleton";
import { microSkillLabel } from "@/lib/labels";

type Question = {
  id: string;
  type: string;
  content: string;
  options: { key: string; text: string }[] | null;
  micro_skill: string;
  subparts?: { id: string; prompt: string }[] | null;
  favorited?: boolean;
};

type Quiz = {
  id: string;
  title: string;
  creator_id?: string;
  is_builtin?: boolean;
  visibility?: string;
  is_public?: boolean;
  questions: Question[];
};

type Result = {
  record_id?: string;
  score: number;
  correct: number;
  total: number;
  graded_total?: number;
  pending_ai_grading?: number;
  details: { question_id: string; correct: boolean | null; answer: unknown; explanation?: string }[];
  weak_skills: string[];
  mastery: Record<string, number>;
};

type AnswerValue = string | string[] | Record<string, string>;

function shuffle<T>(items: T[]): T[] {
  const copy = [...items];
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

function isConstructedQuestion(question: Question): boolean {
  return ["fill_blank", "application", "proof", "short_answer"].includes(question.type)
    && Boolean(question.subparts?.length);
}

function isQuestionAnswered(question: Question, value: AnswerValue | undefined): boolean {
  if (value === undefined) return false;
  if (isConstructedQuestion(question)) {
    if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
    return (question.subparts ?? []).every((part) => Boolean(value[part.id]?.trim()));
  }
  if (typeof value === "string") return value.trim().length > 0;
  if (Array.isArray(value)) return value.length > 0;
  return false;
}

function unansweredIndexes(questions: Question[], answers: Record<string, AnswerValue>): number[] {
  return questions.flatMap((question, index) =>
    isQuestionAnswered(question, answers[question.id]) ? [] : [index],
  );
}

function unansweredSubmitDescription(indexes: number[]): string {
  const labels = indexes.map((index) => String(index + 1)).join("、");
  const head =
    indexes.length === 1
      ? `第 ${labels} 题尚未作答。`
      : `还有 ${indexes.length} 道题未作答：第 ${labels} 题。`;
  return `${head}未作答将按错计。确定交卷吗？`;
}

export default function PracticePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const originalRef = useRef<Question[]>([]);
  const [idx, setIdx] = useState(0);
  const [answers, setAnswers] = useState<Record<string, AnswerValue>>({});
  const [seconds, setSeconds] = useState(0);
  const [result, setResult] = useState<Result | null>(null);
  const [playDetail, setPlayDetail] = useState<PlayDetail | null>(null);
  const [rating, setRating] = useState(0);
  const [rateBusy, setRateBusy] = useState(false);
  const [rateMsg, setRateMsg] = useState("");
  const [mode, setMode] = useState<"sequential" | "random">("sequential");
  const [qFilter, setQFilter] = useState<string | null>(null);
  const [meId, setMeId] = useState<string | null>(null);
  const [msg, setMsg] = useState("");
  const [pendingDelete, setPendingDelete] = useState(false);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [pendingUnanswered, setPendingUnanswered] = useState<number[] | null>(null);
  const [submitBusy, setSubmitBusy] = useState(false);
  const [gradingQuestionId, setGradingQuestionId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    if (!getToken()) router.push("/login");
    const search = typeof window !== "undefined" ? window.location.search : "";
    const params = new URLSearchParams(search);
    const filter = params.get("q") || params.get("question") || params.get("question_id");
    setQFilter(filter);
    Promise.all([
      api<Quiz>(`/quizzes/${id}?purpose=practice`),
      api<{ id: string }>("/auth/me").catch(() => null),
    ]).then(([raw, me]) => {
      const questions = filter ? raw.questions.filter((x) => x.id === filter) : raw.questions;
      originalRef.current = questions;
      setMeId(me?.id ?? null);
      setQuiz({ ...raw, questions });
      setIdx(0);
    }).catch((e) => {
      setLoadError(e instanceof Error ? e.message : "加载失败");
    });
    // 只依赖 id：切顺序/随机只 shuffle 本地副本，不重拉。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    if (result) return;
    const t = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [result]);

  function applyMode(next: "sequential" | "random") {
    setMode(next);
    setIdx(0);
    const base = originalRef.current;
    setQuiz((q) => (q ? { ...q, questions: next === "random" ? shuffle(base) : [...base] } : q));
  }

  const q = quiz?.questions[idx];
  const progress = quiz ? `${idx + 1}/${quiz.questions.length}` : "";
  const canDelete = Boolean(quiz?.creator_id && meId && quiz.creator_id === meId && !quiz.is_builtin);

  function isChecked(qid: string, key: string) {
    const v = answers[qid];
    return Array.isArray(v) ? v.includes(key) : typeof v === "string" && v === key;
  }

  function pickSingle(qid: string, key: string) {
    setAnswers((current) => ({ ...current, [qid]: key }));
  }

  function toggleMulti(qid: string, key: string) {
    const cur = answers[qid];
    const arr = Array.isArray(cur) ? cur : [];
    const next = arr.includes(key) ? arr.filter((k) => k !== key) : [...arr, key];
    setAnswers((current) => ({ ...current, [qid]: next }));
  }

  function setSubpartAnswer(questionId: string, partId: string, value: string) {
    setAnswers((current) => {
      const answer = current[questionId];
      const parts = typeof answer === "object" && answer && !Array.isArray(answer) ? answer : {};
      return { ...current, [questionId]: { ...parts, [partId]: value } };
    });
  }

  function requestRemoveCurrent() {
    if (!quiz || !q || !canDelete) return;
    setPendingDelete(true);
  }

  async function confirmRemoveCurrent() {
    if (!quiz || !q || !canDelete) return;
    const qid = q.id;
    setDeleteBusy(true);
    try {
      await api(`/quizzes/questions/${qid}`, { method: "DELETE" });
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "删除失败");
      setDeleteBusy(false);
      setPendingDelete(false);
      return;
    }
    originalRef.current = originalRef.current.filter((x) => x.id !== qid);
    const nextQs = quiz.questions.filter((x) => x.id !== qid);
    setAnswers((prev) => {
      const copy = { ...prev };
      delete copy[qid];
      return copy;
    });
    setQuiz({ ...quiz, questions: nextQs });
    setIdx((i) => (nextQs.length === 0 ? 0 : Math.min(i, nextQs.length - 1)));
    setMsg("");
    setPendingDelete(false);
    setDeleteBusy(false);
  }

  async function toggleFav() {
    if (!q) return;
    const qid = q.id;
    try {
      const data = await api<{ favorited: boolean }>(`/quizzes/questions/${qid}/favorite`, {
        method: "POST",
      });
      const patch = (item: Question) => (item.id === qid ? { ...item, favorited: data.favorited } : item);
      originalRef.current = originalRef.current.map(patch);
      setQuiz((prev) => (prev ? { ...prev, questions: prev.questions.map(patch) } : prev));
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "收藏失败");
    }
  }

  function requestSubmit() {
    if (!quiz || submitBusy) return;
    const missing = unansweredIndexes(quiz.questions, answers);
    if (missing.length === 0) {
      void submit();
      return;
    }
    setPendingUnanswered(missing);
  }

  function cancelPendingSubmit() {
    if (submitBusy) return;
    const first = pendingUnanswered?.[0];
    setPendingUnanswered(null);
    if (first !== undefined) setIdx(first);
  }

  async function submit() {
    if (!quiz || submitBusy) return;
    const question_ids = qFilter ? quiz.questions.map((x) => x.id) : undefined;
    setSubmitBusy(true);
    setMsg("");
    try {
      const data = await api<Result>(`/plays/${quiz.id}`, {
        method: "POST",
        body: JSON.stringify({
          answers,
          time_spent: seconds,
          mode: qFilter ? "wrong_retry" : mode,
          ...(question_ids ? { question_ids } : {}),
        }),
      });
      setResult(data);
      setPendingUnanswered(null);
      if (data.record_id) {
        try {
          const detail = await api<PlayDetail>(`/plays/${data.record_id}`);
          setPlayDetail(detail);
        } catch (e) {
          setMsg(e instanceof Error ? e.message : "加载作答详情失败");
        }

      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "交卷失败");
      setPendingUnanswered(null);
    } finally {
      setSubmitBusy(false);
    }
  }

  async function gradeQuestion(questionId: string) {
    if (!playDetail || gradingQuestionId) return;
    setGradingQuestionId(questionId);
    setMsg("");
    try {
      await api(`/plays/${playDetail.id}/questions/${questionId}/ai-grade`, { method: "POST" });
      const detail = await api<PlayDetail>(`/plays/${playDetail.id}`);
      setPlayDetail(detail);
      setResult((current) =>
        current
          ? {
              ...current,
              score: detail.score,
              correct: detail.correct,
              total: detail.total,
              graded_total: detail.graded_total,
              pending_ai_grading: detail.pending_ai_grading,
            }
          : current
      );
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "AI 批改失败");
    } finally {
      setGradingQuestionId(null);
    }
  }

  async function submitRating(score: number) {
    if (!quiz || qFilter || rateBusy) return;
    setRating(score);
    setRateBusy(true);
    setRateMsg("");
    try {
      const data = await api<{ avg: number; my_score: number; shared_to_plaza?: boolean }>(
        `/quizzes/${id}/rate`,
        { method: "POST", body: JSON.stringify({ score }) },
      );
      setRateMsg(data.shared_to_plaza ? "评分已同步到社区广场" : "已评分");
    } catch (e) {
      setRateMsg("");
      setMsg(e instanceof Error ? e.message : "评分失败");
    } finally {
      setRateBusy(false);
    }
  }

  if (!quiz) {
    if (loadError) {
      return (
        <div className="card space-y-3 p-4 sm:p-6">
          <p className="text-sm text-red-600">{loadError}</p>
          <Link className="btn-ghost" href="/plaza">
            返回广场
          </Link>
        </div>
      );
    }
    return <CardSkeleton lines={6} />;
  }
  if (!q) {
    return (
      <div className="card space-y-3 p-4 sm:p-6">
        <p>{qFilter ? "未找到要重练的题目。" : "题库中已没有题目。"}</p>
        <Link className="btn-ghost" href={qFilter ? "/wrong" : "/practice"}>
          {qFilter ? "返回错题本" : "返回题库"}
        </Link>
      </div>
    );
  }

  if (result) {
    const score = playDetail?.score ?? result.score;
    const correct = playDetail?.correct ?? result.correct;
    const total = playDetail?.total ?? result.total;
    const gradedTotal = playDetail?.graded_total ?? result.graded_total ?? total;
    const pendingAiGrading = playDetail?.pending_ai_grading ?? result.pending_ai_grading ?? 0;
    return (
      <>
      <div className="space-y-4">
        <div className="card space-y-3 p-4 sm:p-6">
          <h1 className="text-2xl font-semibold break-words">{quiz.title}</h1>
          <p className="text-sm text-slate-500">
            {score} 分 · 已判 {gradedTotal}/{total} 题 · 答对 {correct} 题 · 用时 {seconds} 秒
          </p>
          {pendingAiGrading > 0 && (
            <p className="text-sm text-amber-700">还有 {pendingAiGrading} 道主观题等待 AI 辅助批改。</p>
          )}
          {result.weak_skills.length > 0 && (
            <p className="text-sm text-amber-700">薄弱微技能：{result.weak_skills.join("、")}</p>
          )}
        </div>
        {playDetail ? (
          <PlayDetailCards
            details={playDetail.details}
            gradingQuestionId={gradingQuestionId}
            onGrade={(questionId) => void gradeQuestion(questionId)}
          />
        ) : (
          <ul className="card space-y-2 p-4 text-sm sm:p-6">
            {result.details.map((d, i) => (
              <li
                key={d.question_id}
                className={d.correct === null ? "text-amber-700" : d.correct ? "text-green-700" : "text-red-700"}
              >
                第 {i + 1} 题 {d.correct === null ? "待 AI 批改" : d.correct ? "正确" : "错误"} {d.explanation ? `· ${d.explanation}` : ""}
              </li>
            ))}
          </ul>
        )}
        {!qFilter && (
          <div className="card space-y-3 p-4 sm:p-6">
            <p className="text-sm font-medium">给这个题库打分吧！</p>
            <div className="flex flex-wrap items-center gap-1">
              {[1, 2, 3, 4, 5].map((n) => (
                <button
                  key={n}
                  type="button"
                  className="inline-flex h-11 w-11 items-center justify-center rounded-lg transition hover:bg-amber-50 disabled:opacity-60"
                  aria-label={`${n} 星`}
                  aria-pressed={rating >= n}
                  disabled={rateBusy}
                  onClick={() => void submitRating(n)}
                >
                  <Star
                    className={`h-7 w-7 ${
                      rating >= n ? "fill-amber-400 text-amber-400" : "fill-none text-slate-300"
                    }`}
                    strokeWidth={1.75}
                  />
                </button>
              ))}
            </div>
            {rateMsg ? <p className="text-sm text-emerald-700">{rateMsg}</p> : null}
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          <Link className="btn-primary" href="/wrong">
            去错题本
          </Link>
          <Link className="btn-ghost" href="/plaza">
            返回广场
          </Link>
        </div>
      </div>
      <ErrorDialog open={Boolean(msg)} description={msg} onClose={() => setMsg("")} />
      </>
    );
  }

  const multi = q.type === "multi_choice";

  return (
    <>
    <div className="card space-y-5 p-4 sm:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="min-w-0 break-words text-xl font-semibold">{quiz.title}</h1>
        <div className="flex flex-wrap items-center gap-2 text-sm text-slate-500">
          <FavoriteButton favorited={Boolean(q.favorited)} onToggle={() => void toggleFav()} />
          <span className="shrink-0">
            {progress} · {seconds}s
          </span>
          <select
            className="input w-28"
            value={mode}
            onChange={(e) => applyMode(e.target.value as "sequential" | "random")}
          >
            <option value="sequential">顺序</option>
            <option value="random">随机</option>
          </select>
        </div>
      </div>
      <p className="break-words text-lg">{q.content}</p>
      <p className="text-xs text-slate-400">微技能 {microSkillLabel(q.micro_skill)}</p>
      {isConstructedQuestion(q) ? (
        <fieldset className="space-y-3">
          <legend className="text-sm font-medium text-slate-700">请逐小问作答</legend>
          {q.subparts?.map((part, partIndex) => {
            const current = answers[q.id];
            const value =
              typeof current === "object" && current && !Array.isArray(current) ? current[part.id] || "" : "";
            const compact = q.type === "fill_blank";
            return (
              <label key={part.id} className="block space-y-1.5">
                <span className="text-sm font-medium text-slate-700">
                  第 {partIndex + 1} 问：{part.prompt}
                </span>
                {compact ? (
                  <input
                    className="input"
                    value={value}
                    onChange={(e) => setSubpartAnswer(q.id, part.id, e.target.value)}
                    placeholder="填写答案"
                  />
                ) : (
                  <textarea
                    className="input min-h-28"
                    value={value}
                    onChange={(e) => setSubpartAnswer(q.id, part.id, e.target.value)}
                    placeholder="写下你的推导、论证或答案"
                  />
                )}
              </label>
            );
          })}
        </fieldset>
      ) : q.type === "fill_blank" ? (
        <input
          className="input"
          value={typeof answers[q.id] === "string" ? (answers[q.id] as string) : ""}
          onChange={(e) => setAnswers((current) => ({ ...current, [q.id]: e.target.value }))}
          placeholder="填写答案"
        />
      ) : (
        <div className="space-y-2">
          {(q.options || []).map((o) => (
            <label
              key={o.key}
              className={`flex min-h-11 cursor-pointer items-start gap-2 rounded-xl border px-3 py-3 ${
                isChecked(q.id, o.key) ? "border-brand-600 bg-brand-50" : "border-slate-200"
              }`}
            >
              <input
                className="mt-1 shrink-0"
                type={multi ? "checkbox" : "radio"}
                name={q.id}
                checked={isChecked(q.id, o.key)}
                onChange={() => (multi ? toggleMulti(q.id, o.key) : pickSingle(q.id, o.key))}
              />
              <span className="min-w-0 flex-1 break-words">
                {formatOptionLabel(o, q.type, q.options)}
              </span>
            </label>
          ))}
        </div>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <button className="btn-ghost" disabled={idx === 0} onClick={() => setIdx(idx - 1)}>
          上一题
        </button>
        {canDelete && (
          <button className="btn-danger" onClick={requestRemoveCurrent}>
            删除
          </button>
        )}
        {idx < quiz.questions.length - 1 ? (
          <button className="btn-primary" onClick={() => setIdx(idx + 1)}>
            下一题
          </button>
        ) : (
          <button className="btn-primary" disabled={submitBusy} onClick={requestSubmit}>
            交卷
          </button>
        )}
      </div>
    </div>
    <ConfirmDialog
      open={pendingDelete}
      title="从题库删除"
      description="确定从题库删除本题？此操作不可撤销。"
      confirmLabel="删除"
      busy={deleteBusy}
      onCancel={() => !deleteBusy && setPendingDelete(false)}
      onConfirm={() => void confirmRemoveCurrent()}
    />
    <ConfirmDialog
      open={pendingUnanswered !== null}
      title="还有题目未作答"
      description={pendingUnanswered ? unansweredSubmitDescription(pendingUnanswered) : ""}
      confirmLabel="仍要交卷"
      cancelLabel="返回作答"
      busy={submitBusy}
      onCancel={cancelPendingSubmit}
      onConfirm={() => void submit()}
    />
    <ErrorDialog open={Boolean(msg)} description={msg} onClose={() => setMsg("")} />
    </>
  );
}
