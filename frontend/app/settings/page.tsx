"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import { ErrorDialog } from "@/components/ErrorDialog";
import type { SetupStatus } from "@/lib/labels";

export default function SettingsPage() {
  const router = useRouter();
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [qwen, setQwen] = useState("");
  const [deepseek, setDeepseek] = useState("");
  const [tavily, setTavily] = useState("");
  const [useDemo, setUseDemo] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    const data = await api<SetupStatus>("/setup");
    setStatus(data);
    setUseDemo(data.llm_mode === "mock");
  }

  useEffect(() => {
    if (!getToken()) {
      router.push("/login?next=/settings");
      return;
    }
    load().catch((e) => setErr(e instanceof Error ? e.message : "加载配置失败"));
  }, [router]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!status?.editable) return;
    setActionError("");
    setMsg("");
    setBusy(true);
    try {
      const next = await api<SetupStatus>("/setup", {
        method: "PUT",
        body: JSON.stringify({
          qwen_api_key: qwen.trim() || undefined,
          deepseek_api_key: deepseek.trim() || undefined,
          tavily_api_key: tavily.trim() || undefined,
          use_demo: useDemo,
        }),
      });
      setStatus(next);
      setQwen("");
      setDeepseek("");
      setTavily("");
      setUseDemo(next.llm_mode === "mock");
      setMsg("已保存。新配置立即生效，无需重启。");
    } catch (ex) {
      setActionError(ex instanceof Error ? ex.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function clearTavily() {
    if (!status?.editable) return;
    setActionError("");
    setMsg("");
    setBusy(true);
    try {
      const next = await api<SetupStatus>("/setup", {
        method: "PUT",
        body: JSON.stringify({ clear_tavily: true }),
      });
      setStatus(next);
      setTavily("");
      setMsg("已清除 Tavily Key，联网补充已关闭。");
    } catch (ex) {
      setActionError(ex instanceof Error ? ex.message : "清除失败");
    } finally {
      setBusy(false);
    }
  }

  if (!status && !err) return <p className="text-sm text-slate-500">加载中…</p>;

  const providers = [
    status?.qwen_configured ? "通义千问" : null,
    status?.deepseek_configured ? "DeepSeek" : null,
  ].filter(Boolean);

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">服务配置</h1>
        <p className="mt-1 text-sm text-slate-500">
          出题至少需要一把通义千问或 DeepSeek Key，两把都配时文科走通义、理科走 DeepSeek。Tavily 仅联网补充时需要，可留空。
        </p>
      </div>
      {status && (
        <section className="card space-y-2 p-4 sm:p-5">
          <h2 className="text-sm font-medium">当前状态</h2>
          <p className="text-sm text-slate-600">
            {status.llm_mode === "mock"
              ? "演示模式：不调用网络模型。"
              : `真实出题：已配置 ${providers.join("、") || "出题服务"}。`}
          </p>
          <p className="text-sm text-slate-600">
            {status.tavily_configured
              ? "联网补充已开启。"
              : "未填写 Tavily Key，不影响普通出题。"}
          </p>
        </section>
      )}
      {status && !status.editable && (
        <p className="rounded-xl bg-slate-100 px-3 py-2 text-sm text-slate-600">
          当前环境不能在页面里改密钥，请在服务器环境变量或 `.env` 中配置。
        </p>
      )}
      {status?.editable && (
        <form onSubmit={onSubmit} className="card space-y-4 p-4 sm:p-6">
          <label className="block space-y-1.5">
            <span className="text-sm font-medium text-slate-700">通义千问 API Key</span>
            <input
              className="input"
              type="password"
              autoComplete="off"
              value={qwen}
              onChange={(e) => setQwen(e.target.value)}
              placeholder={status.qwen_configured ? "已保存，留空则保留" : "选填，可与 DeepSeek 同时填写"}
            />
          </label>
          <label className="block space-y-1.5">
            <span className="text-sm font-medium text-slate-700">DeepSeek API Key</span>
            <input
              className="input"
              type="password"
              autoComplete="off"
              value={deepseek}
              onChange={(e) => setDeepseek(e.target.value)}
              placeholder={status.deepseek_configured ? "已保存，留空则保留" : "选填，可与通义千问同时填写"}
            />
          </label>
          <label className="block space-y-1.5">
            <span className="text-sm font-medium text-slate-700">Tavily API Key（选填）</span>
            <input
              className="input"
              type="password"
              autoComplete="off"
              value={tavily}
              onChange={(e) => setTavily(e.target.value)}
              placeholder={status.tavily_configured ? "已保存，留空则保留" : "仅「联网补充知识」需要"}
            />
          </label>
          {status.tavily_configured && (
            <button type="button" className="btn-ghost" disabled={busy} onClick={() => void clearTavily()}>
              清除 Tavily Key
            </button>
          )}
          <label className="flex items-start gap-2 text-sm text-slate-700">
            <input
              className="mt-1"
              type="checkbox"
              checked={useDemo}
              onChange={(e) => setUseDemo(e.target.checked)}
            />
            <span>
              改回演示模式
              <span className="mt-0.5 block text-xs text-slate-500">不调用网络模型；已保存的出题 Key 仍保留。</span>
            </span>
          </label>
          {msg && (
            <p className="text-sm text-emerald-700" role="status">
              {msg}
            </p>
          )}
          <button className="btn-primary" disabled={busy}>
            {busy ? "保存中…" : "保存"}
          </button>
        </form>
      )}
      {err && !status && <p className="text-sm text-red-600">{err}</p>}
      <ErrorDialog open={Boolean(actionError)} description={actionError} onClose={() => setActionError("")} />
    </div>
  );
}
