"use client";

import type { Conversation, SystemStatus } from "@ezo/shared";
import type { ApiError } from "@ezo/shared";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./api";
import { toApiError as asApiError } from "./use-api-data";

interface AppState {
  status: SystemStatus | null;
  statusError: ApiError | null;
  conversations: Conversation[];
  refreshConversations: () => Promise<void>;
  refreshStatus: () => Promise<void>;
  showDebug: boolean;
  setShowDebug: (value: boolean) => void;
}

const AppContext = createContext<AppState | null>(null);


export function AppProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [statusError, setStatusError] = useState<ApiError | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [showDebug, setShowDebug] = useState(false);

  const refreshStatus = useCallback(async () => {
    try {
      setStatus(await api.status());
      setStatusError(null);
    } catch (error) {
      setStatusError(asApiError(error));
    }
  }, []);

  const refreshConversations = useCallback(async () => {
    try {
      setConversations(await api.listConversations());
    } catch (error) {
      setStatusError(asApiError(error));
    }
  }, []);

  // Initial load; later refreshes are triggered by the screens.
  useEffect(() => {
    let cancelled = false;
    Promise.allSettled([api.status(), api.listConversations()]).then(([statusResult, listResult]) => {
      if (cancelled) return;
      if (statusResult.status === "fulfilled") setStatus(statusResult.value);
      else setStatusError(asApiError(statusResult.reason));
      if (listResult.status === "fulfilled") setConversations(listResult.value);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo(
    () => ({ status, statusError, conversations, refreshConversations, refreshStatus, showDebug, setShowDebug }),
    [status, statusError, conversations, refreshConversations, refreshStatus, showDebug],
  );
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppState {
  const value = useContext(AppContext);
  if (!value) throw new Error("useApp must be used inside AppProvider");
  return value;
}
