import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** Basis points (0–10000) to a 0–100 index string with two decimals. */
export function bpToIndex(bp: number): string {
  return (bp / 100).toFixed(2);
}

export function percentFromRatio(value: string | null): string {
  if (value === null) return "—";
  const ratio = Number(value);
  if (Number.isNaN(ratio)) return "—";
  return `${(ratio * 100).toFixed(1)}%`;
}

export function dash(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function dayLabel(day: number): string {
  return DAYS[day] ?? `Day ${day}`;
}

export function minuteLabel(minute: number): string {
  const hours = Math.floor(minute / 60);
  const mins = minute % 60;
  return `${String(hours).padStart(2, "0")}:${String(mins).padStart(2, "0")}`;
}

export function windowLabel(day: number, start: number, end: number): string {
  return `${dayLabel(day)} ${minuteLabel(start)}–${minuteLabel(end)}`;
}

export function titleCase(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

const REASON_LABELS: Record<string, string> = {
  missing_data: "Missing required profile data",
  no_eligible_projects: "No eligible projects",
  below_threshold: "All eligible scores below threshold",
  capacity_competition: "Limited capacity across the cohort",
};

export function reasonLabel(code: string): string {
  return REASON_LABELS[code] ?? titleCase(code);
}

const FACTOR_LABELS: Record<string, string> = {
  interest: "Research interest alignment",
  technical_skill: "Technical skill overlap",
  availability: "Availability beyond minimum",
  preference: "Ranked preference",
  learning_goal: "Learning-goal alignment",
};

export function factorLabel(key: string): string {
  return FACTOR_LABELS[key] ?? titleCase(key);
}

export function formatDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

/** Collision-resistant idempotency key for a consequential action in this session. */
export function newIdempotencyKey(scope: string): string {
  const rand =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2);
  return `${scope}-${rand}`;
}
