import { ListSkeleton } from "@/components/ListSkeleton";

export default function FavoritesLoading() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">收藏</h1>
      <ListSkeleton columns={false} cards={3} label="正在加载收藏" />
    </div>
  );
}
