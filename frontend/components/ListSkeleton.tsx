function PulseBar({ className }: { className: string }) {
  return <div className={`rounded bg-slate-200 ${className}`} />;
}

export function CardSkeleton({ lines = 2 }: { lines?: number }) {
  return (
    <div className="card animate-pulse p-5" aria-hidden>
      <PulseBar className="h-4 w-2/3" />
      {Array.from({ length: lines }, (_, index) => (
        <PulseBar key={index} className={`mt-3 h-3 ${index === lines - 1 ? "w-3/5" : "w-full"}`} />
      ))}
    </div>
  );
}

export function ListSkeleton({
  cards = 4,
  columns = true,
  label = "加载中",
}: {
  cards?: number;
  columns?: boolean;
  label?: string;
}) {
  return (
    <div className="space-y-4" aria-busy="true" aria-live="polite" aria-label={label}>
      <div className={columns ? "grid gap-4 md:grid-cols-2" : "space-y-3"}>
        {Array.from({ length: cards }, (_, index) => (
          <CardSkeleton key={index} />
        ))}
      </div>
    </div>
  );
}
