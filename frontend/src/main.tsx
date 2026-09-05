import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { RouterProvider } from "react-router/dom"
import { ThemeProvider } from "@/components/theme-provider"
// oxlint-disable-next-line import/no-unassigned-import -- Vite loads the global stylesheet for its side effect.
import "./index.css"
import { router } from "./App"

const root = document.getElementById("root")
if (!root) throw new Error("The page could not start.")
createRoot(root).render(
  <StrictMode>
    <ThemeProvider>
      <RouterProvider router={router} />
    </ThemeProvider>
  </StrictMode>,
)
