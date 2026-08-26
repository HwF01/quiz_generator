"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { BookOpen, Menu, X } from "lucide-react";
import { clearToken, getToken } from "@/lib/api";
import { useEffect, useState } from "react";

const links = [
  { href: "/upload", label: "上传出题" },
  { href: "/plaza", label: "社区广场" },
  { href: "/profile", label: "我的题库" },
  { href: "/wrong", label: "错题本" },
  { href: "/favorites", label: "收藏" },
];

export function Nav() {
  const path = usePathname();
  const router = useRouter();
  const [authed, setAuthed] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => setAuthed(Boolean(getToken())), [path]);
  useEffect(() => setOpen(false), [path]);

  function logout() {
    clearToken();
    setOpen(false);
    router.push("/login");
  }

  const linkClass = (href: string) =>
    path.startsWith(href) ? "text-brand-700 font-medium" : "text-slate-600 hover:text-slate-900 active:text-slate-900";

  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 pt-[env(safe-area-inset-top)] backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-3 px-4">
        <Link href="/" className="flex min-w-0 items-center gap-2 font-semibold">
          <BookOpen className="h-5 w-5 shrink-0 text-brand-600" />
          <span className="truncate">智能题库生成器</span>
        </Link>
        <nav className="hidden items-center gap-4 text-sm md:flex">
          {links.map((l) => (
            <Link key={l.href} href={l.href} className={linkClass(l.href)}>
              {l.label}
            </Link>
          ))}
          {authed ? (
            <button type="button" className="text-slate-500 hover:text-slate-900" onClick={logout}>
              退出登录
            </button>
          ) : (
            <Link href="/login" className="text-brand-700">
              登录
            </Link>
          )}
        </nav>
        <button
          type="button"
          className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-slate-700 md:hidden"
          aria-label={open ? "关闭菜单" : "打开菜单"}
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>
      {open && (
        <nav className="border-t border-slate-200 bg-white px-4 py-2 md:hidden">
          <div className="mx-auto flex max-w-6xl flex-col">
            {links.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                className={`flex min-h-11 items-center rounded-xl px-3 text-sm ${linkClass(l.href)}`}
              >
                {l.label}
              </Link>
            ))}
            {authed ? (
              <button
                type="button"
                className="flex min-h-11 items-center rounded-xl px-3 text-left text-sm text-slate-500"
                onClick={logout}
              >
                退出登录
              </button>
            ) : (
              <Link href="/login" className="flex min-h-11 items-center rounded-xl px-3 text-sm text-brand-700">
                登录
              </Link>
            )}
          </div>
        </nav>
      )}
    </header>
  );
}
