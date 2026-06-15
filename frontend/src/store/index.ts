import { createContext, useContext } from "react";
import type { DashboardStats } from "@/types";

export interface AppState {
  stats: DashboardStats | null;
  loading: boolean;
  error: string | null;
}

export const AppStateContext = createContext<AppState>({
  stats: null,
  loading: false,
  error: null,
});

export function useAppState() {
  return useContext(AppStateContext);
}
