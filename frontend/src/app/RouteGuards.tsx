import { Navigate, Outlet, useLocation } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { useAuthStore } from "@/store/auth";

export function ShellLayout() {
  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}

export function RequireAuth() {
  const location = useLocation();
  const status = useAuthStore((state) => state.status);

  if (status === "loading") {
    return (
      <RouteStatePage
        title="Загрузка рабочей среды"
        description="Проверяем сохранённую сессию и права доступа."
      />
    );
  }

  if (status === "anonymous") {
    return (
      <Navigate
        replace
        state={{ from: location.pathname }}
        to="/login"
      />
    );
  }

  return <Outlet />;
}

export function RequireGuest() {
  const status = useAuthStore((state) => state.status);

  if (status === "loading") {
    return (
      <RouteStatePage
        title="Проверка сессии"
        description="Подтягиваем текущего пользователя перед показом экрана входа."
      />
    );
  }

  if (status === "authenticated") {
    return <Navigate replace to="/dashboard" />;
  }

  return <Outlet />;
}

function RouteStatePage({ title, description }: { title: string; description: string }) {
  return (
    <main className="auth-layout">
      <section className="auth-panel space-y-3">
        <h1 className="text-2xl font-semibold text-ink">{title}</h1>
        <p className="max-w-md text-sm text-steel">{description}</p>
      </section>
    </main>
  );
}
