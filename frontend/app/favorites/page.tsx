"use client";

import { useEffect, useMemo, useState } from "react";
import { api, getToken } from "@/lib/api";
import { filterByQuiz, groupByQuiz, uniqueQuizzes } from "@/lib/quiz-groups";
import { formatOptionLabel } from "@/lib/options";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { FavoriteButton } from "@/components/FavoriteButton";
import { QuizFilterTabs } from "@/components/QuizFilterTabs";

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

export default function FavoritesPage() {
  const router = useRouter();
  const [rows, setRows] = useState<Row[]>([]);
  const [quizId, setQuizId] = useState<string | null>(null);

  async function load() {
    const data = await api<Row[]>("/question-favorites");
    setRows(data);
  }

  useEffect(() => {
    if (!getToken()) router.push("/login");
    load().catch(() => {});
  }, [router]);

  const quizzes = useMemo(() => uniqueQuizzes(rows), [rows]);
  const groups = useMemo(() => groupByQuiz(filterByQuiz(rows, quizId)), [rows, quizId]);

  async function toggleFav(questionId: string) {
    await api(`/quizzes/questions/${questionId}/favorite`, { method: "POST" });
    await load();
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">收藏</h1>
      <QuizFilterTabs quizzes={quizzes} activeId={quizId} onSelect={setQuizId} />
      {groups.map((g) => (
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
                <p className="min-w-0 text-xs text-slate-500">{r.question.micro_skill}</p>
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
      {rows.length === 0 && <p className="text-sm text-slate-500">还没有收藏。做题或审校时可以收藏题目。</p>}
    </div>
  );
}
