import { NavLink, Outlet } from "react-router-dom"
import { CalendarClock, LayoutDashboard, LogOut } from "lucide-react"
import { cn } from "cn"
import { LogoMark } from "@/components/logo"
import { useAuth } from "@/state/auth"
import { useHealth } from "@/state/health"

const NAV = [
  { to: "/", label: "Дашборд", icon: LayoutDashboard, end: true },
  { to: "/scheduler", label: "Планировщик", icon: CalendarClock, end: false },
]

export function AppLayout() {
  const { problemCount } = useHealth()
  const { logout } = useAuth()
  const online = problemCount === 0

  return (
    <div className="flex min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-10 flex w-56 flex-col border-r border-border bg-sidebar">
        <div className="flex items-center gap-2.5 border-b border-border px-4 py-5">
          <LogoMark size={26} />
          <div className="overflow-hidden">
            <h1 className="text-lg leading-none font-bold">metroChek</h1>
            <span className="text-[10px] tracking-wide text-muted-foreground">
              Контроль протоколов поверки
            </span>
          </div>
        </div>
        <nav className="flex-1 space-y-1 p-2">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )
              }
            >
              <item.icon className="size-4 shrink-0" />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="flex items-center gap-2 border-t border-border px-4 py-3 text-xs text-muted-foreground">
          <span
            className={cn(
              "size-2 shrink-0 rounded-full",
              online ? "bg-emerald-500 shadow-[0_0_6px] shadow-emerald-500" : "bg-destructive shadow-[0_0_6px] shadow-destructive",
            )}
          />
          <span className="flex-1">{online ? "Сервер онлайн" : "Есть проблемы"}</span>
          <button
            type="button"
            onClick={logout}
            title="Выйти"
            className="rounded-md p-1 transition-colors hover:bg-muted hover:text-foreground"
          >
            <LogOut className="size-4" />
          </button>
        </div>
      </aside>
      <main className="ml-56 min-w-0 flex-1 p-6 lg:p-8">
        <Outlet />
      </main>
    </div>
  )
}
