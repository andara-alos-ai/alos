"use client";

import {
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode,
} from "react";

export type ToastType = "success" | "error" | "warning" | "info";

export interface ToastItem {
  id: string;
  message: string;
  type: ToastType;
  duration?: number;
}

interface ToastContextValue {
  showToast: (message: string, type?: ToastType, duration?: number) => void;
  success: (message: string) => void;
  error: (message: string) => void;
  warning: (message: string) => void;
  info: (message: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showToast = useCallback(
    (message: string, type: ToastType = "info", duration = 4000) => {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      setToasts((prev) => [...prev, { id, message, type, duration }]);
      if (duration > 0) {
        setTimeout(() => removeToast(id), duration);
      }
    },
    [removeToast],
  );

  const success = useCallback((msg: string) => showToast(msg, "success"), [showToast]);
  const error = useCallback((msg: string) => showToast(msg, "error", 6000), [showToast]);
  const warning = useCallback((msg: string) => showToast(msg, "warning", 5000), [showToast]);
  const info = useCallback((msg: string) => showToast(msg, "info"), [showToast]);

  const typeIcons: Record<ToastType, string> = {
    success: "✓",
    error: "✕",
    warning: "⚠",
    info: "ℹ",
  };

  const typeClasses: Record<ToastType, string> = {
    success: "toastSuccess",
    error: "toastError",
    warning: "toastWarning",
    info: "toastInfo",
  };

  return (
    <ToastContext.Provider value={{ showToast, success, error, warning, info }}>
      {children}
      {toasts.length > 0 && (
        <div aria-live="polite" className="toastContainer">
          {toasts.map((t) => (
            <div
              className={`toastItem ${typeClasses[t.type]}`}
              key={t.id}
              onClick={() => removeToast(t.id)}
              role="alert"
              style={{ cursor: "pointer" }}
            >
              <span style={{ fontSize: "14px", fontWeight: "bold" }}>{typeIcons[t.type]}</span>
              <span style={{ flex: 1, lineHeight: "1.4" }}>{t.message}</span>
            </div>
          ))}
        </div>
      )}
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast harus digunakan di dalam <ToastProvider>");
  }
  return context;
}
