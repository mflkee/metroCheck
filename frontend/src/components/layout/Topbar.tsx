import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { fetchHealth } from "@/api/health";
import { useAuthStore } from "@/store/auth";

const routeLabels: Array<{ match: RegExp; label: string }> = [
  { match: /^\/$/, label: "Главная" },
  { match: /^\/dashboard$/, label: "Главная" },
  { match: /^\/jobs$/, label: "Очередь и задачи" },
  { match: /^\/scheduler$/, label: "Планировщик" },
  { match: /^\/reports$/, label: "Отчёты" },
  { match: /^\/protocols$/, label: "Протоколы" },
  { match: /^\/arshin$/, label: "Аршин" },
  { match: /^\/settings$/, label: "Настройки" },
];

type TopbarProps = {
  mobileNavigationOpen: boolean;
  onToggleMobileNavigation: () => void;
};

export function Topbar({ mobileNavigationOpen, onToggleMobileNavigation }: TopbarProps) {
  const location = useLocation();
  const user = useAuthStore((state) => state.user);
  const clearSession = useAuthStore((state) => state.clearSession);
  const currentSection =
    routeLabels.find((item) => item.match.test(location.pathname))?.label ?? "Рабочая область";

  const [healthOk, setHealthOk] = useState(true);

  useEffect(() => {
    fetchHealth()
      .then((h) => setHealthOk(h.status === "ok"))
      .catch(() => setHealthOk(false));
  }, []);

  return (
    <header className="shell-topbar z-20 border-b border-line px-3 py-2 backdrop-blur sm:px-4 sm:py-2.5 lg:sticky lg:top-0 lg:px-8 lg:py-3">
      <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-x-2 sm:gap-x-3">
        <div className="flex min-w-0 items-center gap-2 sm:gap-3">
          <button
            aria-expanded={mobileNavigationOpen}
            aria-label={mobileNavigationOpen ? "Закрыть навигацию" : "Открыть навигацию"}
            className="mobile-nav-toggle lg:hidden"
            type="button"
            onClick={onToggleMobileNavigation}
          >
            {mobileNavigationOpen ? (
              <svg
                className="h-5 w-5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M6 18 18 6M6 6l12 12"
                />
              </svg>
            ) : (
              <svg
                className="h-5 w-5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M4 7h16M4 12h16M4 17h16"
                />
              </svg>
            )}
          </button>
          <div className="hidden min-w-0 truncate text-[11px] uppercase tracking-[0.18em] text-steel sm:block sm:text-xs sm:tracking-[0.22em]">
            {currentSection}
          </div>
          <Link className="shrink-0 text-sm font-semibold text-ink sm:text-base" to="/dashboard">
            metroChek
          </Link>
          <div
            className="hidden shrink-0 items-center gap-2 text-xs font-medium sm:inline-flex"
            title={healthOk ? "Сервер онлайн" : "Сервер недоступен"}
          >
            <span
              aria-hidden="true"
              className={[
                "h-2.5 w-2.5 rounded-full",
                healthOk ? "bg-[var(--success)]" : "bg-[var(--danger)]",
              ].join(" ")}
            />
            <span className="whitespace-nowrap text-steel">{healthOk ? "Сервер" : "Сервер"}</span>
          </div>
        </div>
        <div className="justify-self-end flex items-center gap-2">
          {user ? (
            <>
              <span className="hidden text-sm font-semibold text-ink sm:block">{user.username}</span>
              <button
                className="btn-danger btn-sm"
                type="button"
                onClick={() => clearSession()}
              >
                Выйти
              </button>
            </>
          ) : (
            <Link className="btn-primary btn-sm" to="/login">
              Войти
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
