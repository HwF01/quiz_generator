import { CardSkeleton } from "@/components/ListSkeleton";

export default function UploadLoading() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">上传出题</h1>
      <p className="text-sm text-slate-500">正在打开出题页。</p>
      <CardSkeleton lines={5} />
    </div>
  );
}
