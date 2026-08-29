"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import { isUnnamedTitle, nextUnnamedTitle, withDuplicateSuffix } from "@/lib/quiz-title";

type Job = {
  id: string;
  status: string;
  progress: number;
  stage: string;
  error?: string;
  quiz_set_id?: string;
  models_used?: Record<string, string>;
};

async function fetchQuizTitles(): Promise<string[]> {
  const list = await api<{ id: string; title: string }[]>("/quizzes");
  return list.map((q) => q.title);
}

async function uploadDocument(uploadFile: File): Promise<{ id: string }> {
  const fd = new FormData();
  fd.append("file", uploadFile);
  return api<{ id: string }>("/documents/upload", { method: "POST", body: fd });
}

export default function UploadPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("未命名题库1");
  const [subject, setSubject] = useState("auto");
  const [category, setCategory] = useState("自定义");
  const [total, setTotal] = useState(8);
  const [visibility, setVisibility] = useState("private");
  const [job, setJob] = useState<Job | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [force, setForce] = useState(false);
  const [dupPrompt, setDupPrompt] = useState<{ requested: string; resolved: string } | null>(null);
  const titleTouchedRef = useRef(false);
  const titlesCacheRef = useRef<string[] | null>(null);

  useEffect(() => {
    if (!getToken()) router.push("/login");
  }, [router]);

  useEffect(() => {
    fetchQuizTitles()
      .then((titles) => {
        titlesCacheRef.current = titles;
        if (!titleTouchedRef.current) setTitle(nextUnnamedTitle(titles));
      })
      .catch(() => {
        titlesCacheRef.current = titlesCacheRef.current ?? [];
      });
  }, []);

  useEffect(() => {
    if (!job || job.status === "succeeded" || job.status === "failed") return;
    const t = setInterval(async () => {
      try {
        const next = await api<Job>(`/jobs/${job.id}`);
        setJob(next);
        if (next.status === "succeeded" && next.quiz_set_id) {
          router.push(`/quizzes/${next.quiz_set_id}`);
        }
      } catch {
        /* keep polling through transient proxy/500s */
      }
    }, 1500);
    return () => clearInterval(t);
  }, [job, router]);

  async function requestGenerate(documentId: string, finalTitle: string) {
    const gen = await api<{ job_id: string; quiz_id: string }>("/quizzes/generate", {
      method: "POST",
      body: JSON.stringify({
        document_id: documentId,
        title: finalTitle,
        category,
        subject,
        visibility,
        blueprint: {
          total_questions: total,
          max_detail_ratio: 0.3,
          target_grade: "通用",
          type_mix: { single_choice: 0.8, true_false: 0.2 },
        },
        force,
      }),
    });
    setJob({ id: gen.job_id, status: "queued", progress: 0, stage: "排队中", quiz_set_id: gen.quiz_id });
  }

  async function submitGenerate(uploadFile: File, finalTitle: string) {
    const doc = await uploadDocument(uploadFile);
    await requestGenerate(doc.id, finalTitle);
  }

  async function start() {
    if (!file) return;
    setErr("");
    setBusy(true);
    try {
      const trimmed = title.trim();
      const autoTitle = !titleTouchedRef.current || isUnnamedTitle(trimmed);
      const titlesPromise = fetchQuizTitles()
        .then((titles) => {
          titlesCacheRef.current = titles;
          return titles;
        })
        .catch(() => titlesCacheRef.current ?? []);

      if (autoTitle) {
        const [existingTitles, doc] = await Promise.all([titlesPromise, uploadDocument(file)]);
        await requestGenerate(doc.id, nextUnnamedTitle(existingTitles));
        return;
      }

      const existingTitles = titlesCacheRef.current ?? (await titlesPromise);
      if (existingTitles.includes(trimmed)) {
        setDupPrompt({ requested: trimmed, resolved: withDuplicateSuffix(trimmed, existingTitles) });
        return;
      }
      const doc = await uploadDocument(file);
      await requestGenerate(doc.id, trimmed);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "上传失败");
    } finally {
      setBusy(false);
    }
  }

  async function confirmDuplicate() {
    if (!dupPrompt || !file) return;
    const finalTitle = dupPrompt.resolved;
    setDupPrompt(null);
    setErr("");
    setBusy(true);
    try {
      await submitGenerate(file, finalTitle);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "上传失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <div className="card space-y-4 p-4 sm:p-6">
        <h1 className="text-xl font-semibold">上传文档出题</h1>
        <p className="text-sm text-slate-500">支持 PDF / Word / PPT / TXT / Markdown，最大 20MB。扫描件将尝试 OCR。</p>
        <input
          type="file"
          accept=".pdf,.docx,.pptx,.txt,.md"
          className="w-full max-w-full text-sm"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
        />
        <input
          className="input"
          value={title}
          onChange={(e) => {
            titleTouchedRef.current = true;
            setTitle(e.target.value);
          }}
          placeholder="题库标题"
        />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <select className="input" value={subject} onChange={(e) => setSubject(e.target.value)}>
            <option value="auto">自动识别科目</option>
            <option value="exam_civil">考公 / 文科</option>
            <option value="exam_grad">考研</option>
            <option value="history">历史</option>
            <option value="it">IT / 编程</option>
            <option value="math">数理</option>
            <option value="logic">逻辑</option>
          </select>
          <select className="input" value={category} onChange={(e) => setCategory(e.target.value)}>
            {["自定义", "常识", "考公", "考研", "IT", "历史"].map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </div>
        <label className="text-sm text-slate-600">
          题目数量 {total}
          <input type="range" min={4} max={20} value={total} onChange={(e) => setTotal(Number(e.target.value))} className="w-full" />
        </label>
        <select className="input" value={visibility} onChange={(e) => setVisibility(e.target.value)}>
          <option value="private">私密</option>
          <option value="public">公开到广场</option>
        </select>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} />
          强制重新出题（忽略相似文档复用）
        </label>
        {err && <p className="text-sm text-red-600">{err}</p>}
        <button className="btn-primary" disabled={!file || busy} onClick={start}>
          {busy ? "提交中…" : "开始生成"}
        </button>
      </div>
      <div className="card p-4 sm:p-6">
        <h2 className="font-medium">流水线进度</h2>
        {!job && <p className="mt-4 text-sm text-slate-500">提交后将依次展示：解析 → 篇章映射 → 出题 → 干扰项过滤 → 质量门控。</p>}
        {job && (
          <div className="mt-4 space-y-3">
            <div className="h-2 overflow-hidden rounded-full bg-slate-100">
              <div className="h-full bg-brand-600" style={{ width: `${job.progress}%` }} />
            </div>
            <p className="text-sm">
              {job.stage} · {job.progress}%
            </p>
            {job.models_used && (
              <p className="text-xs text-slate-500">
                出题 {job.models_used.generator} / 干扰项 {job.models_used.critic} / 科目 {job.models_used.subject}
              </p>
            )}
            {job.status === "failed" && <p className="text-sm text-red-600">{job.error}</p>}
          </div>
        )}
      </div>
      {dupPrompt && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/40 p-0 sm:items-center sm:p-4"
          onClick={() => !busy && setDupPrompt(null)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="dup-title"
            className="card w-full max-w-md rounded-t-2xl p-5 sm:rounded-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="dup-title" className="text-lg font-semibold">
              题库名称已存在
            </h2>
            <p className="mt-2 text-sm text-slate-600">
              「{dupPrompt.requested}」已有同名题库。若仍使用该名称，将自动保存为「{dupPrompt.resolved}」。
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" className="btn-ghost" disabled={busy} onClick={() => setDupPrompt(null)}>
                取消
              </button>
              <button type="button" className="btn-primary" disabled={busy} onClick={confirmDuplicate}>
                继续生成
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
