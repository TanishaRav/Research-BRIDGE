"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api, type DemoIdentity } from "./api";
import type { DemoRole, Persona } from "./types";

const STORAGE_KEY = "researchbridge.demo-identity";

interface DemoContextValue {
  identity: DemoIdentity | null;
  personas: Persona[];
  notice: string;
  loading: boolean;
  error: string | null;
  setIdentity: (identity: DemoIdentity) => void;
  personaLabel: (identity: DemoIdentity | null) => string;
}

const DemoContext = createContext<DemoContextValue | null>(null);

export function DemoProvider({ children }: { children: ReactNode }) {
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [notice, setNotice] = useState("");
  const [identity, setIdentityState] = useState<DemoIdentity | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    api
      .personas(controller.signal)
      .then((data) => {
        setPersonas(data.personas);
        setNotice(data.demo_only_notice);
        setError(null);
        const stored = readStoredIdentity();
        const valid =
          stored && data.personas.some((p) => p.role === stored.role && p.persona_id === stored.personaId);
        if (valid) {
          setIdentityState(stored);
        } else {
          const firstStudent = data.personas.find((p) => p.role === "student");
          if (firstStudent) {
            setIdentityState({ role: "student", personaId: firstStudent.persona_id });
          }
        }
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError(
          "Could not load demo personas. Confirm the ResearchBridge API is running on the configured URL.",
        );
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  const setIdentity = useCallback((next: DemoIdentity) => {
    setIdentityState(next);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    }
  }, []);

  const personaLabel = useCallback(
    (target: DemoIdentity | null) => {
      if (!target) return "No persona selected";
      const match = personas.find(
        (p) => p.role === target.role && p.persona_id === target.personaId,
      );
      return match?.label ?? target.personaId;
    },
    [personas],
  );

  const value = useMemo<DemoContextValue>(
    () => ({ identity, personas, notice, loading, error, setIdentity, personaLabel }),
    [identity, personas, notice, loading, error, setIdentity, personaLabel],
  );

  return <DemoContext.Provider value={value}>{children}</DemoContext.Provider>;
}

export function useDemo(): DemoContextValue {
  const ctx = useContext(DemoContext);
  if (!ctx) throw new Error("useDemo must be used inside DemoProvider");
  return ctx;
}

export function personasForRole(personas: Persona[], role: DemoRole): Persona[] {
  return personas.filter((p) => p.role === role);
}

function readStoredIdentity(): DemoIdentity | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as DemoIdentity;
    if (parsed && typeof parsed.role === "string" && typeof parsed.personaId === "string") {
      return parsed;
    }
  } catch {
    return null;
  }
  return null;
}
