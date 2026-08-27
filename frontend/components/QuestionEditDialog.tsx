"use client";

import { useEffect, useMemo, useState } from "react";

export type EditableQuestion = {
  id: string;
  type: string;
  content: string;
  options: { key: string; text: string }[] | null;
  answer: { keys?: string[]; texts?: string[] };
  explanation?: string;
};

export type QuestionPatch = {
  content: string;
  options: { key: string; text: string }[] | null;
  answer: { keys?: string[]; texts?: string[] };
  explanation: string;
};

type Props = {
  question: EditableQuestion;
  busy?: boolean;
  error?: string;
  onClose: () => void;
  onSave: (patch: QuestionPatch) => void;
};

type OptionDraft = { key: string; text: string };

function nextOptionKey(keys: string[]): string {
  const used = new Set(keys);
  for (let i = 0; i < 26; i += 1) {
    const letter = String.fromCharCode(65 + i);
    if (!used.has(letter)) return letter;
  }
  return `O${keys.length + 1}`;
}

function typeLabel(type: string): string {
  if (type === "single_choice") return "单选";
  if (type === "multi_choice") return "多选";
  if (type === "true_false") return "判断";
  if (type === "fill_blank") return "填空";
  return type;
}

export function QuestionEditDialog({ question, busy, error, onClose, onSave }: Props) {
  const choiceLike = question.type === "single_choice" || question.type === "multi_choice";
  const isTf = question.type === "true_false";
  const isBlank = question.type === "fill_blank";
  const [content, setContent] = useState(question.content);
  const [options, setOptions] = useState<OptionDraft[]>(() => {
    const src = (question.options ?? []).map((o) => ({ key: o.key, text: o.text }));
    if (src.length > 0) return src;
    if (question.type === "true_false") return [{ key: "对", text: "对" }, { key: "错", text: "错" }];
    if (question.type === "single_choice" || question.type === "multi_choice") {
      return [
        { key: "A", text: "" },
        { key: "B", text: "" },
        { key: "C", text: "" },
        { key: "D", text: "" },
      ];
    }
    return src;
  });
  const [answerKeys, setAnswerKeys] = useState<string[]>(() => [...(question.answer?.keys ?? [])]);
  const [answerTexts, setAnswerTexts] = useState(() => (question.answer?.texts ?? []).join("\n"));
  const [explanation, setExplanation] = useState(question.explanation ?? "");
  const [localError, setLocalError] = useState("");

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !busy) onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  const canRemoveOption = choiceLike && options.length > 2;

  const previewKeys = useMemo(() => options.map((o) => o.key), [options]);

  function setOptionText(key: string, text: string) {
    setOptions((prev) => prev.map((o) => (o.key === key ? { ...o, text } : o)));
  }

  function addOption() {
    const key = nextOptionKey(options.map((o) => o.key));
    setOptions((prev) => [...prev, { key, text: "" }]);
  }

  function removeOption(key: string) {
    setOptions((prev) => prev.filter((o) => o.key !== key));
    setAnswerKeys((prev) => prev.filter((k) => k !== key));
  }

  function pickSingle(key: string) {
    setAnswerKeys([key]);
  }

  function toggleMulti(key: string) {
    setAnswerKeys((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));
  }

  function submit() {
    const stem = content.trim();
    if (!stem) {
      setLocalError("题干不能为空");
      return;
    }
    if (isBlank) {
      const texts = answerTexts
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean);
      if (texts.length === 0) {
        setLocalError("请至少填写一个可接受答案");
        return;
      }
      setLocalError("");
      onSave({ content: stem, options: null, answer: { texts }, explanation: explanation.trim() });
      return;
    }
    const cleaned = options.map((o) => ({ key: o.key, text: o.text.trim() }));
    if (cleaned.some((o) => !o.text)) {
      setLocalError("选项内容不能为空");
      return;
    }
    const validKeys = new Set(cleaned.map((o) => o.key));
    const keys = answerKeys.filter((k) => validKeys.has(k));
    if (keys.length === 0) {
      setLocalError("请选择正确答案");
      return;
    }
    if (question.type === "single_choice" && keys.length !== 1) {
      setLocalError("单选题只能有一个正解");
      return;
    }
    const texts = cleaned.filter((o) => keys.includes(o.key)).map((o) => o.text);
    setLocalError("");
    onSave({
      content: stem,
      options: cleaned,
      answer: { keys, texts },
      explanation: explanation.trim(),
    });
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/40 p-0 sm:items-center sm:p-4"
      onClick={() => {
        if (!busy) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="question-edit-title"
        className="card flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-t-2xl sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="border-b border-slate-100 px-5 py-4">
          <h2 id="question-edit-title" className="text-lg font-semibold">
            手动修改
          </h2>
          <p className="mt-0.5 text-sm text-slate-500">题型：{typeLabel(question.type)}</p>
        </div>
        <div className="space-y-4 overflow-y-auto px-5 py-4">
          <label className="block space-y-1.5">
            <span className="text-sm font-medium text-slate-700">题干</span>
            <textarea
              className="input min-h-[96px]"
              value={content}
              onChange={(e) => setContent(e.target.value)}
            />
          </label>

          {isBlank ? (
            <label className="block space-y-1.5">
              <span className="text-sm font-medium text-slate-700">正确答案</span>
              <textarea
                className="input min-h-[72px]"
                value={answerTexts}
                onChange={(e) => setAnswerTexts(e.target.value)}
                placeholder="每行一个可接受答案"
              />
            </label>
          ) : (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-slate-700">
                  {isTf ? "选项与正解" : "选项（勾选正解）"}
                </span>
                {choiceLike && (
                  <button type="button" className="btn-ghost h-9 px-3 py-1 text-xs" onClick={addOption}>
                    添加选项
                  </button>
                )}
              </div>
              <ul className="space-y-2">
                {options.map((o) => (
                  <li key={o.key} className="flex items-start gap-2">
                    <label className="mt-2.5 flex shrink-0 items-center gap-1.5 text-sm">
                      <input
                        type={question.type === "multi_choice" ? "checkbox" : "radio"}
                        name="question-edit-answer"
                        checked={answerKeys.includes(o.key)}
                        onChange={() =>
                          question.type === "multi_choice" ? toggleMulti(o.key) : pickSingle(o.key)
                        }
                      />
                      <span className="w-5 font-semibold">{isTf ? "" : o.key}</span>
                    </label>
                    {isTf ? (
                      <p className="input bg-slate-50">{o.text || o.key}</p>
                    ) : (
                      <input
                        className="input"
                        value={o.text}
                        onChange={(e) => setOptionText(o.key, e.target.value)}
                      />
                    )}
                    {canRemoveOption && (
                      <button
                        type="button"
                        className="btn-ghost h-11 shrink-0 px-3 text-red-600"
                        onClick={() => removeOption(o.key)}
                      >
                        删
                      </button>
                    )}
                  </li>
                ))}
              </ul>
              {choiceLike && previewKeys.length === 0 && (
                <p className="text-sm text-slate-500">暂无选项，请先添加。</p>
              )}
            </div>
          )}

          <label className="block space-y-1.5">
            <span className="text-sm font-medium text-slate-700">解析</span>
            <textarea
              className="input min-h-[72px]"
              value={explanation}
              onChange={(e) => setExplanation(e.target.value)}
            />
          </label>

          {(localError || error) && <p className="text-sm text-red-600">{localError || error}</p>}
        </div>
        <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-3">
          <button type="button" className="btn-ghost" disabled={busy} onClick={onClose}>
            取消
          </button>
          <button type="button" className="btn-primary" disabled={busy} onClick={submit}>
            {busy ? "保存中…" : "保存"}
          </button>
        </div>
      </div>
    </div>
  );
}
