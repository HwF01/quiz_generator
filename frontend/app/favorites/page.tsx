"use client";

import { useEffect, useMemo, useState } from "react";
import { api, getToken } from "@/lib/api";
import { filterByQuiz, groupByQuiz, uniqueQuizzes } from "@/lib/quiz-groups";
import { formatOptionLabel } from "@/lib/options";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { FavoriteButton } from "@/components/FavoriteButton";
import { QuizFilterTabs } from "@/components/QuizFilterTabs";
import { StartPracticeButton } from "@/components/StartPracticeButton";
import { ListSkeleton } from "@/components/ListSkeleton";
import { microSkillLabel } from "@/lib/labels";

const QUIZ_SETS_TAB = "quiz-sets";

type Row = {
  favorited: boolean;
  created_at: string | null;
  quiz: { id: string; title: string; category: string };
  question: {
    id: string;
    content: string;
    type?: string;
    options: { key: string; text: string }[] | null;
    micro_skill: string;
    quiz_set_id: string;
  };
};

type QuizFav = {
  id: string;
  title: string;
  category: string;
  question_count: number;
  visibility: string;
  favorited: boolean;
};

export default function FavoritesPage() {
  const router = useRouter();
  const [rows, setRows] = useState<Row[]>([]);
  const [quizFavs, setQuizFavs] = useState<QuizFav[]>([]);
  const [quizId, setQuizId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const showingQuizSets = quizId === QUIZ_SETS_TAB;

  async function load(opts?: { silent?: boolean }) {
    if (!opts?.silent) setLoading(true);
    try {
      const [questions, sets] = await Promise.all([
        api<Row[]>("/question-favorites"),
        api<QuizFav[]>("/quizzes/favorites"),
      ]);
      setRows(questions);
      setQuizFavs(sets);
      setLoadError("");
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "加载收藏失败");
    } finally {
      if (!opts?.silent) setLoading(false);
    }
  }

  useEffect(() => {
    if (!getToken()) router.push("/login");
    void load();
  }, [router]);

  const quizzes = useMemo(() => uniqueQuizzes(rows), [rows]);
  const groups = useMemo(
    () => (showingQuizSets ? [] : groupByQuiz(filterByQuiz(rows, quizId))),
    [rows, quizId, showingQuizSets]
  );

  async function toggleFav(questionId: string) {
    await api(`/quizzes/questions/${questionId}/favorite`, { method: "POST" });
    await load({ silent: true });
  }

  async function toggleQuizFav(id: string) {
    await api(`/quizzes/${id}/favorite`, { method: "POST" });
    await load({ silent: true });
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">收藏</h1>
      {loading ? <ListSkeleton columns={false} cards={3} label="正在加载收藏" /> : null}
      {loadError ? <p className="text-sm text-red-600">{loadError}</p> : null}
      {loading ? null : (
        <QuizFilterTabs
          quizzes={quizzes}
          activeId={quizId}
          onSelect={setQuizId}
          extraTabs={[{ id: QUIZ_SETS_TAB, label: "收藏的题库" }]}
        />
      )}
      {!loading && showingQuizSets ? (
        <div className="grid gap-3 md:grid-cols-2">
          {quizFavs.map((q) => (
            <article key={q.id} className="card p-4">
              <div className="flex items-start justify-between gap-2">
                <Link href={`/quizzes/${q.id}`} className="min-w-0 break-words font-medium hover:text-brand-700">
                  {q.title}
                </Link>
                <FavoriteButton favorited={q.favorited} onToggle={() => void toggleQuizFav(q.id)} />
              </div>
              <p className="mt-2 text-sm text-slate-500">
                {q.category} · {q.question_count} 题 · {q.visibility === "public" ? "公开" : "私密"}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <StartPracticeButton quizId={q.id}>刷题</StartPracticeButton>
                <Link className="btn-ghost" href={`/quizzes/${q.id}`}>
                  查看
                </Link>
              </div>
            </article>
          ))}
          {!loadError && quizFavs.length === 0 ? (
            <p className="text-sm text-slate-500 md:col-span-2">还没有收藏题库。可在题库管理/审校或广场收藏。</p>
          ) : null}
        </div>
      ) : null}
      {!loading &&
        !showingQuizSets &&
        groups.map((g) => (
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
                  <p className="min-w-0 text-xs text-slate-500">{microSkillLabel(r.question.micro_skill)}</p>
                  <FavoriteButton favorited={r.favorited} onToggle={() => void toggleFav(r.question.id)} />
                </div>
                <p className="mt-2 break-words font-medium">{r.question.content}</p>
                <ul className="mt-2 text-sm">
                  {(r.question.options || []).map((o) => (
                    <li key={o.key} className="break-words">
                      {formatOptionLabel(o, r.question.type, r.question.options)}
                    </li>
                  ))}
                </ul>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Link
                    className="btn-ghost"
                    href={`/practice/${r.question.quiz_set_id}?q=${encodeURIComponent(r.question.id)}`}
                  >
                    去练习
                  </Link>
                </div>
              </article>
            ))}
          </section>
        ))}
      {!loading && !showingQuizSets && !loadError && rows.length === 0 ? (
        <p className="text-sm text-slate-500">还没有收藏题目。做题或审校时可以收藏题目。</p>
      ) : null}
    </div>
  );
}
