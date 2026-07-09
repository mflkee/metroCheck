import { type ReactNode, useEffect, useState } from "react";
import { useLocation } from "react-router-dom";

import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";

type AppShellProps = {
  children: ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  const location = useLocation();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    if (typeof window === "undefined") {
      return false;
    }
    return window.localStorage.getItem("metrocheck.sidebarCollapsed") === "1";
  });
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  useEffect(() => {
    window.localStorage.setItem("metrocheck.sidebarCollapsed", sidebarCollapsed ? "1" : "0");
  }, [sidebarCollapsed]);

  useEffect(() => {
    setMobileSidebarOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!mobileSidebarOpen) {
      return undefined;
    }
    const previousBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousBodyOverflow;
    };
  }, [mobileSidebarOpen]);

  return (
    <div className="min-h-screen min-w-full bg-mist text-ink">
      <div
        className={[
          "grid min-h-screen min-w-full grid-cols-1 transition-[grid-template-columns] duration-300",
          sidebarCollapsed
            ? "lg:grid-cols-[78px_minmax(0,1fr)]"
            : "lg:grid-cols-[280px_minmax(0,1fr)]",
        ].join(" ")}
      >
        <Sidebar
          collapsed={sidebarCollapsed}
          mobileOpen={mobileSidebarOpen}
          onCloseMobile={() => setMobileSidebarOpen(false)}
          onToggleCollapsed={() => setSidebarCollapsed((current) => !current)}
        />
        <div className="flex min-h-screen min-w-0 flex-col">
          <Topbar
            mobileNavigationOpen={mobileSidebarOpen}
            onToggleMobileNavigation={() => setMobileSidebarOpen((current) => !current)}
          />
          <main className="flex-1 px-2.5 pb-5 pt-2.5 sm:px-6 sm:pb-8 sm:pt-4 lg:px-8">{children}</main>
        </div>
      </div>
    </div>
  );
}
