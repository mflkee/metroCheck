import { BrowserRouter, Route, Routes } from "react-router-dom"
import { Toaster } from "sonner"
import { AppLayout } from "@/components/layout/app-layout"
import { LoginPage } from "@/components/login-page"
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
      <BrowserRouter>
        <Routes>
          <Route element={<Gate />}>
            <Route index element={<DashboardPage />} />
            <Route path="scheduler" element={<SchedulerPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
      <Toaster position="top-right" theme="dark" richColors />
    </AuthProvider>
  )
}
