"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import Link from "next/link";

type Question = {
  id: string;
  type: string;
  content: string;
  options: { key: string; text: string }[] | null;
  micro_skill: string;
};

type Quiz = { id: string; title: string; questions: Question[] };

type Result = {
  score: number;
  correct: number;
  total: number;
  details: { question_id: string; correct: boolean; answer: unknown; explanation?: string }[];
  weak_skills: string[];
  mastery: Record<string, number>;
};

type AnswerValue = string | string[];

function shuffle<T>(items: T[]): T[] {
  const copy = [...items];
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
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
  const [rating, setRating] = useState(5);
  const [mode, setMode] = useState<"sequential" | "random">("sequential");
  const [qFilter, setQFilter] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) router.push("/login");
    const search = typeof window !== "undefined" ? window.location.search : "";
    const params = new URLSearchParams(search);
    const filter = params.get("q") || params.get("question") || params.get("question_id");
    setQFilter(filter);
    api<Quiz>(`/quizzes/${id}?purpose=practice`).then((raw) => {
      const questions = filter ? raw.questions.filter((x) => x.id === filter) : raw.questions;
      originalRef.current = questions;
      setQuiz({ ...raw, questions });
      setIdx(0);
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

  function isChecked(qid: string, key: string) {
    const v = answers[qid];
    return Array.isArray(v) ? v.includes(key) : v === key;
  }

  function pickSingle(qid: string, key: string) {
    setAnswers({ ...answers, [qid]: key });
  }

  function toggleMulti(qid: string, key: string) {
    const cur = answers[qid];
    const arr = Array.isArray(cur) ? cur : [];
    const next = arr.includes(key) ? arr.filter((k) => k !== key) : [...arr, key];
    setAnswers({ ...answers, [qid]: next });
  }

  async function submit() {
    if (!quiz) return;
    const question_ids = qFilter ? quiz.questions.map((x) => x.id) : undefined;
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
  }

  if (!quiz) return <p>加载中…</p>;
  if (!q) {
    return (
      <div className="card space-y-3 p-6">
        <p>未找到要重练的题目。</p>
        <Link className="btn-ghost" href="/wrong">
          返回错题本
        </Link>
      </div>
    );
  }

  if (result) {
    return (
      <div className="card space-y-4 p-6">
        <h1 className="text-2xl font-semibold">成绩 {result.score} 分</h1>
        <p>
          答对 {result.correct}/{result.total} · 用时 {seconds} 秒
        </p>
        {result.weak_skills.length > 0 && (
          <p className="text-sm text-amber-700">薄弱微技能：{result.weak_skills.join("、")}</p>
        )}
        <ul className="space-y-2 text-sm">
          {result.details.map((d, i) => (
            <li key={d.question_id} className={d.correct ? "text-green-700" : "text-red-700"}>
              第 {i + 1} 题 {d.correct ? "正确" : "错误"} {d.explanation ? `· ${d.explanation}` : ""}
            </li>
          ))}
        </ul>
        <div className="flex items-center gap-2">
          <span className="text-sm">评分</span>
          <select className="input w-24" value={rating} onChange={(e) => setRating(Number(e.target.value))}>
            {[1, 2, 3, 4, 5].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
          <button
            className="btn-ghost"
            onClick={() => api(`/quizzes/${id}/rate`, { method: "POST", body: JSON.stringify({ score: rating }) })}
          >
            提交评分
          </button>
        </div>
        <div className="flex gap-2">
          <Link className="btn-primary" href="/wrong">
            去错题本
          </Link>
          <Link className="btn-ghost" href="/plaza">
            返回广场
          </Link>
        </div>
      </div>
    );
  }

  const multi = q.type === "multi_choice";

  return (
    <div className="card space-y-5 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{quiz.title}</h1>
        <div className="text-sm text-slate-500">
          {progress} · {seconds}s
          <select
            className="input ml-2 w-28"
            value={mode}
            onChange={(e) => applyMode(e.target.value as "sequential" | "random")}
          >
            <option value="sequential">顺序</option>
            <option value="random">随机</option>
          </select>
        </div>
      </div>
      <p className="text-lg">{q.content}</p>
      <p className="text-xs text-slate-400">微技能 {q.micro_skill}</p>
      {q.type === "fill_blank" ? (
        <input
          className="input"
          value={typeof answers[q.id] === "string" ? (answers[q.id] as string) : ""}
          onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })}
          placeholder="填写答案"
        />
      ) : (
        <div className="space-y-2">
          {(q.options || []).map((o) => (
            <label
              key={o.key}
              className={`flex cursor-pointer items-center gap-2 rounded-xl border px-3 py-2 ${
                isChecked(q.id, o.key) ? "border-brand-600 bg-brand-50" : "border-slate-200"
              }`}
            >
              <input
                type={multi ? "checkbox" : "radio"}
                name={q.id}
                checked={isChecked(q.id, o.key)}
                onChange={() => (multi ? toggleMulti(q.id, o.key) : pickSingle(q.id, o.key))}
              />
              {o.key}. {o.text}
            </label>
          ))}
        </div>
      )}
      <div className="flex justify-between">
        <button className="btn-ghost" disabled={idx === 0} onClick={() => setIdx(idx - 1)}>
          上一题
        </button>
        {idx < quiz.questions.length - 1 ? (
          <button className="btn-primary" onClick={() => setIdx(idx + 1)}>
            下一题
          </button>
        ) : (
          <button className="btn-primary" onClick={submit}>
            交卷
          </button>
        )}
      </div>
    </div>
  );
}
