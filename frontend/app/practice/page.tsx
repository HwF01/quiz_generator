"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import { ListSkeleton } from "@/components/ListSkeleton";
import { quizStatusLabel } from "@/lib/labels";
import { isQuizWaitingForQuestions, quizQuestionCountLabel } from "@/lib/quiz-status";

type Quiz = {
  id: string;
  title: string;
  status: string;
  question_count: number;
  category: string;
  blueprint?: { total_questions?: number } | null;
};

function canStartPractice(quiz: Quiz): boolean {
  if (isQuizWaitingForQuestions(quiz)) return false;
  return quiz.question_count > 0;
}

export default function PracticePickPage() {
  const router = useRouter();
  const [quizzes, setQuizzes] = useState<Quiz[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    api<Quiz[]>("/quizzes")
      .then(setQuizzes)
      .catch((e) => setError(e instanceof Error ? e.message : "加载题库失败"))
      .finally(() => setLoading(false));
  }, [router]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">点击刷题</h1>
        <p className="text-sm text-slate-500">选择题库开始练习。</p>
      </div>
      {loading ? <ListSkeleton cards={4} label="正在加载可练习题库" /> : null}
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      {loading ? null : (
        <div className="grid gap-3 md:grid-cols-2">
          {quizzes.map((q) => {
            const ready = canStartPractice(q);
            return (
              <article key={q.id} className="card p-4">
                <div className="flex items-start justify-between gap-2">
                  <h2 className="min-w-0 break-words font-medium">{q.title}</h2>
                  <span className="badge shrink-0">{quizStatusLabel(q.status)}</span>
                </div>
                <p className="mt-2 text-sm text-slate-500">
                  {q.category} · {quizQuestionCountLabel(q)}
                </p>
                <div className="mt-3">
                  <Link
                    className={`btn-primary ${ready ? "" : "pointer-events-none opacity-50"}`}
                    href={`/practice/${q.id}`}
                    aria-disabled={!ready}
                    onClick={(event) => {
                      if (!ready) event.preventDefault();
                    }}
                  >
                    开始刷题
                  </Link>
                </div>
              </article>
            );
          })}
          {quizzes.length === 0 && !error ? (
            <p className="text-sm text-slate-500 md:col-span-2">
              还没有可刷的题库。去{" "}
              <Link href="/upload" className="text-brand-700 hover:underline">
                上传出题
              </Link>{" "}
              或{" "}
              <Link href="/plaza" className="text-brand-700 hover:underline">
                逛广场
              </Link>
              。
            </p>
          ) : null}
        </div>
      )}
    </div>
  );
}
