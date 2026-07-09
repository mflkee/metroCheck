import { Suspense, useEffect } from "react";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";

import { getCurrentUser } from "@/api/auth";
import { router } from "@/app/router";
import { useAuthStore } from "@/store/auth";

const queryClient = new QueryClient();

function RouteLoadingFallback() {
  return (
    <div className="min-h-screen bg-[var(--bg-primary)] px-5 py-8 text-[var(--text-primary)] sm:px-6">
      <div className="mx-auto flex max-w-4xl items-center gap-3 rounded-3xl border border-[var(--border-color)] bg-[var(--panel-bg)] px-5 py-4 shadow-panel">
        <div className="h-2.5 w-2.5 rounded-full bg-[var(--accent)]" aria-hidden="true" />
        <p className="text-sm font-medium text-[var(--text-muted)]">Загружаем раздел...</p>
      </div>
    </div>
  );
}

function AuthBootstrap() {
  const token = useAuthStore((state) => state.token);
  const user = useAuthStore((state) => state.user);
  const status = useAuthStore((state) => state.status);
  const setLoading = useAuthStore((state) => state.setLoading);
  const setSession = useAuthStore((state) => state.setSession);
  const markAnonymous = useAuthStore((state) => state.markAnonymous);

  useEffect(() => {
    if (!token) {
      if (status !== "anonymous" || user) {
        markAnonymous();
      }
      return;
    }

    if (status === "authenticated" && user) {
      return;
    }

    let isActive = true;
    setLoading();

    getCurrentUser(token)
      .then((currentUser) => {
        if (isActive) {
          setSession({ token, user: currentUser });
        }
      })
      .catch(() => {
        if (isActive) {
          markAnonymous();
        }
      });

    return () => {
      isActive = false;
    };
  }, [markAnonymous, setLoading, setSession, status, token, user]);

  return (
    <Suspense fallback={<RouteLoadingFallback />}>
      <RouterProvider router={router} />
    </Suspense>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthBootstrap />
    </QueryClientProvider>
  );
}
