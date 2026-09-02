"use client";

import type {
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";

export interface FormFieldProps {
  label: string;
  error?: string | null;
  helper?: string;
  required?: boolean;
  children: ReactNode;
  className?: string;
}

export function FormField({
  label,
  error,
  helper,
  required,
  children,
  className = "",
}: FormFieldProps) {
  return (
    <div className={`formGroup ${className}`} style={{ display: "grid", gap: "5px", marginBottom: "12px" }}>
      <label style={{ fontSize: "11px", fontWeight: 750, color: "#385248", display: "flex", gap: "4px" }}>
        <span>{label}</span>
        {required && <span style={{ color: "#b7443d" }}>*</span>}
      </label>

      {children}

      {error && <span className="formError" style={{ marginTop: "4px" }}>{error}</span>}
      {helper && !error && (
        <span style={{ fontSize: "10px", color: "var(--muted)", marginTop: "2px" }}>
          {helper}
        </span>
      )}
    </div>
  );
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} />;
}

export function TextAreaInput(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea rows={props.rows || 3} {...props} />;
}

export function SelectInput(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} />;
}
