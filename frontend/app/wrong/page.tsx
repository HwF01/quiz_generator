"use client";

import { useEffect, useMemo, useState } from "react";
import { api, getToken } from "@/lib/api";
import { filterByQuiz, groupByQuiz, uniqueQuizzes } from "@/lib/quiz-groups";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { FavoriteButton } from "@/components/FavoriteButton";
import { QuizFilterTabs } from "@/components/QuizFilterTabs";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ListSkeleton } from "@/components/ListSkeleton";
import { microSkillLabel } from "@/lib/labels";

type Row = {
  wrong_count: number;
  favorited: boolean;
  last_wrong_at: string;
  quiz: { id: string; title: string; category: string };
  question: {
    id: string;
    content: string;
    micro_skill: string;
    quiz_set_id: string;
  };
};

export default function WrongPage() {
  const router = useRouter();
  const [rows, setRows] = useState<Row[]>([]);
  const [quizId, setQuizId] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  async function load(opts?: { silent?: boolean }) {
    if (!opts?.silent) setLoading(true);
    try {
      setRows(await api<Row[]>("/wrong-questions"));
    } finally {
      if (!opts?.silent) setLoading(false);
    }
  }

  useEffect(() => {
    if (!getToken()) router.push("/login");
    load().catch(() => {});
  }, [router]);

  const quizzes = useMemo(() => uniqueQuizzes(rows), [rows]);
  const groups = useMemo(() => groupByQuiz(filterByQuiz(rows, quizId)), [rows, quizId]);

  function requestRemove(questionId: string) {
    setPendingId(questionId);
  }

  async function confirmRemove() {
    if (!pendingId) return;
    setDeleteBusy(true);
    try {
      await api(`/wrong-questions/${pendingId}`, { method: "DELETE" });
      setPendingId(null);
      await load({ silent: true });
    } finally {
      setDeleteBusy(false);
    }
  }

  async function toggleFav(questionId: string) {
    await api(`/quizzes/questions/${questionId}/favorite`, { method: "POST" });
    await load({ silent: true });
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">错题本</h1>
      {loading ? <ListSkeleton columns={false} cards={3} label="正在加载错题本" /> : null}
      {loading ? null : <QuizFilterTabs quizzes={quizzes} activeId={quizId} onSelect={setQuizId} />}
      {!loading && groups.map((g) => (
        <section key={g.quiz.id} className="space-y-3">
          <h2 className="text-sm font-medium text-slate-600">
            <Link href={`/quizzes/${g.quiz.id}`} className="hover:text-brand-700 hover:underline">
              {g.quiz.title}
            </Link>
            {g.quiz.category ? ` · ${g.quiz.category}` : ""}
            <span className="ml-2 text-slate-400">{g.items.length} 题</span>
          </h2>
          {g.items.map((r) => (
            <article key={r.question.id} className="card p-5">
              <div className="flex items-start justify-between gap-3">
                <p className="min-w-0 text-xs text-slate-500">
                  错 {r.wrong_count} 次 · {microSkillLabel(r.question.micro_skill)}
                </p>
                <FavoriteButton favorited={r.favorited} onToggle={() => void toggleFav(r.question.id)} />
              </div>
              <p className="mt-2 break-words font-medium">{r.question.content}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Link
                  className="btn-ghost"
                  href={`/practice/${r.question.quiz_set_id}?q=${encodeURIComponent(r.question.id)}`}
                >
                  再练一次
                </Link>
                <button
                  className="btn-danger"
                  type="button"
                  onClick={() => requestRemove(r.question.id)}
                >
                  删除本题
                </button>
              </div>
            </article>
          ))}
        </section>
      ))}
      {!loading && rows.length === 0 && <p className="text-sm text-slate-500">还没有错题。</p>}
      <ConfirmDialog
        open={pendingId !== null}
        title="从错题本删除"
        description="确定从错题本删除本题？题库中的原题不会被删除。"
        confirmLabel="删除"
        busy={deleteBusy}
        onCancel={() => !deleteBusy && setPendingId(null)}
        onConfirm={() => void confirmRemove()}
      />
    </div>
  );
}
