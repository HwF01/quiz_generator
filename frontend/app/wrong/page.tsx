"use client";

import { useEffect, useState } from "react";
import { api, getToken } from "@/lib/api";
import { useRouter } from "next/navigation";
import Link from "next/link";

type Row = {
  wrong_count: number;
  is_starred: boolean;
  last_wrong_at: string;
  question: {
    id: string;
    content: string;
    options: { key: string; text: string }[] | null;
    micro_skill: string;
    quiz_set_id: string;
  };
};

export default function WrongPage() {
  const router = useRouter();
  const [rows, setRows] = useState<Row[]>([]);

  async function load() {
    const data = await api<Row[]>("/wrong-questions");
    setRows(data);
  }

  useEffect(() => {
    if (!getToken()) router.push("/login");
    load().catch(() => {});
  }, [router]);

  async function removeRow(questionId: string) {
    if (!window.confirm("确定从错题本删除本题？题库中的原题不会被删除。")) return;
    await api(`/wrong-questions/${questionId}`, { method: "DELETE" });
    await load();
  }

  async function toggleStar(questionId: string) {
    await api(`/wrong-questions/${questionId}/star`, { method: "POST" });
    await load();
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">错题本</h1>
      {rows.map((r) => (
        <article key={r.question.id} className="card p-5">
          <p className="text-xs text-slate-500">
            错 {r.wrong_count} 次 · {r.question.micro_skill}
            {r.is_starred ? " · 重点" : ""}
          </p>
          <p className="mt-2 font-medium">{r.question.content}</p>
          <ul className="mt-2 text-sm">
            {(r.question.options || []).map((o) => (
              <li key={o.key}>
                {o.key}. {o.text}
              </li>
            ))}
          </ul>
          <div className="mt-3 flex flex-wrap gap-2">
            <Link
              className="btn-ghost"
              href={`/practice/${r.question.quiz_set_id}?q=${encodeURIComponent(r.question.id)}`}
            >
              再练一次
            </Link>
            <button className="btn-ghost" type="button" onClick={() => toggleStar(r.question.id)}>
              {r.is_starred ? "取消重点" : "重点标记"}
            </button>
            <button
              className="btn-ghost text-red-600"
              type="button"
              onClick={() => removeRow(r.question.id)}
            >
              删除本题
            </button>
          </div>
        </article>
      ))}
      {rows.length === 0 && <p className="text-sm text-slate-500">还没有错题。</p>}
    </div>
  );
}
