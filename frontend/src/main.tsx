import React from "react";
import ReactDOM from "react-dom/client";

import { App } from "@/app/App";
import { initializeTheme } from "@/store/theme";
import "@/shared/styles.css";

initializeTheme();

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
