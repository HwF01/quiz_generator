import { ListSkeleton } from "@/components/ListSkeleton";

export default function WrongLoading() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">错题本</h1>
      <ListSkeleton columns={false} cards={3} label="正在加载错题本" />
    </div>
  );
}
