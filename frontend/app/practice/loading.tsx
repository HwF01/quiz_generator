import { ListSkeleton } from "@/components/ListSkeleton";

export default function PracticePickLoading() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">点击刷题</h1>
        <p className="text-sm text-slate-500">正在加载可练习题库。</p>
      </div>
      <ListSkeleton cards={4} label="正在加载可练习题库" />
    </div>
  );
}
