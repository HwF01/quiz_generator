"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, setToken } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    try {
      const data = await api<{ token: string }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setToken(data.token);
      router.push("/profile");
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "登录失败");
    }
  }

  return (
    <form onSubmit={onSubmit} className="card mx-auto max-w-md space-y-4 p-8">
      <h1 className="text-xl font-semibold">登录</h1>
      <input className="input" placeholder="邮箱" value={email} onChange={(e) => setEmail(e.target.value)} />
      <input className="input" type="password" placeholder="密码" value={password} onChange={(e) => setPassword(e.target.value)} />
      {err && <p className="text-sm text-red-600">{err}</p>}
      <button className="btn-primary w-full">登录</button>
      <p className="text-sm text-slate-500">
        没有账号？ <Link href="/register" className="text-brand-700">注册</Link>
      </p>
    </form>
  );
}
