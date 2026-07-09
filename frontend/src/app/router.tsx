import { lazy } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";

import { AuthLayout } from "@/components/layout/AuthLayout";
import { RequireAuth, RequireGuest, ShellLayout } from "@/app/RouteGuards";

const DashboardPage = lazy(() =>
  import("@/pages/DashboardPage").then((module) => ({ default: module.DashboardPage })),
);
const JobsPage = lazy(() =>
  import("@/pages/JobsPage").then((module) => ({ default: module.JobsPage })),
);
const SchedulerPage = lazy(() =>
  import("@/pages/SchedulerPage").then((module) => ({ default: module.SchedulerPage })),
);
const ReportsPage = lazy(() =>
  import("@/pages/ReportsPage").then((module) => ({ default: module.ReportsPage })),
);
const ProtocolsPage = lazy(() =>
  import("@/pages/ProtocolsPage").then((module) => ({ default: module.ProtocolsPage })),
);
const ArshinPage = lazy(() =>
  import("@/pages/ArshinPage").then((module) => ({ default: module.ArshinPage })),
);
const SettingsPage = lazy(() =>
  import("@/pages/SettingsPage").then((module) => ({ default: module.SettingsPage })),
);
const LoginPage = lazy(() =>
  import("@/pages/LoginPage").then((module) => ({ default: module.LoginPage })),
);
const NotFoundPage = lazy(() =>
  import("@/pages/NotFoundPage").then((module) => ({ default: module.NotFoundPage })),
);

export const router = createBrowserRouter([
  {
    path: "/",
    element: <Navigate to="/dashboard" replace />,
  },
  {
    element: <RequireGuest />,
    children: [
      {
        element: <AuthLayout />,
        children: [{ path: "/login", element: <LoginPage /> }],
      },
    ],
  },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <ShellLayout />,
        children: [
          { path: "/dashboard", element: <DashboardPage /> },
          { path: "/jobs", element: <JobsPage /> },
          { path: "/scheduler", element: <SchedulerPage /> },
          { path: "/reports", element: <ReportsPage /> },
          { path: "/protocols", element: <ProtocolsPage /> },
          { path: "/arshin", element: <ArshinPage /> },
          { path: "/settings", element: <SettingsPage /> },
        ],
      },
    ],
  },
  {
    path: "*",
    element: <NotFoundPage />,
  },
]);
