"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import { ListSkeleton } from "@/components/ListSkeleton";
import { quizStatusLabel } from "@/lib/labels";
import { isListedForPractice, isQuizWaitingForQuestions, quizQuestionCountLabel } from "@/lib/quiz-status";

type Quiz = {
  id: string;
  title: string;
  status: string;
  question_count: number;
  category: string;
  blueprint?: { total_questions?: number } | null;
};

function canStartPractice(quiz: Quiz): boolean {
  return !isQuizWaitingForQuestions(quiz) && quiz.question_count > 0;
}

export default function PracticeIndexPage() {
  const router = useRouter();
  const [quizzes, setQuizzes] = useState<Quiz[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    api<Quiz[]>("/quizzes")
      .then((list) => setQuizzes(list.filter(isListedForPractice)))
      .catch((e) => setLoadError(e instanceof Error ? e.message : "加载题库失败"))
      .finally(() => setLoading(false));
  }, [router]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">点击刷题</h1>
        <p className="text-sm text-slate-500">选择题库开始练习。题目选项在作答时才会显示。</p>
      </div>
      {loading ? <ListSkeleton cards={3} label="正在加载可刷题库" /> : null}
      {loadError ? <p className="text-sm text-red-600">{loadError}</p> : null}
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
                  {ready ? (
                    <Link className="btn-primary" href={`/practice/${q.id}`}>
                      开始刷题
                    </Link>
                  ) : (
                    <span className="btn-primary pointer-events-none opacity-50" aria-disabled="true">
                      开始刷题
                    </span>
                  )}
                </div>
              </article>
            );
          })}
          {quizzes.length === 0 && !loadError ? (
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
