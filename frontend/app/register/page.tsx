"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, setToken } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [nickname, setNickname] = useState("");
  const [err, setErr] = useState("");

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    try {
      const data = await api<{ token: string }>("/auth/register", {
        method: "POST",
        body: JSON.stringify({ email, password, nickname }),
      });
      setToken(data.token);
      router.push("/upload");
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "注册失败");
    }
  }

  return (
    <form onSubmit={onSubmit} className="card mx-auto max-w-md space-y-4 p-8">
      <h1 className="text-xl font-semibold">注册</h1>
      <input className="input" placeholder="昵称" value={nickname} onChange={(e) => setNickname(e.target.value)} />
      <input className="input" placeholder="邮箱" value={email} onChange={(e) => setEmail(e.target.value)} />
      <input className="input" type="password" placeholder="密码至少 8 位" value={password} onChange={(e) => setPassword(e.target.value)} minLength={8} />
      {err && <p className="text-sm text-red-600">{err}</p>}
      <button className="btn-primary w-full">创建账号</button>
      <p className="text-sm text-slate-500">
        已有账号？ <Link href="/login" className="text-brand-700">登录</Link>
      </p>
    </form>
  );
}
