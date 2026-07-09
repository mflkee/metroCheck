import { Outlet } from "react-router-dom";

export function AuthLayout() {
  return (
    <main className="auth-layout">
      <section className="auth-panel space-y-6">
        <p className="text-base font-semibold tracking-[0.02em] text-signal-info">metroChek</p>
        <Outlet />
      </section>
    </main>
  );
}
