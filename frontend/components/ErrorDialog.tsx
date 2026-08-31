"use client";

import { useEffect } from "react";

type Props = {
  open: boolean;
  title?: string;
  description: string;
  confirmLabel?: string;
  onClose: () => void;
};

export function ErrorDialog({
  open,
  title = "操作失败",
  description,
  confirmLabel = "知道了",
  onClose,
}: Props) {
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/40 p-0 sm:items-center sm:p-4"
      onClick={onClose}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="error-title"
        aria-describedby="error-description"
        className="card w-full max-w-md rounded-t-2xl p-5 sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="error-title" className="text-lg font-semibold">
          {title}
        </h2>
        <p id="error-description" className="mt-2 text-sm text-slate-600">
          {description}
        </p>
        <div className="mt-5 flex justify-end">
          <button type="button" className="btn-primary" onClick={onClose}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
