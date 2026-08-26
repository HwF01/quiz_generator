"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, getToken } from "@/lib/api";
import { useRouter } from "next/navigation";

type Quiz = {
  id: string;
  title: string;
  status: string;
  question_count: number;
  visibility: string;
  category: string;
};

type Play = { id: string; quiz_id: string; title: string; score: number; created_at: string };

export default function ProfilePage() {
  const router = useRouter();
  const [quizzes, setQuizzes] = useState<Quiz[]>([]);
  const [favs, setFavs] = useState<Quiz[]>([]);
  const [plays, setPlays] = useState<Play[]>([]);
  const [me, setMe] = useState<{ nickname: string; email: string; quota?: { remaining: number; limit: number } } | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    api<typeof me>("/auth/me").then(setMe);
    api<Quiz[]>("/quizzes").then(setQuizzes);
    api<Quiz[]>("/quizzes/favorites").then(setFavs).catch(() => setFavs([]));
    api<Play[]>("/plays").then(setPlays).catch(() => setPlays([]));
  }, [router]);

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
                <span className="badge shrink-0">{q.status}</span>
              </div>
              <p className="mt-2 text-sm text-slate-500">
                {q.category} · {q.question_count} 题 · {q.visibility === "public" ? "公开" : "私密"}
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
        <h2 className="mb-3 font-medium">刷题记录</h2>
        <ul className="space-y-2 text-sm">
          {plays.map((p) => (
            <li key={p.id} className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 px-3 py-2">
              <span className="min-w-0 truncate">{p.title}</span>
              <span className="shrink-0">{p.score} 分</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
