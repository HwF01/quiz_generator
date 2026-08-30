import { ListSkeleton } from "@/components/ListSkeleton";

export default function PlazaLoading() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">社区广场</h1>
        <p className="text-sm text-slate-500">公开题库与系统预置题库，可收藏、评分、复制练习。</p>
      </div>
      <ListSkeleton label="正在加载广场题库" />
    </div>
  );
}
