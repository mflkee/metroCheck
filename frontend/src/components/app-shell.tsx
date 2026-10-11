import { type ReactNode, useEffect, useState } from "react"
import { Link, NavLink, useLocation } from "react-router-dom"

export type NavItem = {
  to: string
  label: string
  description?: string
  icon: ReactNode
  /** Match the path exactly (use for the index route). */
  end?: boolean
}

export type NavSection = {
  label?: string
  items: NavItem[]
}

type AppShellProps = {
  /** The brand shown in the top bar. */
  brand: ReactNode
  brandTo?: string
  /** Rendered right next to the brand — the application version badge. */
  versionBadge?: ReactNode
  /** The main navigation, in order. */
  nav: NavSection[]
  /** The block pinned to the bottom of the sidebar (metroLog puts «Справка» here). */
  help?: NavSection
  /** Top-bar indicator placed before the actions (a service's own health dot). */
  statusIndicator?: ReactNode
  /** Top-bar right-hand actions (the account menu). */
  topbarActions?: ReactNode
  /** A banner rendered under the top bar (a temporary-password warning). */
  banner?: ReactNode
  /** Title shown in the mobile drawer header. */
  mobileNavTitle?: string
  /** Where the collapsed state is remembered. */
  collapsedStorageKey?: string
  children: ReactNode
}

/**
 * The fleet application shell — metroLog's shell, generalised.
 *
 * It carries the layout, the sidebar behaviour (collapse, mobile drawer) and the
 * top bar, and takes everything service-specific as slots: the brand, the
 * navigation as data, the header actions. Because the markup and the classes come
 * from the shared theme, every service renders the same frame.
 */
export function AppShell({
  brand,
  brandTo = "/",
  versionBadge,
  nav,
  help,
  statusIndicator,
  topbarActions,
  banner,
  mobileNavTitle,
  collapsedStorageKey = "metro.sidebarCollapsed",
  children,
}: AppShellProps) {
  const location = useLocation()
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    if (typeof window === "undefined") {
      return false
    }
    return window.localStorage.getItem(collapsedStorageKey) === "1"
  })
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)

  useEffect(() => {
    window.localStorage.setItem(collapsedStorageKey, sidebarCollapsed ? "1" : "0")
  }, [collapsedStorageKey, sidebarCollapsed])

  useEffect(() => {
    setMobileSidebarOpen(false)
  }, [location.pathname])

  useEffect(() => {
    if (!mobileSidebarOpen) {
      return undefined
    }

    const previousBodyOverflow = document.body.style.overflow
    document.body.style.overflow = "hidden"

    return () => {
      document.body.style.overflow = previousBodyOverflow
    }
  }, [mobileSidebarOpen])

  return (
    <div className="min-h-screen min-w-full bg-mist text-ink">
      <div
        className={[
          "grid min-h-screen min-w-full grid-cols-1 transition-[grid-template-columns] duration-300",
          sidebarCollapsed ? "lg:grid-cols-[68px_minmax(0,1fr)]" : "lg:grid-cols-[280px_minmax(0,1fr)]",
        ].join(" ")}
      >
        <Sidebar
          collapsed={sidebarCollapsed}
          help={help}
          mobileNavTitle={mobileNavTitle}
          mobileOpen={mobileSidebarOpen}
          nav={nav}
          onCloseMobile={() => setMobileSidebarOpen(false)}
          onToggleCollapsed={() => setSidebarCollapsed((current) => !current)}
        />
        <div className="flex min-h-screen min-w-0 flex-col">
          <Topbar
            banner={banner}
            brand={brand}
            brandTo={brandTo}
            mobileNavigationOpen={mobileSidebarOpen}
            onToggleMobileNavigation={() => setMobileSidebarOpen((current) => !current)}
            statusIndicator={statusIndicator}
            topbarActions={topbarActions}
            versionBadge={versionBadge}
          />
          <main className="flex-1 px-2.5 pb-5 pt-2.5 sm:px-6 sm:pb-8 sm:pt-4 lg:px-8">{children}</main>
        </div>
      </div>
    </div>
  )
}

type SidebarProps = {
  collapsed: boolean
  mobileOpen: boolean
  nav: NavSection[]
  help?: NavSection
  mobileNavTitle?: string
  onCloseMobile: () => void
  onToggleCollapsed: () => void
}

function Sidebar({
  collapsed,
  mobileOpen,
  nav,
  help,
  mobileNavTitle,
  onCloseMobile,
  onToggleCollapsed,
}: SidebarProps) {
  return (
    <>
      <aside
        className={[
          "sidebar-shell hidden lg:sticky lg:top-0 lg:block lg:self-start lg:h-screen lg:overflow-y-auto lg:py-5 lg:backdrop-blur-sm lg:transition-[padding] lg:duration-300",
          collapsed ? "lg:px-1.5" : "lg:px-4",
        ].join(" ")}
      >
        <SidebarContent
          collapsed={collapsed}
          help={help}
          nav={nav}
          onToggleCollapsed={onToggleCollapsed}
        />
      </aside>

      {mobileOpen ? (
        <div className="sidebar-drawer lg:hidden" onClick={onCloseMobile}>
          <aside className="sidebar-drawer__panel" onClick={(event) => event.stopPropagation()}>
            <SidebarContent
              collapsed={false}
              help={help}
              isMobile
              mobileNavTitle={mobileNavTitle}
              nav={nav}
              onCloseMobile={onCloseMobile}
              onToggleCollapsed={onToggleCollapsed}
            />
          </aside>
        </div>
      ) : null}
    </>
  )
}

function SidebarContent({
  collapsed,
  isMobile = false,
  nav,
  help,
  mobileNavTitle,
  onCloseMobile,
  onToggleCollapsed,
}: {
  collapsed: boolean
  isMobile?: boolean
  nav: NavSection[]
  help?: NavSection
  mobileNavTitle?: string
  onCloseMobile?: () => void
  onToggleCollapsed: () => void
}) {
  return (
    <div className="flex h-full flex-col">
      {isMobile ? (
        <div className="sidebar-drawer__header">
          <div>
            <p className="sidebar-drawer__eyebrow">Навигация</p>
            {mobileNavTitle ? <div className="sidebar-drawer__title">{mobileNavTitle}</div> : null}
          </div>
          <button aria-label="Закрыть меню" className="sidebar-toggle" type="button" onClick={onCloseMobile}>
            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      ) : (
        <div className={["mb-6 flex", collapsed ? "justify-center" : "justify-end"].join(" ")}>
          <button
            aria-label={collapsed ? "Развернуть левое меню" : "Свернуть левое меню"}
            className="sidebar-toggle"
            type="button"
            onClick={onToggleCollapsed}
          >
            <svg className="h-6 w-6" viewBox="0 0 1024 1024" fill="currentColor">
              <path d="M768 102.4c54.186667 0 100.437333 19.2 138.752 57.514667C945.109333 198.229333 964.266667 244.48 964.266667 298.666667v426.666666c0 54.186667-19.2 100.437333-57.514667 138.794667C868.437333 902.4 822.186667 921.6 768 921.6H256c-54.186667 0-100.437333-19.2-138.752-57.514667C78.890667 825.813333 59.733333 779.52 59.733333 725.333333V298.666667c0-54.186667 19.2-100.437333 57.514667-138.752C155.562667 121.6 201.770667 102.4 256 102.4h512z m-512 85.333333c-73.941333 0-110.933333 36.992-110.933333 110.933334v426.666666c0 73.941333 36.949333 110.933333 110.933333 110.933334h85.333333V187.733333H256z m170.666667 648.533334h341.333333c73.941333 0 110.933333-36.992 110.933333-110.933334V298.666667c0-73.941333-36.992-110.933333-110.933333-110.933334h-341.333333v648.533334z" />
            </svg>
          </button>
        </div>
      )}

      {nav.map((section, index) => (
        <nav className="space-y-2" key={section.label ?? index}>
          {section.label ? (
            <div className="mb-2 px-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-steel/70">
              <span className={collapsed && !isMobile ? "lg:hidden" : ""}>{section.label}</span>
            </div>
          ) : null}
          {section.items.map((item) => (
            <SidebarNavItem
              collapsed={collapsed}
              item={item}
              key={item.to}
              onClick={onCloseMobile}
            />
          ))}
        </nav>
      ))}

      {help ? (
        <div className="mt-auto pt-6">
          <div className="mb-2 px-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-steel/70">
            <span className={collapsed && !isMobile ? "lg:hidden" : ""}>{help.label ?? ""}</span>
          </div>
          {help.items.map((item) => (
            <SidebarNavItem collapsed={collapsed} item={item} key={item.to} onClick={onCloseMobile} />
          ))}
        </div>
      ) : null}
    </div>
  )
}

function SidebarNavItem({
  collapsed,
  item,
  onClick,
}: {
  collapsed: boolean
  item: NavItem
  onClick?: () => void
}) {
  return (
    <NavLink
      title={item.description ? `${item.label} — ${item.description}` : item.label}
      to={item.to}
      end={item.end}
      className={({ isActive }) =>
        [
          "sidebar-nav-item block rounded-2xl transition",
          // Collapsed, the row *is* the icon, so the highlight has to be a square around it: a
          // row-shaped pill came out taller than it was wide and read as a stretched rectangle.
          collapsed
            ? "px-2.5 py-3 lg:mx-auto lg:flex lg:h-11 lg:w-11 lg:items-center lg:justify-center lg:rounded-xl lg:p-0"
            : "px-4 py-3",
          isActive ? "sidebar-nav-item--active text-ink" : "bg-transparent text-steel",
        ].join(" ")
      }
      onClick={onClick}
    >
      <div className={["flex items-center gap-3", collapsed ? "lg:justify-center" : ""].join(" ")}>
        <div className="nav-icon-badge">{item.icon}</div>
        <div className={collapsed ? "block lg:hidden" : "block"}>
          <div className="text-sm font-semibold">{item.label}</div>
          {item.description ? <div className="mt-1 text-xs">{item.description}</div> : null}
        </div>
      </div>
    </NavLink>
  )
}

type TopbarProps = {
  brand: ReactNode
  brandTo: string
  versionBadge?: ReactNode
  statusIndicator?: ReactNode
  topbarActions?: ReactNode
  banner?: ReactNode
  mobileNavigationOpen: boolean
  onToggleMobileNavigation: () => void
}

function Topbar({
  brand,
  brandTo,
  versionBadge,
  statusIndicator,
  topbarActions,
  banner,
  mobileNavigationOpen,
  onToggleMobileNavigation,
}: TopbarProps) {
  return (
    <header className="shell-topbar z-20 border-b border-line px-3 py-1.5 backdrop-blur-sm sm:px-4 lg:sticky lg:top-0 lg:px-6">
      <div className="flex min-w-0 items-center gap-2 sm:gap-3">
        <div className="flex min-w-0 flex-1 items-center gap-2 sm:gap-3">
          <button
            aria-expanded={mobileNavigationOpen}
            aria-label={mobileNavigationOpen ? "Закрыть навигацию" : "Открыть навигацию"}
            className="mobile-nav-toggle lg:hidden"
            type="button"
            onClick={onToggleMobileNavigation}
          >
            {mobileNavigationOpen ? (
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
              </svg>
            ) : (
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 7h16M4 12h16M4 17h16" />
              </svg>
            )}
          </button>
          <div className="flex min-w-0 items-baseline gap-1.5">
            {/* A plain link on purpose: the wordmark is the way home, not the current page. */}
            <Link className="shrink-0 text-sm font-semibold text-ink sm:text-base" to={brandTo}>
              {brand}
            </Link>
            {versionBadge}
          </div>
        </div>
        {statusIndicator}
        <div className="flex min-w-0 flex-1 justify-end">{topbarActions}</div>
      </div>
      {banner ? (
        <div className="shell-status-banner mt-2 rounded-2xl border border-signal-info px-4 py-2.5 text-sm text-ink">
          {banner}
        </div>
      ) : null}
    </header>
  )
}
