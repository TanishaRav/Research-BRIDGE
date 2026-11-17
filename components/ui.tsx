import type { ButtonHTMLAttributes, ReactNode } from "react";
import Link from "next/link";
import { cn } from "@/lib/format";

type ButtonVariant = "primary" | "secondary" | "ghost" | "destructive";

const buttonBase =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-md px-4 text-sm font-semibold no-underline transition-colors disabled:cursor-not-allowed disabled:opacity-55";
const buttonVariants: Record<ButtonVariant, string> = {
  primary:
    "rb-on-accent border border-accent bg-accent hover:bg-accent-hover active:bg-accent-pressed",
  secondary:
    "border border-divider bg-surface text-ink hover:bg-subtle active:bg-divider",
  ghost: "border border-transparent bg-transparent text-ink hover:bg-subtle",
  destructive:
    "border border-error bg-surface text-error hover:bg-error-soft active:bg-error-soft",
};

export function Button({
  variant = "secondary",
  loading = false,
  className,
  children,
  disabled,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  loading?: boolean;
}) {
  return (
    <button
      className={cn(buttonBase, buttonVariants[variant], className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading ? "Working…" : children}
    </button>
  );
}

export function LinkButton({
  href,
  variant = "secondary",
  className,
  children,
}: {
  href: string;
  variant?: ButtonVariant;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Link href={href} className={cn(buttonBase, buttonVariants[variant], className)}>
      {children}
    </Link>
  );
}

export function Field({
  label,
  htmlFor,
  required,
  hint,
  error,
  children,
}: {
  label: string;
  htmlFor: string;
  required?: boolean | undefined;
  hint?: string | undefined;
  error?: string | undefined;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-sm font-semibold text-ink">
        {label}
        {required ? (
          <span className="ml-1 text-accent" aria-hidden="true">
            *
          </span>
        ) : (
          <span className="ml-2 text-xs font-normal text-ink-muted">Optional</span>
        )}
      </label>
      {hint ? <p className="text-xs text-ink-muted">{hint}</p> : null}
      {children}
      {error ? (
        <p role="alert" className="text-xs font-medium text-error">
          {error}
        </p>
      ) : null}
    </div>
  );
}

const inputClass =
  "w-full rounded-md border border-divider bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-muted focus-visible:border-focus";

export function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(inputClass, props.className)} {...props} />;
}

export function TextArea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(inputClass, "min-h-28 resize-y", props.className)} {...props} />;
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn(inputClass, "pr-8", props.className)} {...props} />;
}

type ToneKey = "neutral" | "accent" | "success" | "warning" | "error" | "info";

const toneText: Record<ToneKey, string> = {
  neutral: "border-divider bg-subtle text-ink-secondary",
  accent: "border-accent/30 bg-accent-soft text-accent-pressed",
  success: "border-success/30 bg-success-soft text-success",
  warning: "border-warning/30 bg-warning-soft text-warning",
  error: "border-error/30 bg-error-soft text-error",
  info: "border-info/30 bg-info-soft text-info",
};

export function Badge({ tone = "neutral", children }: { tone?: ToneKey; children: ReactNode }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-sm border px-2 py-0.5 text-xs font-semibold",
        toneText[tone],
      )}
    >
      {children}
    </span>
  );
}

export function StatusCallout({
  tone = "info",
  title,
  children,
}: {
  tone?: ToneKey;
  title?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={cn("rounded-md border px-4 py-3 text-sm", toneText[tone])}
      role={tone === "error" ? "alert" : "status"}
    >
      {title ? <p className="font-semibold">{title}</p> : null}
      <div className={cn(title ? "mt-1" : "", "leading-relaxed")}>{children}</div>
    </div>
  );
}

export function Panel({
  title,
  description,
  action,
  children,
  className,
}: {
  title?: string | undefined;
  description?: string | undefined;
  action?: ReactNode;
  children: ReactNode;
  className?: string | undefined;
}) {
  return (
    <section
      className={cn(
        "rounded-lg border border-divider bg-surface",
        className,
      )}
    >
      {(title || action) && (
        <header className="flex flex-wrap items-start justify-between gap-3 border-b border-divider px-5 py-4">
          <div>
            {title ? <h2 className="text-lg">{title}</h2> : null}
            {description ? (
              <p className="mt-1 text-sm text-ink-secondary">{description}</p>
            ) : null}
          </div>
          {action}
        </header>
      )}
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-md border border-dashed border-divider bg-subtle/50 px-5 py-8 text-center">
      <p className="text-sm font-semibold text-ink">{title}</p>
      <p className="mx-auto mt-1 max-w-md text-sm text-ink-secondary">{children}</p>
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("rb-skeleton h-4 w-full", className)} aria-hidden="true" />;
}

export function SkeletonText({ lines = 3 }: { lines?: number }) {
  return (
    <div className="space-y-2" aria-hidden="true">
      {Array.from({ length: lines }).map((_, index) => (
        <Skeleton key={index} className={index === lines - 1 ? "w-2/3" : "w-full"} />
      ))}
    </div>
  );
}

export function ScoreBar({
  label,
  valueBp,
  weightPercent,
}: {
  label: string;
  valueBp: number;
  weightPercent?: string | undefined;
}) {
  const pct = Math.max(0, Math.min(100, valueBp / 100));
  return (
    <div className="grid grid-cols-[minmax(10rem,1fr)_minmax(6rem,2fr)_auto] items-center gap-3">
      <span className="text-sm text-ink">{label}</span>
      <span className="h-2.5 overflow-hidden rounded-full bg-subtle" aria-hidden="true">
        <span
          className="block h-full rounded-full bg-accent"
          style={{ width: `${pct}%` }}
        />
      </span>
      <span className="tnum text-sm text-ink-secondary">
        {pct.toFixed(1)}
        {weightPercent ? (
          <span className="ml-1 text-xs text-ink-muted">· w {weightPercent}%</span>
        ) : null}
      </span>
    </div>
  );
}

export function KeyValue({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-xs font-medium uppercase tracking-wide text-ink-muted">{label}</dt>
      <dd className="text-sm text-ink">{value}</dd>
    </div>
  );
}
