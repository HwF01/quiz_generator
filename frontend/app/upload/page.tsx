"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";

type Job = {
  id: string;
  status: string;
  progress: number;
  stage: string;
  error?: string;
  quiz_set_id?: string;
  models_used?: Record<string, string>;
};

export default function UploadPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("未命名题库");
  const [subject, setSubject] = useState("auto");
  const [category, setCategory] = useState("自定义");
  const [total, setTotal] = useState(8);
  const [visibility, setVisibility] = useState("private");
  const [job, setJob] = useState<Job | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [force, setForce] = useState(false);

  useEffect(() => {
    if (!getToken()) router.push("/login");
  }, [router]);

  useEffect(() => {
    if (!job || job.status === "succeeded" || job.status === "failed") return;
    const t = setInterval(async () => {
      const next = await api<Job>(`/jobs/${job.id}`);
      setJob(next);
      if (next.status === "succeeded" && next.quiz_set_id) {
        router.push(`/quizzes/${next.quiz_set_id}`);
      }
    }, 1500);
    return () => clearInterval(t);
  }, [job, router]);

  async function start() {
    if (!file) return;
    setErr("");
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const doc = await api<{ id: string }>("/documents/upload", { method: "POST", body: fd });
      const gen = await api<{ job_id: string; quiz_id: string }>("/quizzes/generate", {
        method: "POST",
        body: JSON.stringify({
          document_id: doc.id,
          title,
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
        <p className="text-sm text-slate-500">支持 PDF / Word / PPT，最大 20MB。扫描件将尝试 OCR。</p>
        <input
          type="file"
          accept=".pdf,.docx,.pptx,.txt,.md"
          className="w-full max-w-full text-sm"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
        />
        <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="题库标题" />
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
    </div>
  );
}
