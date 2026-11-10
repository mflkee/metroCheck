import type { ReactNode } from "react"
import { CalendarClock, FileCheck2, LayoutDashboard } from "lucide-react"
import { Outlet } from "react-router-dom"
import { AppShell, type NavSection } from "@/components/app-shell"
import { AccountMenu } from "@/components/layout/account-menu"
import { VersionBadgeWithHistory } from "@/components/version-history"
import { HealthIndicator } from "@/components/layout/health-indicator"

/**
 * The navigation is data: the shell (from `@metro/app-shell`) renders whatever it is
 * handed, so the app keeps only its own list and its own icons.
 */
const NAV: NavSection[] = [
  {
    items: [
      {
        to: "/",
        label: "Дашборд",
        description: "Очередь, история и запуск проверок",
        icon: <LayoutDashboard className="h-5 w-5" />,
        end: true,
      },
      {
        to: "/scheduler",
        label: "Планировщик",
        description: "Расписание и email-отчёты",
        icon: <CalendarClock className="h-5 w-5" />,
      },
      {
        to: "/precheck",
        label: "Перед АРШИНом",
        description: "Проверка пачки перед загрузкой",
        icon: <FileCheck2 className="h-5 w-5" />,
      },
    ],
  },
]

export function AppLayout({ children }: { children?: ReactNode }) {
  return (
    <AppShell
      brand="metroChek"
      brandTo="/"
      mobileNavTitle="metroChek"
      nav={NAV}
      statusIndicator={<HealthIndicator />}
      topbarActions={<AccountMenu />}
      versionBadge={<VersionBadgeWithHistory />}
    >
      {children ?? <Outlet />}
    </AppShell>
  )
}
