"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, type DemoIdentity } from "./api";
import { useDemo } from "./demo-context";

export interface ApiState<T> {
  data: T | null;
  loading: boolean;
  error: ApiError | null;
  refetch: () => void;
}

/**
 * Load data that depends on the current demo identity. Cancels in-flight requests
 * on identity change or unmount and preserves the previous data during refetches.
 */
export function useApiResource<T>(
  loader: (identity: DemoIdentity, signal: AbortSignal) => Promise<T>,
  deps: ReadonlyArray<unknown>,
  options: { enabled?: boolean } = {},
): ApiState<T> {
  const { identity } = useDemo();
  const enabled = options.enabled ?? true;
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<ApiError | null>(null);
  const [tick, setTick] = useState(0);

  const loaderRef = useRef(loader);
  useEffect(() => {
    loaderRef.current = loader;
  });

  useEffect(() => {
    if (!identity || !enabled) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    let cancelled = false;
    setLoading(true);
    loaderRef
      .current(identity, controller.signal)
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled || (err instanceof DOMException && err.name === "AbortError")) return;
        setError(
          err instanceof ApiError
            ? err
            : new ApiError(0, "unknown", "An unexpected error occurred."),
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [identity?.role, identity?.personaId, enabled, tick, ...deps]);

  const refetch = useCallback(() => setTick((value) => value + 1), []);
  return { data, loading, error, refetch };
}
