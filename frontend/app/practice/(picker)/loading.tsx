import { ListSkeleton } from "@/components/ListSkeleton";

export default function PracticeIndexLoading() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">点击刷题</h1>
        <p className="text-sm text-slate-500">正在加载可刷题库。</p>
      </div>
      <ListSkeleton cards={3} label="正在加载可刷题库" />
    </div>
  );
}
