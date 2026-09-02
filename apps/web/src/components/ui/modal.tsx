"use client";

import { useEffect, type ReactNode } from "react";

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
  maxWidth?: "sm" | "md" | "lg" | "xl" | "2xl";
}

export function Modal({
  open,
  onClose,
  title,
  subtitle,
  children,
  footer,
  maxWidth = "lg",
}: ModalProps) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && open) {
        onClose();
      }
    };
    if (open) {
      document.body.style.overflow = "hidden";
      window.addEventListener("keydown", handleKeyDown);
    }
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      aria-modal="true"
      className="modalOverlay"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
    >
      <div className={`modalDialog max-w-${maxWidth}`}>
        <div className="modalHeader">
          <div>
            <h3 className="modalTitle">{title}</h3>
            {subtitle && <p className="modalSubtitle">{subtitle}</p>}
          </div>
          <button
            aria-label="Tutup"
            className="modalClose"
            onClick={onClose}
            type="button"
          >
            ✕
          </button>
        </div>

        <div className="modalBody">{children}</div>

        {footer && <div className="modalFooter">{footer}</div>}
      </div>
    </div>
  );
}
