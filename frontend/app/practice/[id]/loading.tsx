import { CardSkeleton } from "@/components/ListSkeleton";

export default function PracticeLoading() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">练习</h1>
      <CardSkeleton lines={6} />
    </div>
  );
}
