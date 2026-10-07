import { BrowserRouter, Route, Routes } from "react-router-dom"
import { AppLayout } from "@/components/layout/app-layout"
import { LoginPage } from "@/components/login-page"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { DashboardPage } from "@/pages/dashboard"
import { SchedulerPage } from "@/pages/scheduler"
import { AuthProvider, useAuth } from "@/state/auth"
import { HealthProvider } from "@/state/health"

function Gate() {
  const { authed } = useAuth()
  if (!authed) return <LoginPage />
  return (
    <HealthProvider>
      <AppLayout />
    </HealthProvider>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <TooltipProvider delayDuration={200}>
        <BrowserRouter>
          <Routes>
            <Route element={<Gate />}>
              <Route index element={<DashboardPage />} />
              <Route path="scheduler" element={<SchedulerPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
        <Toaster theme="dark" position="top-right" richColors />
      </TooltipProvider>
    </AuthProvider>
  )
}
