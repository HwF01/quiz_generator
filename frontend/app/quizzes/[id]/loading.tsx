import { ListSkeleton } from "@/components/ListSkeleton";

export default function QuizLoading() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">题库审校</h1>
      <ListSkeleton columns={false} cards={3} label="正在加载题库" />
    </div>
  );
}
