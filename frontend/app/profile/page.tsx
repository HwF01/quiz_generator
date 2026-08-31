"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, getToken } from "@/lib/api";
import { useRouter } from "next/navigation";
import { PlayDetailDialog, type PlayDetail } from "@/components/PlayDetailDialog";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ListSkeleton } from "@/components/ListSkeleton";
import { quizStatusLabel } from "@/lib/labels";
import { isQuizInFlight, quizQuestionCountLabel } from "@/lib/quiz-status";

type Quiz = {
  id: string;
  title: string;
  status: string;
  question_count: number;
  visibility: string;
  category: string;
  generation_job_id?: string | null;
  blueprint?: { total_questions?: number } | null;
};

type Play = {
  id: string;
  quiz_id: string;
  title: string;
  score: number;
  time_spent?: number;
  mode?: string;
  created_at: string | null;
};

function scoreTone(score: number): string {
  if (score >= 80) return "bg-emerald-50 text-emerald-700";
  if (score >= 60) return "bg-amber-50 text-amber-800";
  return "bg-rose-50 text-rose-700";
}

function formatWhen(iso: string | null): string {
  if (!iso) return "时间未知";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDuration(seconds?: number): string {
  const total = Math.max(0, Math.round(seconds ?? 0));
  if (total < 60) return `${total} 秒`;
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return rest ? `${minutes} 分 ${rest} 秒` : `${minutes} 分钟`;
}

function modeLabel(mode?: string): string {
  if (mode === "random") return "随机";
  if (mode === "wrong_retry") return "错题重练";
  return "顺序";
}

export default function ProfilePage() {
  const router = useRouter();
  const [quizzes, setQuizzes] = useState<Quiz[]>([]);
  const [favs, setFavs] = useState<Quiz[]>([]);
  const [plays, setPlays] = useState<Play[]>([]);
  const [me, setMe] = useState<{ nickname: string; email: string; quota?: { remaining: number; limit: number } } | null>(null);
  const [detail, setDetail] = useState<PlayDetail | null>(null);
  const [detailError, setDetailError] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [pendingPlayId, setPendingPlayId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const hasInflight = quizzes.some((q) => isQuizInFlight(q.status));

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    Promise.all([
      api<typeof me>("/auth/me").then(setMe),
      api<Quiz[]>("/quizzes").then(setQuizzes),
      api<Quiz[]>("/quizzes/favorites").then(setFavs).catch(() => setFavs([])),
      api<Play[]>("/plays").then(setPlays).catch(() => setPlays([])),
    ]).finally(() => setLoading(false));
  }, [router]);

  useEffect(() => {
    if (!hasInflight) return;
    const timer = setInterval(() => {
      api<Quiz[]>("/quizzes")
        .then(setQuizzes)
        .catch(() => {
          /* keep showing last snapshot through transient errors */
        });
    }, 1500);
    return () => clearInterval(timer);
  }, [hasInflight]);

  async function openDetail(playId: string) {
    setDetailError("");
    setBusyId(playId);
    try {
      const data = await api<PlayDetail>(`/plays/${playId}`);
      setDetail(data);
    } catch (e) {
      setDetailError(e instanceof Error ? e.message : "加载详情失败");
    } finally {
      setBusyId(null);
    }
  }

  function requestRemovePlay(playId: string) {
    setPendingPlayId(playId);
  }

  async function confirmRemovePlay() {
    if (!pendingPlayId) return;
    setDetailError("");
    setBusyId(pendingPlayId);
    try {
      await api(`/plays/${pendingPlayId}`, { method: "DELETE" });
      setPlays((prev) => prev.filter((p) => p.id !== pendingPlayId));
      setDetail((prev) => (prev?.id === pendingPlayId ? null : prev));
      setPendingPlayId(null);
    } catch (e) {
      setDetailError(e instanceof Error ? e.message : "删除失败");
    } finally {
      setBusyId(null);
    }
  }

  if (loading) {
    return (
      <div className="space-y-8">
        <div>
          <h1 className="text-2xl font-semibold">我的题库</h1>
          <p className="text-sm text-slate-500">正在加载你的题库与练习记录。</p>
        </div>
        <ListSkeleton cards={3} label="正在加载我的题库" />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">{me?.nickname || "我的主页"}</h1>
        <p className="text-sm text-slate-500">
          {me?.email} · 今日剩余生成 {me?.quota?.remaining ?? "-"} / {me?.quota?.limit ?? "-"}
        </p>
      </div>
      <section>
        <h2 className="mb-3 font-medium">我创建的</h2>
        <div className="grid gap-3 md:grid-cols-2">
          {quizzes.map((q) => (
            <Link key={q.id} href={`/quizzes/${q.id}`} className="card p-4 hover:border-brand-500 active:border-brand-500">
              <div className="flex items-start justify-between gap-2">
                <strong className="min-w-0 break-words">{q.title}</strong>
                <span className="badge shrink-0">{quizStatusLabel(q.status)}</span>
              </div>
              <p className="mt-2 text-sm text-slate-500">
                {q.category} · {quizQuestionCountLabel(q)} · {q.visibility === "public" ? "公开" : "私密"}
              </p>
            </Link>
          ))}
          {quizzes.length === 0 && <p className="text-sm text-slate-500">还没有题库，去上传一份文档吧。</p>}
        </div>
      </section>
      <section>
        <h2 className="mb-3 font-medium">收藏的题库</h2>
        <div className="flex flex-wrap items-end gap-x-4 gap-y-2">
          {favs.map((q) => (
            <Link
              key={q.id}
              href={`/quizzes/${q.id}`}
              className="border-b-2 border-transparent pb-1 text-sm text-slate-600 transition hover:border-brand-600 hover:text-brand-700"
            >
              {q.title}
            </Link>
          ))}
          {favs.length === 0 && <p className="text-sm text-slate-500">暂无收藏</p>}
        </div>
      </section>
      <section>
        <div className="mb-3 flex items-baseline justify-between gap-3">
          <h2 className="font-medium">刷题记录</h2>
          {plays.length > 0 && <span className="text-xs text-slate-400">{plays.length} 次</span>}
        </div>
        {detailError && <p className="mb-3 text-sm text-red-600">{detailError}</p>}
        <div className="space-y-3">
          {plays.map((p) => (
            <article key={p.id} className="card p-4 sm:p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="font-medium break-words">{p.title || "未知题库"}</h3>
                  <p className="mt-1 text-sm text-slate-500">
                    {formatWhen(p.created_at)} · 用时 {formatDuration(p.time_spent)} · {modeLabel(p.mode)}
                  </p>
                </div>
                <span className={`shrink-0 rounded-full px-2.5 py-1 text-sm font-semibold ${scoreTone(p.score)}`}>
                  {p.score} 分
                </span>
              </div>
              <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-100">
                <div
                  className="h-full rounded-full bg-brand-500 transition-[width] duration-500 ease-out"
                  style={{ width: `${Math.max(0, Math.min(100, p.score))}%` }}
                />
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  className="btn-ghost"
                  disabled={busyId === p.id}
                  onClick={() => void openDetail(p.id)}
                >
                  {busyId === p.id ? "加载中…" : "详情"}
                </button>
                <button
                  type="button"
                  className="btn-danger"
                  disabled={busyId === p.id}
                  onClick={() => requestRemovePlay(p.id)}
                >
                  删除
                </button>
              </div>
            </article>
          ))}
          {plays.length === 0 && <p className="text-sm text-slate-500">还没有刷题记录，去题库或广场练一套吧。</p>}
        </div>
      </section>
      {detail && <PlayDetailDialog detail={detail} onClose={() => setDetail(null)} />}
      <ConfirmDialog
        open={pendingPlayId !== null}
        title="删除刷题记录"
        description="确定删除这条刷题记录？此操作不可撤销。"
        confirmLabel="删除"
        busy={busyId === pendingPlayId}
        onCancel={() => !busyId && setPendingPlayId(null)}
        onConfirm={() => void confirmRemovePlay()}
      />
    </div>
  );
}
