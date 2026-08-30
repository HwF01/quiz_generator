import { ListSkeleton } from "@/components/ListSkeleton";

export default function ProfileLoading() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">我的题库</h1>
        <p className="text-sm text-slate-500">正在加载你的题库与练习记录。</p>
      </div>
      <ListSkeleton cards={2} label="正在加载我的题库" />
    </div>
  );
}
