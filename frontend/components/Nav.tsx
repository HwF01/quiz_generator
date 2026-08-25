"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { BookOpen } from "lucide-react";
import { clearToken, getToken } from "@/lib/api";
import { useEffect, useState } from "react";

const links = [
  { href: "/upload", label: "上传出题" },
  { href: "/plaza", label: "社区广场" },
  { href: "/profile", label: "我的题库" },
  { href: "/wrong", label: "错题本" },
];

export function Nav() {
  const path = usePathname();
  const router = useRouter();
  const [authed, setAuthed] = useState(false);
  useEffect(() => setAuthed(Boolean(getToken())), [path]);

  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <BookOpen className="h-5 w-5 text-brand-600" />
          智能题库生成器
        </Link>
        <nav className="flex items-center gap-4 text-sm">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={path.startsWith(l.href) ? "text-brand-700 font-medium" : "text-slate-600 hover:text-slate-900"}
            >
              {l.label}
            </Link>
          ))}
          {authed ? (
            <button
              className="text-slate-500"
              onClick={() => {
                clearToken();
                router.push("/login");
              }}
            >
              退出
            </button>
          ) : (
            <Link href="/login" className="text-brand-700">
              登录
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}
