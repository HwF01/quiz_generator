"use client";

import { FormEvent, Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { api, setToken } from "@/lib/api";
import { ErrorDialog } from "@/components/ErrorDialog";
import { safeNextPath } from "@/lib/labels";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErr("");
    try {
      const data = await api<{ token: string }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setToken(data.token);
      router.push(safeNextPath(searchParams.get("next")));
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "登录失败");
    }
  }

  return (
    <>
    <form onSubmit={onSubmit} className="card mx-auto max-w-md space-y-4 p-6 sm:p-8">
      <h1 className="text-xl font-semibold">登录</h1>
      <label className="block space-y-1.5">
        <span className="text-sm font-medium text-slate-700">邮箱</span>
        <input
          className="input"
          type="email"
          inputMode="email"
          autoComplete="email"
          placeholder="邮箱地址"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </label>
      <label className="block space-y-1.5">
        <span className="text-sm font-medium text-slate-700">密码</span>
        <input
          className="input"
          type="password"
          autoComplete="current-password"
          placeholder="请输入密码"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </label>
      <button className="btn-primary w-full">登录</button>
      <p className="text-sm text-slate-500">
        没有账号？ <Link href="/register" className="text-brand-700">注册</Link>
      </p>
    </form>
    <ErrorDialog open={Boolean(err)} description={err} onClose={() => setErr("")} />
    </>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<p className="text-sm text-slate-500">加载中…</p>}>
      <LoginForm />
    </Suspense>
  );
}
