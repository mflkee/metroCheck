import { create } from "zustand";

import type { AuthUser } from "@/api/auth";

export type AuthStatus = "loading" | "authenticated" | "anonymous";

type SessionPayload = {
  token: string;
  user: AuthUser;
};

type AuthState = {
  token: string | null;
  user: AuthUser | null;
  status: AuthStatus;
  setLoading: () => void;
  setSession: (payload: SessionPayload) => void;
  markAnonymous: () => void;
  clearSession: () => void;
};

const STORAGE_KEY = "metrocheck.auth.token";

function getStoredToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(STORAGE_KEY);
}

function persistToken(token: string | null): void {
  if (typeof window === "undefined") {
    return;
  }
  if (token) {
    window.localStorage.setItem(STORAGE_KEY, token);
    return;
  }
  window.localStorage.removeItem(STORAGE_KEY);
}

const initialToken = getStoredToken();

export const useAuthStore = create<AuthState>((set) => ({
  token: initialToken,
  user: null,
  status: initialToken ? "loading" : "anonymous",
  setLoading: () =>
    set((state) => ({
      status: state.token ? "loading" : "anonymous",
    })),
  setSession: ({ token, user }) => {
    persistToken(token);
    set({
      token,
      user,
      status: "authenticated",
    });
  },
  markAnonymous: () => {
    persistToken(null);
    set({
      token: null,
      user: null,
      status: "anonymous",
    });
  },
  clearSession: () => {
    persistToken(null);
    set({
      token: null,
      user: null,
      status: "anonymous",
    });
  },
}));
