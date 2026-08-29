"use client";

import { useEffect, useMemo, useRef, useState } from "react";
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
  models_used?: Record<string, string | string[]>;
};

type AllocationMode = "auto" | "manual";
type TypeCounts = Record<string, number>;
type GenerationPreview = {
  subject: string;
  subject_tags: string[];
  available_question_types: string[];
  suggested_type_counts: TypeCounts;
  suitable_passages: number;
  capacity_hint: number;
  web_search_available: boolean;
};

const TYPE_LABELS: Record<string, string> = {
  single_choice: "单选题",
  true_false: "判断题",
  fill_blank: "填空题",
  application: "应用题",
  proof: "证明题",
  short_answer: "简答题",
};

const SUBJECT_TAG_LABELS: Record<string, string> = {
  humanities: "文科",
  science: "理科",
  engineering: "工科",
  it: "IT / 编程",
  math: "数理",
  logic: "逻辑",
};

function countTotal(counts: TypeCounts): number {
  return Object.values(counts).reduce((sum, count) => sum + count, 0);
}

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
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [preview, setPreview] = useState<GenerationPreview | null>(null);
  const [subjectTags, setSubjectTags] = useState<string[]>([]);
  const [allocationMode, setAllocationMode] = useState<AllocationMode>("auto");
  const [typeCounts, setTypeCounts] = useState<TypeCounts>({});
  const [targetDifficulty, setTargetDifficulty] = useState("");
  const [enableWebSearch, setEnableWebSearch] = useState(false);
  const [visibility, setVisibility] = useState("private");
  const [job, setJob] = useState<Job | null>(null);
  const [err, setErr] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [force, setForce] = useState(false);
  const [dupPrompt, setDupPrompt] = useState<{ requested: string; resolved: string } | null>(null);
  const titleTouchedRef = useRef(false);
  const titlesCacheRef = useRef<string[] | null>(null);
  const showDifficulty = subjectTags.some((tag) => ["it", "math", "logic"].includes(tag));
  const manualCountTotal = useMemo(() => countTotal(typeCounts), [typeCounts]);

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

  function blueprint(mode: AllocationMode = allocationMode) {
    return {
      total_questions: total,
      allocation_mode: mode,
      type_counts: typeCounts,
      max_detail_ratio: 0.3,
      target_grade: "通用",
      subject_tags: subjectTags,
      ...(showDifficulty && targetDifficulty ? { target_difficulty: targetDifficulty } : {}),
      enable_web_search: enableWebSearch,
    };
  }

  async function loadPreview(id: string, tags = subjectTags, subjectHint = subject) {
    const data = await api<GenerationPreview>(`/documents/${id}/generation-preview`, {
      method: "POST",
      body: JSON.stringify({
        subject: subjectHint,
        blueprint: { ...blueprint("auto"), subject_tags: tags },
      }),
    });
    setPreview(data);
    setSubjectTags(tags.length > 0 ? tags : data.subject_tags);
    if (allocationMode === "auto") setTypeCounts(data.suggested_type_counts);
    if (!data.web_search_available) setEnableWebSearch(false);
  }

  function updateSubjectTag(tag: string, checked: boolean) {
    const next = checked ? [...new Set([...subjectTags, tag])] : subjectTags.filter((item) => item !== tag);
    setSubjectTags(next);
    if (documentId) {
      void loadPreview(documentId, next).catch((e) =>
        setErr(e instanceof Error ? e.message : "更新题型建议失败")
      );
    }
  }

  function updateTypeCount(kind: string, value: string) {
    const count = Math.max(0, Math.floor(Number(value) || 0));
    setTypeCounts((current) => ({ ...current, [kind]: count }));
  }

  async function requestGenerate(id: string, finalTitle: string) {
    if (allocationMode === "manual" && manualCountTotal !== total) {
      setErr("各题型数量之和必须等于总题量");
      return;
    }
    const gen = await api<{ job_id: string; quiz_id: string }>("/quizzes/generate", {
      method: "POST",
      body: JSON.stringify({
        document_id: id,
        title: finalTitle,
        category,
        subject,
        visibility,
        blueprint: blueprint(),
        force,
      }),
    });
    setJob({ id: gen.job_id, status: "queued", progress: 0, stage: "排队中", quiz_set_id: gen.quiz_id });
  }

  async function submitGenerate(uploadFile: File, finalTitle: string) {
    if (documentId && preview) {
      await requestGenerate(documentId, finalTitle);
      return;
    }
    const doc = await uploadDocument(uploadFile);
    setDocumentId(doc.id);
    await loadPreview(doc.id);
    setNotice("已识别材料范围，请确认题型配额后开始生成。");
  }

  async function start() {
    if (!file) return;
    setErr("");
    setNotice("");
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

      const existingTitles = titlesCacheRef.current ?? (await titlesPromise);
      const finalTitle = autoTitle ? nextUnnamedTitle(existingTitles) : trimmed;
      if (!autoTitle && existingTitles.includes(finalTitle)) {
        setDupPrompt({ requested: trimmed, resolved: withDuplicateSuffix(trimmed, existingTitles) });
        return;
      }
      await submitGenerate(file, finalTitle);
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
    setNotice("");
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
        <label className="block space-y-1.5">
          <span className="text-sm font-medium text-slate-700">出题文件</span>
          <input
            type="file"
            accept=".pdf,.docx,.pptx,.txt,.md"
            className="w-full max-w-full text-sm"
            onChange={(e) => {
              setFile(e.target.files?.[0] || null);
              setDocumentId(null);
              setPreview(null);
              setSubjectTags([]);
              setTypeCounts({});
              setNotice("");
            }}
          />
        </label>
        <label className="block space-y-1.5">
          <span className="text-sm font-medium text-slate-700">题库标题</span>
          <input
            className="input"
            name="quiz-title"
            autoComplete="off"
            value={title}
            onChange={(e) => {
              titleTouchedRef.current = true;
              setTitle(e.target.value);
            }}
            placeholder="例如：高等数学第 1 章练习…"
          />
        </label>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="block space-y-1.5">
            <span className="text-sm font-medium text-slate-700">科目</span>
            <select
              className="input"
              name="subject"
              value={subject}
              onChange={(e) => {
                const next = e.target.value;
                setSubject(next);
                if (documentId) {
                  void loadPreview(documentId, subjectTags, next).catch((error) =>
                    setErr(error instanceof Error ? error.message : "更新科目识别失败")
                  );
                }
              }}
            >
              <option value="auto">自动识别科目</option>
              <option value="exam_civil">考公 / 文科</option>
              <option value="exam_grad">考研</option>
              <option value="history">历史</option>
              <option value="it">IT / 编程</option>
              <option value="math">数理</option>
              <option value="logic">逻辑</option>
            </select>
          </label>
          <label className="block space-y-1.5">
            <span className="text-sm font-medium text-slate-700">分类</span>
            <select className="input" name="category" value={category} onChange={(e) => setCategory(e.target.value)}>
              {["自定义", "常识", "考公", "考研", "IT", "历史"].map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
        </div>
        <label className="block space-y-1.5 text-sm text-slate-600">
          <span>目标题量（1–50）</span>
          <input
            className="input"
            type="number"
            name="total-questions"
            inputMode="numeric"
            min={1}
            max={50}
            step={1}
            value={total}
            onChange={(e) => setTotal(Math.min(50, Math.max(1, Math.floor(Number(e.target.value) || 1))))}
          />
        </label>
        {preview && (
          <section className="space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
            <div>
              <h2 className="text-sm font-semibold">材料识别与出题蓝图</h2>
              <p className="mt-1 text-xs text-slate-500">
                识别为 {preview.subject || "通用"}，发现 {preview.suitable_passages} 段适合出题的材料。实际题量以质量门控结果为准。
              </p>
            </div>
            <fieldset>
              <legend className="text-sm font-medium text-slate-700">学科标签（可修改）</legend>
              <div className="mt-2 flex flex-wrap gap-x-3 gap-y-2">
                {Object.entries(SUBJECT_TAG_LABELS).map(([tag, label]) => (
                  <label key={tag} className="flex items-center gap-1.5 text-sm text-slate-700">
                    <input
                      type="checkbox"
                      checked={subjectTags.includes(tag)}
                      onChange={(e) => updateSubjectTag(tag, e.target.checked)}
                    />
                    {label}
                  </label>
                ))}
              </div>
            </fieldset>
            <fieldset>
              <legend className="text-sm font-medium text-slate-700">题型分配</legend>
              <div className="mt-2 flex gap-4 text-sm">
                <label className="flex items-center gap-1.5">
                  <input
                    type="radio"
                    name="allocation-mode"
                    checked={allocationMode === "auto"}
                    onChange={() => {
                      setAllocationMode("auto");
                      setTypeCounts(preview.suggested_type_counts);
                    }}
                  />
                  自动分配
                </label>
                <label className="flex items-center gap-1.5">
                  <input
                    type="radio"
                    name="allocation-mode"
                    checked={allocationMode === "manual"}
                    onChange={() => setAllocationMode("manual")}
                  />
                  手动分配
                </label>
              </div>
              <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
                {preview.available_question_types.map((kind) => (
                  <label key={kind} className="flex items-center justify-between gap-3 text-sm">
                    <span>{TYPE_LABELS[kind] || kind}</span>
                    <input
                      className="input w-20"
                      type="number"
                      min={0}
                      max={50}
                      value={typeCounts[kind] ?? 0}
                      disabled={allocationMode === "auto"}
                      onChange={(e) => updateTypeCount(kind, e.target.value)}
                      aria-label={`${TYPE_LABELS[kind] || kind}数量`}
                    />
                  </label>
                ))}
              </div>
              <p className={`mt-2 text-xs ${allocationMode === "manual" && manualCountTotal !== total ? "text-red-600" : "text-slate-500"}`}>
                {allocationMode === "auto"
                  ? "系统将按材料适配度生成配额，可切换为手动分配调整。"
                  : `已分配 ${manualCountTotal} / ${total} 题`}
              </p>
            </fieldset>
            {showDifficulty && (
              <label className="block space-y-1.5">
                <span className="text-sm font-medium text-slate-700">目标难度</span>
                <select className="input" value={targetDifficulty} onChange={(e) => setTargetDifficulty(e.target.value)}>
                  <option value="">由系统按材料判断</option>
                  <option value="easy">基础</option>
                  <option value="medium">进阶</option>
                  <option value="hard">挑战</option>
                </select>
              </label>
            )}
            <label className="flex items-start gap-2 text-sm text-slate-700">
              <input
                className="mt-1"
                type="checkbox"
                checked={enableWebSearch}
                disabled={!preview.web_search_available}
                onChange={(e) => setEnableWebSearch(e.target.checked)}
              />
              <span>
                联网补充知识
                <span className="mt-0.5 block text-xs text-slate-500">
                  仅发送从材料提取的主题词，不上传原文；来源会在审校页和作答后展示。
                  {!preview.web_search_available && " 当前未配置检索服务。"}
                </span>
              </span>
            </label>
          </section>
        )}
        <label className="block space-y-1.5">
          <span className="text-sm font-medium text-slate-700">可见性</span>
          <select className="input" name="visibility" value={visibility} onChange={(e) => setVisibility(e.target.value)}>
            <option value="private">私密</option>
            <option value="public">公开到广场</option>
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} />
          强制重新出题（忽略相似文档复用）
        </label>
        {notice && <p className="text-sm text-emerald-700" role="status" aria-live="polite">{notice}</p>}
        {err && <p className="text-sm text-red-600" role="alert">{err}</p>}
        <button
          className="btn-primary"
          disabled={!file || busy || (allocationMode === "manual" && manualCountTotal !== total)}
          onClick={start}
        >
          {busy ? "提交中…" : documentId && preview ? "开始生成" : "解析并配置"}
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
              <div className="space-y-1 text-xs text-slate-500">
                <p>
                  出题 {job.models_used.generator} / 干扰项 {job.models_used.critic} / 科目 {job.models_used.subject}
                </p>
                {typeof job.models_used.shortfall_reason === "string" && <p>{job.models_used.shortfall_reason}</p>}
              </div>
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
