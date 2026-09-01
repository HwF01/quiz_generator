"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, getToken } from "@/lib/api";
import { FavoriteButton } from "@/components/FavoriteButton";
import { ListSkeleton } from "@/components/ListSkeleton";
import { StartPracticeButton } from "@/components/StartPracticeButton";

type Item = {
  id: string;
  title: string;
  description?: string;
  category: string;
  question_count: number;
  likes: number;
  plays: number;
  is_builtin: boolean;
  avg_rating: number;
  favorited: boolean;
};

type PlazaPage = {
  items: Item[];
  total: number;
  page: number;
  page_size: number;
};

type CategoryRow = {
  category: string;
  count: number;
};

const PAGE_SIZE = 20;

export default function PlazaPage() {
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [sort, setSort] = useState("hot");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [categories, setCategories] = useState<CategoryRow[]>([]);

  async function load(opts?: { silent?: boolean; page?: number }) {
    const currentPage = opts?.page ?? page;
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (category) params.set("category", category);
    params.set("sort", sort);
    params.set("page", String(currentPage));
    params.set("page_size", String(PAGE_SIZE));
    if (!opts?.silent) setLoading(true);
    try {
      const data = await api<PlazaPage>(`/plaza?${params.toString()}`);
      setItems(data.items);
      setTotal(data.total);
      setLoaded(true);
    } finally {
      if (!opts?.silent) setLoading(false);
    }
  }

  useEffect(() => {
    void api<CategoryRow[]>("/plaza/categories")
      .then((rows) => setCategories(rows.filter((row) => row.category)))
      .catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    void load();
  }, [category, sort, page]);

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  function goToPage(next: number) {
    setPage(Math.min(pageCount, Math.max(1, next)));
  }

  function resetToFirstPage() {
    if (page === 1) {
      void load({ page: 1 });
      return;
    }
    setPage(1);
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-semibold">社区广场</h1>
          <p className="text-sm text-slate-500">公开题库与系统预置题库，可收藏、评分、复制练习。</p>
        </div>
        <input
          className="input w-full sm:max-w-xs"
          placeholder="搜索标题"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && resetToFirstPage()}
        />
        <button type="button" className="btn-ghost" onClick={() => resetToFirstPage()}>
          搜索
        </button>
        <select
          className="input w-full sm:w-auto"
          value={category}
          onChange={(e) => {
            setCategory(e.target.value);
            setPage(1);
          }}
        >
          <option value="">全部分类</option>
          {categories.map((row) => (
            <option key={row.category} value={row.category}>
              {row.category}（{row.count}）
            </option>
          ))}
        </select>
        <select
          className="input w-full sm:w-auto"
          value={sort}
          onChange={(e) => {
            setSort(e.target.value);
            setPage(1);
          }}
        >
          <option value="hot">热门</option>
          <option value="new">最新</option>
        </select>
      </div>
      {loading ? (
        <ListSkeleton label="正在加载广场题库" />
      ) : (
      <div className="grid gap-4 md:grid-cols-2">
        {items.map((it) => (
          <div key={it.id} className="card p-5">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <Link href={`/quizzes/${it.id}`} className="break-words font-medium hover:text-brand-700">
                  {it.title}
                </Link>
                <p className="mt-1 text-sm text-slate-500">{it.description}</p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {it.is_builtin && <span className="badge">内置</span>}
                {getToken() && (
                  <FavoriteButton
                    favorited={it.favorited}
                    onToggle={() => {
                      void api(`/quizzes/${it.id}/favorite`, { method: "POST" }).then(() =>
                        load({ silent: true })
                      );
                    }}
                  />
                )}
              </div>
            </div>
            <p className="mt-3 text-xs text-slate-500">
              {it.category} · {it.question_count} 题 · {it.plays} 次练习 · {it.likes} 收藏 · {it.avg_rating.toFixed(1)} 分
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <StartPracticeButton quizId={it.id}>刷题</StartPracticeButton>
              <Link className="btn-ghost" href={`/quizzes/${it.id}`}>
                查看
              </Link>
            </div>
          </div>
        ))}
        {loaded && items.length === 0 && (
          <p className="text-sm text-slate-500 md:col-span-2">没有符合条件的公开题库。换个关键词，或去上传一份文档出题。</p>
        )}
      </div>
      )}
      {loaded && total > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-slate-500">
            第 {page} / {pageCount} 页，共 {total} 套题库
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              className="btn-ghost"
              disabled={page <= 1}
              onClick={() => goToPage(page - 1)}
            >
              上一页
            </button>
            <button
              type="button"
              className="btn-ghost"
              disabled={page >= pageCount}
              onClick={() => goToPage(page + 1)}
            >
              下一页
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
