"use client";

import { useSyncExternalStore } from "react";
import { readStorage, writeStorage } from "./storage";

/**
 * A string value persisted in localStorage and readable as a React hook.
 * The server render always uses `fallback`; the browser then switches to the
 * stored value without a hydration mismatch.
 */
export function createStoredValue<T extends string>(
  key: string,
  fallback: T,
  isValid: (value: string) => value is T,
) {
  const listeners = new Set<() => void>();

  function subscribe(listener: () => void) {
    listeners.add(listener);
    const onStorage = (event: StorageEvent) => {
      if (event.key === key) listener();
    };
    window.addEventListener("storage", onStorage);
    return () => {
      listeners.delete(listener);
      window.removeEventListener("storage", onStorage);
    };
  }

  function get(): T {
    const value = readStorage(key);
    return value !== null && isValid(value) ? value : fallback;
  }

  function set(value: T | null) {
    writeStorage(key, value);
    for (const listener of listeners) listener();
  }

  function useValue(): T {
    return useSyncExternalStore(subscribe, get, () => fallback);
  }

  return { get, set, useValue };
}
