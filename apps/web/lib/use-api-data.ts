"use client";

import { ApiError } from "@ezo/shared";
import { useCallback, useEffect, useState } from "react";

export function toApiError(error: unknown): ApiError {
  return error instanceof ApiError ? error : new ApiError(0, "unknown", String(error));
}

/**
 * Fetch data for a screen. `fetcher` must be memoized (useCallback); it is
 * called again whenever it changes or `reload()` is called.
 */
export function useApiData<T>(fetcher: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetcher().then(
      (value) => {
        if (cancelled) return;
        setData(value);
        setError(null);
      },
      (reason: unknown) => {
        if (!cancelled) setError(toApiError(reason));
      },
    );
    return () => {
      cancelled = true;
    };
  }, [fetcher, version]);

  const reload = useCallback(() => setVersion((value) => value + 1), []);
  return { data, error, reload, loading: data === null && error === null };
}
