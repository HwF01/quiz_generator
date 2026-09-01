"use client";

import { useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import {
  StartPracticeDialog,
  practiceHref,
  type PracticeMode,
} from "@/components/StartPracticeDialog";

type Props = {
  quizId: string;
  className?: string;
  disabled?: boolean;
  children: ReactNode;
};

export function StartPracticeButton({
  quizId,
  className = "btn-primary",
  disabled = false,
  children,
}: Props) {
  const router = useRouter();
  const [open, setOpen] = useState(false);

  function start(mode: PracticeMode) {
    setOpen(false);
    router.push(practiceHref(quizId, mode));
  }

  if (disabled) {
    return (
      <span className={`${className} pointer-events-none opacity-50`} aria-disabled="true">
        {children}
      </span>
    );
  }

  return (
    <>
      <button type="button" className={className} onClick={() => setOpen(true)}>
        {children}
      </button>
      <StartPracticeDialog open={open} onCancel={() => setOpen(false)} onConfirm={start} />
    </>
  );
}
