import Link from "next/link";

export default function HomePage() {
  return (
    <div className="space-y-10">
      <section className="card p-6 sm:p-10">
        <p className="text-sm text-brand-700">AI 辅助低风险命题 · 练习草稿不是正式考卷</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">
          从讲义到强干扰项练习题
        </h1>
        <p className="mt-3 max-w-2xl text-slate-600">
          上传 PDF / Word / PPT，系统先做篇章映射与关键句抽取，再用 Qwen / Deepseek 出题干，
          Claude / GPT 过生成干扰项并经语义过滤。你始终可以审校、改题、再发布。
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link href="/upload" className="btn-primary">
            开始出题
          </Link>
          <Link href="/plaza" className="btn-ghost">
            逛广场
          </Link>
        </div>
      </section>
      <section className="grid gap-4 md:grid-cols-3">
        {[
          ["篇章映射", "不适切段落自动跳过，避免整书无脑切片出题。"],
          ["GCRDG 干扰项", "过生成 8–12 个候选，过滤与正解语义重叠的选项。"],
          ["质量门控", "答案存在性、单正确、微技能配额，待审校题目置顶。"],
        ].map(([t, d]) => (
          <div key={t} className="card p-5">
            <h3 className="font-medium">{t}</h3>
            <p className="mt-2 text-sm text-slate-600">{d}</p>
          </div>
        ))}
      </section>
    </div>
  );
}
