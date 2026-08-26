"use client";

import { Star } from "lucide-react";

type Props = {
  favorited: boolean;
  onToggle: () => void;
  className?: string;
};

/** Rounded-rect star toggle: hollow when off, solid amber when on. */
export function FavoriteButton({ favorited, onToggle, className = "" }: Props) {
  return (
    <button
      type="button"
      className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white transition hover:bg-slate-50 active:bg-slate-100 ${className}`}
      aria-label={favorited ? "取消收藏" : "收藏"}
      aria-pressed={favorited}
      onClick={onToggle}
    >
      <Star
        className={`h-4 w-4 ${favorited ? "fill-amber-400 text-amber-400" : "fill-none text-slate-400"}`}
        strokeWidth={1.75}
      />
    </button>
  );
}
