"use client";

import { useEffect, useRef } from "react";

export function ConfirmDialog({
  open,
  title,
  body,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  body: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal?.();
    if (!open && d.open) d.close?.();
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-label={title || "Confirm action"}
      onCancel={(e) => {
        e.preventDefault();
        onCancel();
      }}
      className="m-auto w-[min(28rem,calc(100vw-2rem))] rounded-lg border border-[var(--line)] bg-[var(--panel)] p-5 text-[var(--fg)] backdrop:bg-black/40"
    >
      {open && (
        <>
          <h2 id="confirm-title" className="text-lg font-semibold">
            {title}
          </h2>
          <p className="mt-2 text-sm">{body}</p>
          <p className="mt-2 text-xs text-[var(--muted)]">Demo only: nothing happens to a real account.</p>
          <div className="mt-4 flex justify-end gap-2">
            <button type="button" className="btn-secondary" onClick={onCancel}>
              No, cancel
            </button>
            <button type="button" className="btn-primary" onClick={onConfirm}>
              Yes, go ahead
            </button>
          </div>
        </>
      )}
    </dialog>
  );
}
